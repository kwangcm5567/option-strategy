"""
/api/earnings  —  财报日历 + 预期波动幅度
主数据源：Financial Modeling Prep (FMP)
Fallback：yfinance earnings_dates
"""
import math
from datetime import datetime

import pandas as pd
import yfinance as yf
from fastapi import APIRouter

from services import cache as cache_svc
from services.scanner import TICKERS

router = APIRouter()

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")


def _fetch_fmp_earnings() -> dict[str, str]:
    """从 FMP 拉取未来 90 天财报日历，返回 {symbol: date_str}。"""
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


def _get_next_earnings(ticker) -> datetime | None:
    """尝试多种方式获取下一个财报日期。"""
    # 方法 1: ticker.calendar
    try:
        cal = ticker.calendar
        if cal and "Earnings Date" in cal and cal["Earnings Date"]:
            return cal["Earnings Date"][0]
    except Exception:
        pass

    # 方法 2: ticker.earnings_dates（yfinance 0.2.x 新接口）
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

    fmp_map = _fetch_fmp_earnings()
    results = []
    today = datetime.now()

    for symbol in TICKERS:
        try:
            ticker = yf.Ticker(symbol)
            next_earnings = _get_next_earnings(ticker)

            if next_earnings is None:
                continue

            next_earnings_naive = next_earnings.replace(tzinfo=None) if hasattr(next_earnings, 'tzinfo') else next_earnings
            earnings_date_str = next_earnings_naive.strftime("%Y-%m-%d")
            days_to_earnings = (next_earnings_naive - today).days

            history = ticker.history(period="1y")
            if history.empty:
                continue
            current_price = float(history["Close"].iloc[-1])

            expected_move_pct = None
            expected_move_dollar = None
            try:
                exp_dates = ticker.options
                for date_str in exp_dates:
                    dte = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
                    if 5 <= dte <= 45:
                        chain = ticker.option_chain(date_str)
                        atm = chain.puts[
                            (chain.puts["strike"] >= current_price * 0.97) &
                            (chain.puts["strike"] <= current_price * 1.03)
                        ]
                        if not atm.empty:
                            iv = float(atm["impliedVolatility"].median())
                            if iv > 0:
                                move = current_price * iv * math.sqrt(max(dte, 1) / 365)
                                expected_move_pct = round(move / current_price * 100, 1)
                                expected_move_dollar = round(move, 2)
                            break
            except Exception:
                pass

            if expected_move_pct is None:
                daily_ret = history["Close"].pct_change().dropna()
                hv = float(daily_ret.std() * math.sqrt(252))
                move = current_price * hv * math.sqrt(max(abs(days_to_earnings), 1) / 365)
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
