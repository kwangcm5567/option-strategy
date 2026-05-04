"""
/api/covered-call/{symbol}     — Covered Call 建议（持有股票时卖出 Call）
/api/protective-put/{symbol}   — Protective Put 建议（持有股票时买入 Put 对冲）
"""
import math
from datetime import datetime

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from services.greeks import calc_black_scholes

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


def _annualized_return(premium_per_share: float, reference_price: float, dte: int) -> float:
    """权利金年化收益率（%）"""
    if reference_price <= 0 or dte <= 0:
        return 0.0
    return round(premium_per_share / reference_price / dte * 365 * 100, 2)


@router.get("/api/covered-call/{symbol}")
def covered_call_suggestions(
    symbol: str,
    shares: int = Query(default=100, ge=1),
    cost_basis: float = Query(default=0.0, ge=0),
):
    """
    返回针对持有股票的 Covered Call 建议列表。
    目标行权价：当前价上方 2%、5%、10%、15%、20%（按可用期权链选最近匹配）。
    """
    sym = symbol.upper()
    try:
        ticker = yf.Ticker(sym)
        history = ticker.history(period="3mo")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取 {sym} 数据失败: {e}")

    if history.empty:
        raise HTTPException(status_code=404, detail=f"找不到 {sym} 的历史数据")

    current_price = _safe_float(history["Close"].iloc[-1])
    if current_price <= 0:
        raise HTTPException(status_code=502, detail="无法获取当前价格")

    daily_ret = history["Close"].pct_change().dropna()
    hist_vol = _safe_float(daily_ret.std() * math.sqrt(252), default=0.30)

    try:
        exp_dates = ticker.options or []
    except Exception:
        exp_dates = []

    today = datetime.now()
    TARGET_OTM = [0.02, 0.05, 0.10, 0.15, 0.20]
    suggestions = []

    for date_str in exp_dates[:6]:
        dte = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
        if dte < 7 or dte > 90:
            continue

        try:
            chain = ticker.option_chain(date_str)
            calls = chain.calls
        except Exception:
            continue

        used_targets = set()
        for target_otm in TARGET_OTM:
            target_strike = current_price * (1 + target_otm)

            # 找最接近目标行权价的 call
            if calls.empty:
                continue
            calls_copy = calls.copy()
            calls_copy["_dist"] = abs(calls_copy["strike"] - target_strike)
            best = calls_copy.nsmallest(1, "_dist").iloc[0]

            strike = _safe_float(best.get("strike"))
            premium = _safe_float(best.get("lastPrice"))
            bid = _safe_float(best.get("bid"))
            ask = _safe_float(best.get("ask"))
            iv = _safe_float(best.get("impliedVolatility"))
            volume = _safe_int(best.get("volume"))
            oi = _safe_int(best.get("openInterest"))

            if premium <= 0 or strike <= current_price * 0.98:
                continue

            # 去重（同一行权价+到期日组合只收录一次）
            key = (date_str, round(strike, 2))
            if key in used_targets:
                continue
            used_targets.add(key)

            actual_otm_pct = (strike - current_price) / current_price * 100
            annualized_on_price = _annualized_return(premium, current_price, dte)
            annualized_on_cost = _annualized_return(premium, cost_basis, dte) if cost_basis > 0 else None

            # 若被行权：资本增值 + 权利金 总收益
            cap_gain = max(0.0, strike - (cost_basis if cost_basis > 0 else current_price))
            total_return_if_called = round((cap_gain + premium) * shares, 2)
            total_return_pct = round((cap_gain + premium) / (cost_basis if cost_basis > 0 else current_price) * 100, 2)

            bs = calc_black_scholes(current_price, strike, dte, iv if iv > 0 else hist_vol, "call")

            suggestions.append({
                "expirationDate": date_str,
                "dte": dte,
                "strike": round(strike, 2),
                "premium": round(premium, 4),
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "volume": volume,
                "openInterest": oi,
                "impliedVolatility": round(iv * 100, 1) if iv > 0 else None,
                "otmPct": round(actual_otm_pct, 1),
                "annualizedReturnOnPrice": annualized_on_price,
                "annualizedReturnOnCost": annualized_on_cost,
                "premiumPerContract": round(premium * 100, 2),
                "totalPremiumIncome": round(premium * 100 * (shares // 100 or 1), 2),
                "totalReturnIfCalled": total_return_if_called,
                "totalReturnIfCalledPct": total_return_pct,
                "delta": bs.get("delta") if bs else None,
                "theta": bs.get("theta_day") if bs else None,
            })

        if len(suggestions) >= 12:
            break

    suggestions.sort(key=lambda x: (x["dte"], x["otmPct"]))

    return {
        "symbol": sym,
        "currentPrice": round(current_price, 2),
        "histVolatility": round(hist_vol * 100, 1),
        "shares": shares,
        "costBasis": cost_basis,
        "suggestions": suggestions,
    }


@router.get("/api/protective-put/{symbol}")
def protective_put_suggestions(
    symbol: str,
    shares: int = Query(default=100, ge=1),
    cost_basis: float = Query(default=0.0, ge=0),
):
    """
    返回针对持有股票的 Protective Put 建议列表（买入 Put 对冲下行风险）。
    目标行权价：当前价下方 5%、10%、15%、20%。
    """
    sym = symbol.upper()
    try:
        ticker = yf.Ticker(sym)
        history = ticker.history(period="3mo")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取 {sym} 数据失败: {e}")

    if history.empty:
        raise HTTPException(status_code=404, detail=f"找不到 {sym} 的历史数据")

    current_price = _safe_float(history["Close"].iloc[-1])
    if current_price <= 0:
        raise HTTPException(status_code=502, detail="无法获取当前价格")

    daily_ret = history["Close"].pct_change().dropna()
    hist_vol = _safe_float(daily_ret.std() * math.sqrt(252), default=0.30)

    try:
        exp_dates = ticker.options or []
    except Exception:
        exp_dates = []

    today = datetime.now()
    TARGET_OTM = [0.05, 0.10, 0.15, 0.20]
    suggestions = []

    for date_str in exp_dates[:6]:
        dte = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
        if dte < 14 or dte > 180:
            continue

        try:
            chain = ticker.option_chain(date_str)
            puts = chain.puts
        except Exception:
            continue

        used_targets = set()
        for target_otm in TARGET_OTM:
            target_strike = current_price * (1 - target_otm)

            if puts.empty:
                continue
            puts_copy = puts.copy()
            puts_copy["_dist"] = abs(puts_copy["strike"] - target_strike)
            best = puts_copy.nsmallest(1, "_dist").iloc[0]

            strike = _safe_float(best.get("strike"))
            premium = _safe_float(best.get("lastPrice"))
            bid = _safe_float(best.get("bid"))
            ask = _safe_float(best.get("ask"))
            iv = _safe_float(best.get("impliedVolatility"))
            volume = _safe_int(best.get("volume"))
            oi = _safe_int(best.get("openInterest"))

            if premium <= 0 or strike >= current_price * 1.02:
                continue

            key = (date_str, round(strike, 2))
            if key in used_targets:
                continue
            used_targets.add(key)

            actual_otm_pct = (current_price - strike) / current_price * 100
            contracts = shares // 100 or 1
            total_cost = round(premium * 100 * contracts, 2)

            # 年化保险成本（占当前股价的百分比）
            annualized_cost_pct = round(premium / current_price / dte * 365 * 100, 2)

            # 最大损失（若股价跌到 0）
            max_loss_without_put = round(current_price * shares, 2)
            # 有了 Put：最大损失 = (current - strike) * shares + 权利金成本
            protected_max_loss = round((current_price - strike) * shares + total_cost, 2)

            # 盈亏平衡（股价下跌多少才开始保护赚钱）
            put_break_even = round(strike - premium, 2)

            # 保护生效的价格区间
            protection_floor = round(strike / current_price * 100, 1)  # 保护后最大跌幅是 (1 - floor/100)%

            bs = calc_black_scholes(current_price, strike, dte, iv if iv > 0 else hist_vol, "put")

            suggestions.append({
                "expirationDate": date_str,
                "dte": dte,
                "strike": round(strike, 2),
                "premium": round(premium, 4),
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "volume": volume,
                "openInterest": oi,
                "impliedVolatility": round(iv * 100, 1) if iv > 0 else None,
                "otmPct": round(actual_otm_pct, 1),
                "annualizedCostPct": annualized_cost_pct,
                "totalCost": total_cost,
                "putBreakEven": put_break_even,
                "protectionFloorPct": protection_floor,
                "protectedMaxLoss": protected_max_loss,
                "delta": bs.get("delta") if bs else None,
            })

        if len(suggestions) >= 10:
            break

    suggestions.sort(key=lambda x: (x["dte"], x["otmPct"]))

    return {
        "symbol": sym,
        "currentPrice": round(current_price, 2),
        "histVolatility": round(hist_vol * 100, 1),
        "shares": shares,
        "costBasis": cost_basis,
        "suggestions": suggestions,
    }
