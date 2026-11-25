"""Tradier 数据源解析与"数据源不可用"判定，用固定响应代替真实请求。"""
from datetime import datetime, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from services import chains, scanner, spreads, tradier


@pytest.fixture
def api(monkeypatch):
    for k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TRADIER_TOKEN", "test")
    for name in ("_exp_cache", "_chain_cache", "_quote_cache"):
        monkeypatch.setattr(tradier, name, {})
    today = datetime.now(ZoneInfo("America/New_York")).date()
    dates = [(today + timedelta(days=d)).isoformat() for d in (3, 10, 17, 24, 31, 38, 45, 80)]
    calls: list[tuple[str, dict]] = []

    def get(path, params):
        calls.append((path, params))
        if path.endswith("expirations"):
            return {"expirations": {"date": dates}}
        if path.endswith("chains"):
            return {"options": {"option": [
                {"strike": 95, "option_type": "put", "bid": 1.0, "ask": 1.1, "last": 1.05,
                 "volume": 10, "open_interest": 500, "greeks": {"mid_iv": 0.25, "smv_vol": 0.3}},
                {"strike": 90, "option_type": "put", "bid": 0.5, "ask": 0.6, "last": None,
                 "volume": None, "open_interest": 200, "greeks": None},
                {"strike": 105, "option_type": "call", "bid": 1.2, "ask": 1.3, "last": 1.25,
                 "volume": 5, "open_interest": 300, "greeks": {"mid_iv": 0, "smv_vol": 0.28}},
            ]}}
        if path.endswith("quotes"):
            return {"quotes": {"quote": {"symbol": "SPY", "last": 100.5, "prevclose": 99.0,
                                         "change_percentage": 1.516}}}
        return None

    monkeypatch.setattr(tradier, "_get", get)
    return dates, calls


def test_fetch_maps_tradier_chain_to_scanner_columns(api):
    dates, calls = api
    data = tradier.fetch("spy", 7, 60, 4)
    assert data["current_price"] == 100.5 and data["change_pct"] == 1.52
    assert list(data["chains"]) == [dates[1], dates[2], dates[4], dates[6]]
    puts = data["chains"][dates[1]]["puts"]
    assert puts["strike"].tolist() == [90, 95]
    assert puts.iloc[1]["impliedVolatility"] == 0.25 and puts.iloc[1]["openInterest"] == 500
    assert puts.iloc[0]["impliedVolatility"] == 0 and puts.iloc[0]["lastPrice"] == 0
    assert data["chains"][dates[1]]["calls"].iloc[0]["impliedVolatility"] == 0.28
    assert sum(p.endswith("chains") for p, _ in calls) == 4


def test_expirations_and_chains_are_cached(api):
    _, calls = api
    tradier.fetch("SPY", 7, 60, 4)
    n = len(calls)
    tradier.fetch("SPY", 7, 60, 4)
    assert len(calls) == n


def test_without_token_tradier_is_skipped(monkeypatch):
    for k in ("TRADIER_TOKEN", "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(tradier, "_get", Mock(side_effect=AssertionError("no request")))
    monkeypatch.setattr(chains.cboe, "fetch", lambda _: None)
    assert chains.fetch("SPY", 7, 60, 4) == (None, None)
    tradier.prefetch_quotes(["SPY"])


def test_chain_source_prefers_tradier(api, monkeypatch):
    monkeypatch.setattr(chains.cboe, "fetch", Mock(side_effect=AssertionError("cboe not needed")))
    data, source = chains.fetch("SPY", 7, 60, 4)
    assert source == "tradier" and data["chains"]


def test_scan_reports_unavailable_when_no_ticker_has_data(monkeypatch):
    monkeypatch.setattr(scanner, "_process_ticker", lambda *a: None)
    with pytest.raises(chains.DataSourceUnavailable):
        scanner.scan_options(profile="simple")


def test_scan_with_data_but_no_matches_is_empty_not_error(monkeypatch):
    monkeypatch.setattr(scanner, "_process_ticker", lambda sym, *a: [] if sym == "SPY" else None)
    assert scanner.scan_options(profile="simple") == []


def test_spreads_report_unavailable_when_no_chains(monkeypatch):
    monkeypatch.setattr(spreads, "_build_for_ticker", lambda *a: None)
    with pytest.raises(chains.DataSourceUnavailable):
        spreads.scan_spreads()
