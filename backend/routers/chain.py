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


def _safe_float(val, default=0.0) -> float:
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return default
        v = float(val)
        return default if math.isnan(v) else v
    except Exception:
        return default


def _safe_int(val, default=0) -> int:
    try:
        if val is None:
            return default
        f = float(val)
        return default if math.isnan(f) else int(f)
    except Exception:
        return default


@router.get("/api/option-chain/{symbol}")
def get_option_chain(
    symbol: str,
    strategy: str = Query(default="sell_put"),
):
    try:
        ticker = yf.Ticker(symbol.upper())
        history = ticker.history(period="1y")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取 {symbol} 数据失败: {e}")

    if history.empty:
        raise HTTPException(status_code=404, detail=f"找不到 {symbol} 的历史数据")

    current_price = _safe_float(history["Close"].iloc[-1])
    daily_ret = history["Close"].pct_change().dropna()
    hist_vol_raw = daily_ret.std() * math.sqrt(252)
    hist_vol = _safe_float(hist_vol_raw, default=0.0)
    sma50 = _safe_float(history["Close"].tail(50).mean())

    try:
        exp_dates = ticker.options or []
    except Exception:
        exp_dates = []

    today = datetime.now()
    bs_type = "put" if "put" in strategy else "call"
    is_put = bs_type == "put"

    chain_by_date = []

    for date_str in exp_dates[:8]:
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
            try:
                strike  = _safe_float(row.get("strike"))
                bid     = _safe_float(row.get("bid"))
                ask     = _safe_float(row.get("ask"))
                last    = _safe_float(row.get("lastPrice"))
                iv_raw  = _safe_float(row.get("impliedVolatility"))
                volume  = _safe_int(row.get("volume"))
                oi      = _safe_int(row.get("openInterest"))

                # 用 mid 价格兜底（近期无成交但 bid/ask 有效）
                mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
                premium = last if last > 0 else mid
                if premium <= 0:
                    continue

                # IV：yfinance 原始值优先；不可靠时用历史波动率估算
                iv_valid = iv_raw > 0.005  # <0.5% 视为无效
                iv = iv_raw if iv_valid else hist_vol
                iv_estimated = not iv_valid  # 前端用于标注"估算"

                greeks   = calc_black_scholes(current_price, strike, dte, iv, bs_type)
                exp_move = calc_expected_move(current_price, iv, dte)
                iv_rank  = calc_iv_rank(history, iv)

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
                    "premium": round(premium, 4),
                    "bid": round(bid, 2),
                    "ask": round(ask, 2),
                    "volume": volume,
                    "openInterest": oi,
                    "impliedVolatility": round(iv * 100, 1),
                    "ivEstimated": iv_estimated,
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
            except Exception:
                continue

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
