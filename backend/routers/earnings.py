"""
/api/earnings  —  财报日历 + 预期波动幅度
"""
import math

import yfinance as yf
from fastapi import APIRouter

from services import cache as cache_svc
from services.scanner import TICKERS

router = APIRouter()


@router.get("/api/earnings")
def get_earnings(force_refresh: bool = False):
    cached = cache_svc.get("earnings", ttl_seconds=7200)
    if not force_refresh and cached:
        return {"data": cached, "cached": True}

    results = []
    for symbol in TICKERS:
        try:
            ticker = yf.Ticker(symbol)
            cal = ticker.calendar

            if not cal or "Earnings Date" not in cal or not cal["Earnings Date"]:
                continue

            next_earnings = cal["Earnings Date"][0]
            earnings_date_str = next_earnings.strftime("%Y-%m-%d")

            # 预期波动幅度（用当前 ATM IV 估算）
            history = ticker.history(period="1y")
            if history.empty:
                continue
            current_price = float(history["Close"].iloc[-1])

            # 到财报还有多少天
            from datetime import datetime
            today = datetime.now()
            days_to_earnings = (next_earnings.replace(tzinfo=None) - today).days

            # 尝试获取接近财报日的期权 IV
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

            # Fallback：用历史波动率
            if expected_move_pct is None:
                daily_ret = history["Close"].pct_change().dropna()
                hv = float(daily_ret.std() * math.sqrt(252))
                move = current_price * hv * math.sqrt(max(days_to_earnings, 1) / 365)
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
