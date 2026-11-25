"""Alpaca 数据源解析，用固定响应代替真实请求。"""
from datetime import datetime, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from services import alpaca, chains


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    for name in ("_contract_cache", "_chain_cache", "_quote_cache"):
        monkeypatch.setattr(alpaca, name, {})
    monkeypatch.setattr(alpaca, "_trading_base", [])
    today = datetime.now(ZoneInfo("America/New_York")).date()
    dates = [(today + timedelta(days=d)).isoformat() for d in (10, 17, 24, 31, 38, 45)]
    yymmdd = {d: d[2:4] + d[5:7] + d[8:10] for d in dates}
    calls: list[tuple[str, dict]] = []

    def request(url, params):
        calls.append((url, params))
        if url.endswith("/v2/stocks/snapshots"):
            return 200, {"SPY": {"latestTrade": {"p": 100.0}, "prevDailyBar": {"c": 98.0}}}
        if "paper-api" in url:
            return 403, None
        if url.endswith("/v2/options/contracts"):
            page = [{"symbol": f"SPY{yymmdd[d]}P00095000", "expiration_date": d, "open_interest": "700"}
                    for d in dates]
            if params.get("page_token"):
                return 200, {"option_contracts": page[3:], "next_page_token": None}
            return 200, {"option_contracts": page[:3], "next_page_token": "p2"}
        if "/options/snapshots/" in url:
            d = yymmdd[params["expiration_date"]]
            return 200, {"snapshots": {
                f"SPY{d}P00095000": {"latestQuote": {"bp": 1.0, "ap": 1.1}, "latestTrade": {"p": 1.05},
                                     "impliedVolatility": 0.24, "dailyBar": {"v": 12}},
                f"SPY{d}P00090000": {"latestQuote": {"bp": 0.5, "ap": 0.6}},
                f"SPY{d}C00105000": {"latestQuote": {"bp": 1.2, "ap": 1.3}, "impliedVolatility": 0.2},
            }, "next_page_token": None}
        return 404, None

    monkeypatch.setattr(alpaca, "_request", request)
    return dates, calls


def test_fetch_maps_snapshots_and_open_interest(api):
    dates, calls = api
    data = alpaca.fetch("spy", 7, 60, 4)
    assert data["current_price"] == 100.0 and data["change_pct"] == 2.04
    assert list(data["chains"]) == [dates[0], dates[1], dates[3], dates[5]]
    puts = data["chains"][dates[0]]["puts"]
    assert puts["strike"].tolist() == [90, 95]
    assert puts.iloc[1][["bid", "ask", "impliedVolatility", "volume", "openInterest"]].tolist() == [1.0, 1.1, 0.24, 12, 700]
    assert puts.iloc[0]["openInterest"] == 0 and puts.iloc[0]["impliedVolatility"] == 0
    assert data["chains"][dates[0]]["calls"].iloc[0]["strike"] == 105
    assert alpaca._trading_base == ["https://api.alpaca.markets"]


def test_contracts_and_chains_are_cached(api):
    _, calls = api
    alpaca.fetch("SPY", 7, 60, 4)
    n = len(calls)
    alpaca.fetch("SPY", 7, 60, 4)
    assert len(calls) == n


def test_chain_source_prefers_alpaca(api, monkeypatch):
    monkeypatch.setattr(chains.tradier, "fetch", Mock(side_effect=AssertionError("tradier not needed")))
    data, source = chains.fetch("SPY", 7, 60, 4)
    assert source == "alpaca" and data["chains"]


def test_without_keys_alpaca_is_skipped(monkeypatch):
    for k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(alpaca, "_request", Mock(side_effect=AssertionError("no request")))
    assert alpaca.fetch("SPY", 7, 60, 4) is None
    alpaca.prefetch_quotes(["SPY"])
