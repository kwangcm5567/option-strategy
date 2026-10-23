"""Scanner regressions, using deterministic quotes instead of live market data."""
from datetime import datetime
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import scanner as route
from services import cache, scanner
from services.simple import evaluate_put


def quote(**changes) -> dict:
    return {"strike": 93.0, "bid": 1.0, "ask": 1.05, "lastPrice": 9.0,
            "impliedVolatility": 0.30, "openInterest": 1000, "volume": 100, **changes}


def candidate(**changes) -> dict | None:
    return evaluate_put(quote(**changes), "SPY", 100, "2026-11-24", 35, 0.65, 0.01)


def test_bid_and_round_trip_costs_drive_cash_secured_payoff():
    result = candidate()
    assert result is not None
    assert result["premium"] == 1.0  # Ignore last trade at $9.
    assert result["estimatedRoundTripCosts"] == 3.30
    assert result["netCredit"] == 96.70
    assert result["capitalRequired"] == 9300
    assert result["netMaxLoss"] == 9203.30
    assert result["netBreakEven"] == 92.03
    assert result["closeTarget"] == 0.50
    assert result["targetNetProfit"] == 46.70
    assert result["netReturnPct"] == 1.04


@pytest.mark.parametrize("changes", [
    {"bid": 0}, {"ask": 0}, {"ask": 0.9}, {"ask": 1.5},
    {"bid": float("nan")}, {"ask": float("inf")}, {"impliedVolatility": 0},
    {"bid": None}, {"ask": "invalid"}, {"bid": 94, "ask": 95},
    {"openInterest": 99}, {"openInterest": float("nan")},
    {"strike": 100}, {"strike": 50}, {"strike": 99},
])
def test_invalid_or_unsuitable_quotes_are_rejected(changes):
    assert candidate(**changes) is None


def test_simple_rules_do_not_depend_on_intraday_trade_volume():
    assert candidate(volume=0) is not None


def test_costs_can_eliminate_an_apparently_profitable_trade():
    assert evaluate_put(quote(), "SPY", 100, "2026-11-24", 35, 26, 0) is None


@pytest.mark.parametrize("symbol,dte", [("TSLA", 35), ("SPY", 29), ("SPY", 46)])
def test_simple_universe_and_dte_are_enforced(symbol, dte):
    assert evaluate_put(quote(), symbol, 100, "2026-11-24", dte, 0.65, 0.01) is None


def test_windows_begin_after_entry_close_and_include_horizon_end():
    history = pd.DataFrame({"Close": [100, 100, 100], "Low": [1, 95, 70],
                            "High": [999, 105, 130]}, index=pd.date_range("2026-01-01", periods=3))
    down = scanner._precompute_windows(history, 3)  # 2 trading sessions
    up = scanner._precompute_up_windows(history, 3)
    assert len(down) == len(up) == 1
    assert down[0][2:] == (70, 0.30)
    assert up[0][2:] == (130, 0.30)


def history() -> pd.DataFrame:
    return pd.DataFrame({"Close": [100.0] * 100, "Low": [99.0] * 100,
                         "High": [101.0] * 100}, index=pd.date_range("2026-01-01", periods=100))


def test_each_expiry_uses_its_own_full_history_horizon(monkeypatch):
    monkeypatch.setattr(scanner.cboe, "fetch_history", lambda _: history())
    chain = {"puts": pd.DataFrame([quote()]), "calls": pd.DataFrame()}
    monkeypatch.setattr(scanner.cboe, "fetch", lambda _: {
        "current_price": 100, "change_pct": 0,
        "chains": {"2026-11-19": chain, "2026-12-04": chain},
    })
    seen = []
    def process(*args, **kwargs):
        seen.append((args[8], len(kwargs["down_windows"])))
    monkeypatch.setattr(scanner, "_process_row", process)
    scanner._process_ticker("SPY", ["sell_put"], datetime(2026, 10, 20, 15),
                            30, 45, {}, {}, True, False)
    assert seen == [("2026-11-19", 80), ("2026-12-04", 69)]


def test_budget_filter_runs_before_selecting_one_contract_per_symbol(monkeypatch):
    queried = []
    def process(symbol, *args):
        queried.append(symbol)
        return [
            {"symbol": symbol, "strategy": "sell_put", "delta": -.20,
             "capitalRequired": 12000, "bidAskSpreadPct": 2, "netReturnPct": 1,
             "expirationDate": "2026-11-24", "strike": 120},
            {"symbol": symbol, "strategy": "sell_put", "delta": -.21,
             "capitalRequired": 9000, "bidAskSpreadPct": 2, "netReturnPct": 1,
             "expirationDate": "2026-11-24", "strike": 90},
        ]
    monkeypatch.setattr(scanner, "_process_ticker", process)
    monkeypatch.setattr(scanner, "_fetch_earnings_map", Mock(side_effect=AssertionError("unnecessary earnings fetch")))
    result = scanner.scan_options(profile="simple", max_capital=10000)
    assert set(queried) == {"SPY", "QQQ", "IWM"}
    assert len(result) == 3 and all(item["strike"] == 90 for item in result)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(cache, "_store", {})
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


def test_empty_scan_never_relaxes_and_remains_empty_in_cache(client, monkeypatch):
    scan = Mock(return_value=[])
    monkeypatch.setattr(route, "scan_options", scan)
    first = client.get("/api/scan").json()
    second = client.get("/api/scan").json()
    assert first["data"] == second["data"] == []
    assert first["noTrade"] and not first["relaxed"] and not first["bestEffort"]
    assert second["cached"]
    scan.assert_called_once()
    assert scan.call_args.kwargs["relaxed"] is False


@pytest.mark.parametrize("params", [
    "strategies=unknown", "strategies=", "dte_min=45&dte_max=30", "dte_max=-1",
    "profile=simple&relaxed=true", "profile=simple&strategies=sell_call",
    "profile=simple&dte_max=20", "profile=invalid", "fee_per_contract=-1",
    "slippage_per_share=nan", "max_capital=inf", "profile=simple&min_iv_rank=20",
])
def test_invalid_scan_requests_do_not_fetch_market_data(client, monkeypatch, params):
    scan = Mock()
    monkeypatch.setattr(route, "scan_options", scan)
    assert client.get(f"/api/scan?{params}").status_code == 422
    scan.assert_not_called()


def test_cache_separates_profile_costs_and_cash_budget(client, monkeypatch):
    scan = Mock(return_value=[])
    monkeypatch.setattr(route, "scan_options", scan)
    for params in ["", "profile=simple", "profile=simple&fee_per_contract=1",
                   "profile=simple&slippage_per_share=0.1", "profile=simple&max_capital=1000"]:
        assert client.get(f"/api/scan?{params}").status_code == 200
    assert scan.call_count == 5
    client.get("/api/scan?profile=simple&max_capital=1000")
    assert scan.call_count == 5


def test_warmup_and_http_use_the_same_default_cache(client, monkeypatch):
    from services.warmup import _DEFAULTS
    scan = Mock(return_value=[])
    monkeypatch.setattr(route, "scan_options", scan)
    route.scan(force_refresh=True, **_DEFAULTS)
    response = client.get("/api/scan?profile=simple&dte_min=30&dte_max=45")
    assert response.json()["cached"] is True
    scan.assert_called_once()


@pytest.mark.parametrize("strategy,expected", [("sell_put", 1), ("buy_put", 1.05)])
def test_advanced_quotes_use_trade_side_and_calendar_days(strategy, expected):
    result = scanner._process_row(quote(), "SPY", 100, history(), .3, 90, 90,
                                   strategy, "2026-11-19", datetime(2026, 10, 20, 15),
                                   best_effort=True)
    assert result["premium"] == expected
    assert result["dte"] == 30
