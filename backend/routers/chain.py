"""
/api/option-chain/{symbol}  —  实时期权链（策略构建 Tab 使用）
"""
import math
from datetime import datetime

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from services.greeks import calc_black_scholes, calc_expected_move, calc_iv_rank

router = APIRouter()


@router.get("/api/option-chain/{symbol}")
def get_option_chain(
    symbol: str,
    strategy: str = Query(default="sell_put"),
):
    ticker = yf.Ticker(symbol.upper())
    history = ticker.history(period="1y")

    if history.empty:
        raise HTTPException(status_code=404, detail=f"找不到 {symbol} 的历史数据")

    current_price = float(history["Close"].iloc[-1])
    daily_ret = history["Close"].pct_change().dropna()
    hist_vol = float(daily_ret.std() * math.sqrt(252))
    sma50 = float(history["Close"].tail(50).mean())

    exp_dates = ticker.options
    today = datetime.now()
    bs_type = "put" if "put" in strategy else "call"
    is_put = bs_type == "put"

    chain_by_date = []

    for date_str in exp_dates[:8]:   # 最多展示 8 个到期日
        dte = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
        if dte <= 0:
            continue

        try:
            chain = ticker.option_chain(date_str)
            rows = chain.puts if is_put else chain.calls
        except Exception:
            continue

        options = []
        for _, row in rows.iterrows():
            strike = float(row["strike"])
            premium = float(row["lastPrice"]) if not pd.isna(row["lastPrice"]) else 0.0
            bid = float(row.get("bid", 0) or 0)
            ask = float(row.get("ask", 0) or 0)
            iv = float(row["impliedVolatility"]) if not pd.isna(row["impliedVolatility"]) else 0.0
            volume = int(row.get("volume", 0) or 0)
            oi = int(row.get("openInterest", 0) or 0)

            if premium <= 0 or iv <= 0:
                continue

            greeks = calc_black_scholes(current_price, strike, dte, iv, bs_type)
            exp_move = calc_expected_move(current_price, iv, dte)
            iv_rank = calc_iv_rank(history, iv)

            distance_pct = (
                round((current_price - strike) / current_price * 100, 1) if is_put
                else round((strike - current_price) / current_price * 100, 1)
            )
            break_even = (
                round(strike - premium, 2) if strategy in ("sell_put", "buy_put")
                else round(strike + premium, 2)
            )

            options.append({
                "strike": strike,
                "premium": round(premium, 2),
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "volume": volume,
                "openInterest": oi,
                "impliedVolatility": round(iv * 100, 1),
                "ivRank": iv_rank,
                "distancePct": distance_pct,
                "breakEven": break_even,
                "expectedMoveUpper": exp_move["upper"],
                "expectedMoveLower": exp_move["lower"],
                "expectedMovePct": exp_move["move_pct"],
                "delta": greeks["delta"] if greeks else None,
                "gamma": greeks["gamma"] if greeks else None,
                "thetaPerDay": round(greeks["theta_day"] * 100, 2) if greeks else None,
                "vegaPerPct": round(greeks["vega_1pct"] * 100, 2) if greeks else None,
                "popTheoretical": greeks["pop"] if greeks else None,
                "inTheMoney": bool(row.get("inTheMoney", False)),
            })

        chain_by_date.append({
            "expirationDate": date_str,
            "dte": dte,
            "options": options,
        })

    return {
        "symbol": symbol.upper(),
        "currentPrice": round(current_price, 2),
        "histVolatility": round(hist_vol * 100, 1),
        "sma50": round(sma50, 2),
        "aboveSma50": current_price >= sma50,
        "strategy": strategy,
        "chain": chain_by_date,
    }
