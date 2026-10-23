from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
from routers import positions as routes
from services import cboe, position_quotes as quotes

NOW = datetime(2026, 10, 22, 23, 45, tzinfo=timezone.utc)


def position(**changes):
    return {"id": 1, "symbol": "QQQ", "strategy": "sell_put", "strike": 675,
            "premium": 1.96, "quantity": 5, "expiration_date": "2026-10-29", **changes}


def market_quote(**changes):
    return {"spot": 702.99, "bid": 3.01, "ask": 3.14, "iv": .3406,
            "source": "cboe", "quoteAsOf": "2026-10-22 23:42:58",
            "quoteStatus": "delayed", **changes}


def chain(**changes):
    row = {"strike": 675, "bid": 3.01, "ask": 3.14, "lastPrice": .2838,
           "impliedVolatility": .3406, **changes}
    return {"puts": pd.DataFrame([row]), "calls": pd.DataFrame([row])}


def test_screenshot_position_uses_buyback_ask_and_five_contracts():
    row = quotes.mark_position(position(), market_quote(), NOW)
    assert row["currentPremium"] == 3.14
    assert row["unrealizedPnl"] == -590
    assert row["unrealizedPnlPct"] == -60.2
    assert row["positionDelta"] > 0
    assert row["positionTheta"] > 0
    assert row["positionVega"] < 0
    assert row["dte"] == 7
    assert row["quoteAsOf"] == "2026-10-22 23:42:58"


def test_long_put_uses_bid_and_opposite_exposure():
    short = quotes.mark_position(position(), market_quote(), NOW)
    long = quotes.mark_position(position(strategy="buy_put"), market_quote(), NOW)
    assert long["currentPremium"] == 3.01
    assert long["unrealizedPnl"] == 525
    assert long["positionDelta"] == -short["positionDelta"]
    assert long["positionTheta"] == -short["positionTheta"]


def test_missing_quotes_are_not_replaced_with_model_or_zero():
    row = quotes.mark_position(position(), None, NOW)
    assert row["unrealizedPnl"] is None and row["currentPremium"] is None
    assert row["error"]
    assert quotes.aggregate_greeks([position()], [row])["totalDelta"] is None
    assert all(s["pnlChange"] is None for s in quotes.stress_scenarios([row]))


def test_missing_iv_keeps_observed_pnl_but_not_model_greeks():
    row = quotes.mark_position(position(), market_quote(iv=None), NOW)
    assert row["unrealizedPnl"] == -590
    assert row["positionDelta"] is None


def test_expired_positions_need_reconciliation_not_fictional_day_to_expiry():
    row = quotes.mark_position(position(expiration_date="2026-10-21"), market_quote(), NOW)
    assert row["quoteStatus"] == "expired"
    assert row["dte"] == -1 and row["unrealizedPnl"] is None


def test_greeks_theta_sign_and_collateral_are_consistent():
    pos = position()
    row = quotes.mark_position(pos, market_quote(), NOW)
    totals = quotes.aggregate_greeks([pos], [row])
    assert totals["dailyThetaIncome"] == row["positionTheta"] > 0
    assert totals["totalCapitalAtRisk"] == 337500
    assert totals["sellPutCount"] == 5


def test_stress_reprices_spot_and_iv_with_direction_and_quantity():
    pos = position()
    five = quotes.stress_scenarios([quotes.mark_position(pos, market_quote(), NOW)])
    one = quotes.stress_scenarios([quotes.mark_position(position(quantity=1), market_quote(), NOW)])
    long = quotes.stress_scenarios([quotes.mark_position(position(strategy="buy_put"), market_quote(), NOW)])
    assert five[0]["pnlChange"] < -10000  # 15% decline on five $675 short puts
    assert five[2]["pnlChange"] == 0
    assert five[-1]["pnlChange"] > 0
    for full, single, opposite in zip(five, one, long):
        assert full["pnlChange"] == pytest.approx(single["pnlChange"] * 5, abs=.03)
        assert full["pnlChange"] == -opposite["pnlChange"]


def test_stress_includes_iv_shock(monkeypatch):
    monkeypatch.setattr(quotes, "SCENARIOS", [("IV only", 0, .5)])
    row = quotes.mark_position(position(), market_quote(), NOW)
    assert quotes.stress_scenarios([row])[0]["pnlChange"] < 0


@pytest.mark.parametrize("changes", [{"strike": 680}, {"bid": -1}, {"ask": 0},
                                     {"ask": 2.5}, {"bid": float("nan")}, {"ask": float("inf")}])
def test_exact_contract_and_valid_quote_required(changes):
    assert quotes._contract(chain(**changes), position()) is None


def test_no_bid_is_not_a_sellable_long_position():
    assert quotes._contract(chain(bid=0), position(strategy="buy_put")) is None
    assert quotes._contract(chain(bid=0), position()) is not None


def test_exact_expiry_falls_back_to_yahoo_and_never_uses_last_trade_time(monkeypatch):
    monkeypatch.setattr(cboe, "fetch", lambda *a, **kw: {
        "current_price": 999, "chains": {"2026-10-30": chain()}, "quote_as_of": "old",
    })
    fallback = SimpleNamespace(puts=chain()["puts"], calls=chain()["calls"],
                               underlying={"regularMarketPrice": 702.99})
    ticker = Mock()
    ticker.option_chain.return_value = fallback
    monkeypatch.setattr(quotes.yf, "Ticker", lambda _: ticker)
    result = quotes._load_symbol("QQQ", [position()], True)[1]
    ticker.option_chain.assert_called_once_with("2026-10-29")
    assert result["spot"] == 702.99 and result["source"] == "yfinance"
    assert result["quoteAsOf"] is None and result["quoteStatus"] == "time_unknown"


def test_snapshot_fetches_each_symbol_once_and_skips_expired(monkeypatch):
    loader = Mock(return_value={1: market_quote(), 2: market_quote()})
    monkeypatch.setattr(quotes, "_load_symbol", loader)
    result = quotes.build_snapshot([position(), position(id=2),
                                   position(id=3, expiration_date="2026-10-21")], True, NOW)
    loader.assert_called_once()
    assert loader.call_args.args[2] is True
    assert len(loader.call_args.args[1]) == 2
    assert result["data"][2]["quoteStatus"] == "expired"
    assert result["greeks"]["complete"] is False


def test_cboe_force_refresh_bypasses_two_minute_cache(monkeypatch):
    monkeypatch.setattr(cboe, "_cache", {})
    build = Mock(side_effect=[{"current_price": 704.47}, {"current_price": 702.99}])
    monkeypatch.setattr(cboe, "_build", build)
    assert cboe.fetch("QQQ")["current_price"] == 704.47
    assert cboe.fetch("QQQ")["current_price"] == 704.47
    assert cboe.fetch("QQQ", force_refresh=True)["current_price"] == 702.99
    assert build.call_count == 2


def test_cboe_preserves_source_timestamp(monkeypatch):
    monkeypatch.setattr(cboe, "_get_json", lambda _: {
        "timestamp": "2026-10-22 23:42:58", "data": {"current_price": 702.99,
        "options": [{"option": "QQQ261029P00675000", "bid": 3.01, "ask": 3.14, "iv": .3406}]},
    })
    result = cboe._build("QQQ")
    assert result["quote_as_of"] == "2026-10-22 23:42:58"
    assert "2026-10-29" in result["chains"]


def test_snapshot_route_is_read_only_and_disables_http_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "positions.db")
    database.init_db()
    with database.get_conn() as conn:
        conn.execute("INSERT INTO positions (symbol,strategy,strike,premium,quantity,expiration_date,open_date) "
                     "VALUES ('QQQ','sell_put',675,1.96,5,'2026-10-29','2026-10-01')")
        conn.commit()
    build = Mock(return_value={"data": [], "greeks": {}, "scenarios": [], "fetchedAt": NOW.isoformat()})
    monkeypatch.setattr(quotes, "build_snapshot", build)
    app = FastAPI()
    app.include_router(routes.router)
    response = TestClient(app).get("/api/portfolio/snapshot?force_refresh=true")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert build.call_args.kwargs["force_refresh"] is True
    assert build.call_args.args[0][0]["quantity"] == 5
    with database.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0] == 1
