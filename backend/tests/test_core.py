"""核心纯函数单测：评分/筛选/胜率/Greeks/CBOE 解析。无网络依赖。"""
from datetime import date, datetime

import pandas as pd

from services.cboe import _parse_osi
from services.greeks import calc_black_scholes, calc_p50
from services.scanner import _liquidity_score, _calc_empirical_win_rate, _earnings_days_from_calendar


# ── CBOE OSI 期权代码解析 ──
def test_parse_osi_valid():
    assert _parse_osi("AAPL260608P00250000", "AAPL") == ("2026-06-08", "P", 250.0)
    assert _parse_osi("SPY261218C00500000", "SPY") == ("2026-12-18", "C", 500.0)


def test_parse_osi_invalid():
    assert _parse_osi("GARBAGE", "AAPL") is None
    assert _parse_osi("AAPL260608X00250000", "AAPL") is None  # 非 C/P


# ── 流动性评分 ──
def test_liquidity_score_bounds():
    assert _liquidity_score(1000, 1000, 1) == 10   # 满分
    assert _liquidity_score(0, 0, 100) == 0        # 零分
    assert 0 <= _liquidity_score(150, 300, 8) <= 10


# ── Black-Scholes Greeks ──
def test_bs_atm_call_delta():
    g = calc_black_scholes(100, 100, 30, 0.30, "call")
    assert g is not None
    assert 0.50 < g["delta"] < 0.65   # ATM call 略高于 0.5
    assert g["gamma"] > 0
    assert 0 <= g["pop"] <= 100


def test_bs_atm_put_delta_negative():
    g = calc_black_scholes(100, 100, 30, 0.30, "put")
    assert g is not None
    assert -0.50 < g["delta"] < -0.35


def test_bs_invalid_returns_none():
    assert calc_black_scholes(100, 100, 0, 0.30, "call") is None   # dte=0
    assert calc_black_scholes(100, 100, 30, 0, "call") is None     # iv=0


def test_p50_sell_put_in_range():
    p = calc_p50(100, 95, 1.5, 30, 0.30, "sell_put")
    assert p is not None and 0 <= p <= 100


# ── 经验胜率 ──
def _flat_history(price: float, n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({"Close": price, "High": price, "Low": price}, index=idx)


def test_win_rate_flat_history_never_breaches():
    # 价格恒定 100，行权价 90：从不跌破 → 胜率 100%
    stats = _calc_empirical_win_rate(_flat_history(100), 30, 100, 90)
    assert stats["win_rate"] == 1.0
    assert stats["total_windows"] > 0 and stats["safe_windows"] == stats["total_windows"]


def test_win_rate_strike_above_price_is_zero():
    # 行权价 110 高于现价 100：required_drop <= 0 → 0%
    stats = _calc_empirical_win_rate(_flat_history(100), 30, 100, 110)
    assert stats["win_rate"] == 0.0


def test_win_rate_empty_history():
    stats = _calc_empirical_win_rate(pd.DataFrame(), 30, 100, 90)
    assert stats["win_rate"] is None and stats["total_windows"] == 0


def test_win_rate_reports_independent_sample_smaller_than_total():
    stats = _calc_empirical_win_rate(_flat_history(100), 30, 100, 90)
    # 30 日 DTE ≈ 20 个交易日步长，重叠窗口数应明显多于独立窗口数
    assert stats["independent_windows"] < stats["total_windows"]
    assert stats["independent_windows"] > 0


def test_independent_sample_count_matches_stride():
    from services.scanner import _independent_sample_count
    windows = [(None, 0, 0, 0)] * 100
    assert _independent_sample_count(windows, trading_dte=10) == 10
    assert _independent_sample_count([], trading_dte=10) == 0
    assert _independent_sample_count(windows, trading_dte=1) == 100


# ── 财报日期解析（yfinance .calendar 返回 date 对象，不能直接跟 datetime 相减）──

def test_earnings_days_from_calendar_handles_plain_date():
    today = datetime(2026, 7, 27)
    cal = {"Earnings Date": [date(2026, 7, 30)]}
    assert _earnings_days_from_calendar(cal, today) == 3


def test_earnings_days_from_calendar_handles_tz_aware_datetime():
    import datetime as dt_mod
    today = datetime(2026, 7, 27)
    aware = datetime(2026, 8, 5, tzinfo=dt_mod.timezone.utc)
    cal = {"Earnings Date": [aware]}
    assert _earnings_days_from_calendar(cal, today) == 9


def test_earnings_days_from_calendar_handles_string_date():
    today = datetime(2026, 7, 27)
    cal = {"Earnings Date": ["2026-07-31"]}
    assert _earnings_days_from_calendar(cal, today) == 4


def test_earnings_days_from_calendar_none_when_no_dates():
    today = datetime(2026, 7, 27)
    assert _earnings_days_from_calendar({}, today) is None
    assert _earnings_days_from_calendar({"Earnings Date": []}, today) is None
