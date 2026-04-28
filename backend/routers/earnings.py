"""
/api/earnings  —  财报日历 + 预期波动幅度
主数据源：Financial Modeling Prep (FMP)  — 2 次 API call 搞定全部 20 只股票
Fallback：yfinance earnings_dates（仅在未配置 FMP_API_KEY 时使用）
"""
import math
import os
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf
from fastapi import APIRouter

from services import cache as cache_svc
from services.scanner import TICKERS

router = APIRouter()

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")


def _fetch_fmp_earnings() -> dict[str, str]:
    """从 FMP 拉取未来 90 天财报日历，返回 {symbol: date_str}。1 次 call 覆盖所有标的。"""
    if not FMP_API_KEY:
        return {}
    try:
        today = datetime.now()
        end = today + timedelta(days=90)
        url = (
            "https://financialmodelingprep.com/api/v3/earning_calendar"
            f"?from={today.strftime('%Y-%m-%d')}"
            f"&to={end.strftime('%Y-%m-%d')}"
            f"&apikey={FMP_API_KEY}"
        )
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return {}
        result: dict[str, str] = {}
        for item in resp.json():
            sym = item.get("symbol", "").upper()
            date = item.get("date", "")
            if sym and date and sym not in result:
                result[sym] = date
        return result
    except Exception:
        return {}


def _fetch_fmp_quotes(symbols: list[str]) -> dict[str, dict]:
    """批量获取行情（price / yearHigh / yearLow），1 次 call 覆盖所有标的。"""
    if not FMP_API_KEY:
        return {}
    try:
        joined = ",".join(symbols)
        url = f"https://financialmodelingprep.com/api/v3/quote/{joined}?apikey={FMP_API_KEY}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return {}
        result: dict[str, dict] = {}
        for item in resp.json():
            sym = item.get("symbol", "").upper()
            price = item.get("price")
            if sym and price:
                result[sym] = {
                    "price": float(price),
                    "yearHigh": float(item.get("yearHigh") or 0),
                    "yearLow": float(item.get("yearLow") or 0),
                }
        return result
    except Exception:
        return {}


def _parkinson_hv(year_high: float, year_low: float) -> float:
    """Parkinson 高低价估算年化历史波动率。"""
    if year_high > 0 and year_low > 0 and year_high > year_low:
        return math.log(year_high / year_low) / math.sqrt(4 * math.log(2))
    return 0.25  # 兜底：25% 年化波动率


def _get_next_earnings_yf(ticker) -> datetime | None:
    """yfinance fallback：先试 calendar，再试 earnings_dates。"""
    try:
        cal = ticker.calendar
        if cal and "Earnings Date" in cal and cal["Earnings Date"]:
            return cal["Earnings Date"][0]
    except Exception:
        pass
    try:
        eds = ticker.earnings_dates
        if eds is not None and not eds.empty:
            now_tz = pd.Timestamp.now(tz=eds.index.tz)
            future = eds[eds.index > now_tz]
            if not future.empty:
                return future.index.min().to_pydatetime()
    except Exception:
        pass
    return None


@router.get("/api/earnings")
def get_earnings(force_refresh: bool = False):
    cached = cache_svc.get("earnings", ttl_seconds=7200)
    if not force_refresh and cached:
        return {"data": cached, "cached": True}

    fmp_dates = _fetch_fmp_earnings()
    fmp_quotes = _fetch_fmp_quotes(TICKERS)

    results = []
    today = datetime.now()

    for symbol in TICKERS:
        try:
            # ── 财报日期 ──
            if symbol in fmp_dates:
                earnings_date_str = fmp_dates[symbol]
                next_earnings_naive = datetime.strptime(earnings_date_str, "%Y-%m-%d")
            else:
                # FMP 没有时才走 yfinance
                yf_ticker = yf.Ticker(symbol)
                next_dt = _get_next_earnings_yf(yf_ticker)
                if next_dt is None:
                    continue
                next_earnings_naive = next_dt.replace(tzinfo=None)
                earnings_date_str = next_earnings_naive.strftime("%Y-%m-%d")

            days_to_earnings = (next_earnings_naive - today).days

            # ── 当前价格 ──
            quote = fmp_quotes.get(symbol)
            if quote:
                current_price = quote["price"]
                hv = _parkinson_hv(quote["yearHigh"], quote["yearLow"])
            else:
                # FMP 没有时才走 yfinance
                try:
                    hist = yf.Ticker(symbol).history(period="5d")
                    if hist.empty:
                        continue
                    current_price = float(hist["Close"].iloc[-1])
                    hv = 0.25
                except Exception:
                    continue

            # ── 预期波动幅度（基于年化 HV + DTE） ──
            dte = max(abs(days_to_earnings), 1)
            move = current_price * hv * math.sqrt(dte / 365)
            expected_move_pct = round(move / current_price * 100, 1)
            expected_move_dollar = round(move, 2)

            results.append({
                "symbol": symbol,
                "earningsDate": earnings_date_str,
                "daysAway": days_to_earnings,
                "currentPrice": round(current_price, 2),
                "expectedMovePct": expected_move_pct,
                "expectedMoveDollar": expected_move_dollar,
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["earningsDate"])
    cache_svc.set("earnings", results)
    return {"data": results, "cached": False}
