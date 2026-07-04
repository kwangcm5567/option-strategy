"""
多腿价差扫描：垂直价差（信用/借记）、Iron Condor、跨式/宽跨。

在现有 CBOE 期权链上组合两腿/四腿结构，计算净权利金、最大盈亏、
盈亏平衡、信用/宽度比、组合 Greeks 和 POP，并按甜点评分排序。
"""
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

from . import cboe
from .greeks import calc_black_scholes
from .scanner import TICKERS

logger = logging.getLogger(__name__)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """过滤无效行：需有正 bid/ask、正 IV。"""
    if df.empty:
        return df
    d = df[(df["bid"] > 0) & (df["ask"] > 0) & (df["impliedVolatility"] > 0.005)].copy()
    d["mid"] = (d["bid"] + d["ask"]) / 2
    return d.sort_values("strike").reset_index(drop=True)


def _leg_greeks(spot: float, strike: float, dte: int, iv: float, opt_type: str) -> dict | None:
    return calc_black_scholes(spot, strike, dte, iv, opt_type)


def _vertical(short_row, long_row, spot: float, dte: int, kind: str, exp: str) -> dict | None:
    """
    构建垂直价差。
    kind: bull_put（信用）/ bear_call（信用）/ bull_call（借记）/ bear_put（借记）
    short_row 是卖出腿，long_row 是买入腿。
    """
    sk, lk = float(short_row["strike"]), float(long_row["strike"])
    width = abs(sk - lk)
    if width <= 0:
        return None

    net = short_row["mid"] - long_row["mid"]   # 正=信用，负=借记
    is_credit = kind in ("bull_put", "bear_call")
    opt_type = "put" if kind in ("bull_put", "bear_put") else "call"

    if is_credit:
        credit = net
        if credit <= 0.02:
            return None
        max_profit = round(credit * 100, 2)
        max_loss = round((width - credit) * 100, 2)
        if kind == "bull_put":
            break_even = round(sk - credit, 2)
        else:  # bear_call
            break_even = round(sk + credit, 2)
    else:
        debit = -net
        if debit <= 0.02:
            return None
        max_profit = round((width - debit) * 100, 2)
        max_loss = round(debit * 100, 2)
        if kind == "bull_call":
            break_even = round(min(sk, lk) + debit, 2)
        else:  # bear_put
            break_even = round(max(sk, lk) - debit, 2)

    credit_width = round(net / width * 100, 1) if is_credit else None
    risk_reward = round(max_profit / max_loss, 2) if max_loss > 0 else None

    sg = _leg_greeks(spot, sk, dte, float(short_row["impliedVolatility"]), opt_type)
    lg = _leg_greeks(spot, lk, dte, float(long_row["impliedVolatility"]), opt_type)
    if not sg or not lg:
        return None

    short_sign = -1 if is_credit else (1 if kind == "bull_call" else -1)
    # 组合 Greeks：短腿取负号，长腿取正号（借记价差里“短腿”其实是更远的买入…统一处理）
    if is_credit:
        net_delta = round(-sg["delta"] + lg["delta"], 3)
        net_theta = round((-sg["theta_day"] + lg["theta_day"]) * 100, 2)
        net_vega = round((-sg["vega_1pct"] + lg["vega_1pct"]) * 100, 2)
        pop = round(sg["pop"] if opt_type == "put" else 100 - sg["pop"], 1)
        short_delta = abs(sg["delta"])
    else:
        net_delta = round(sg["delta"] - lg["delta"], 3)
        net_theta = round((sg["theta_day"] - lg["theta_day"]) * 100, 2)
        net_vega = round((sg["vega_1pct"] - lg["vega_1pct"]) * 100, 2)
        pop = None
        short_delta = abs(sg["delta"])

    return {
        "type": "vertical",
        "strategy": kind,
        "expiration": exp,
        "dte": dte,
        "shortStrike": sk,
        "longStrike": lk,
        "width": round(width, 2),
        "netCredit": round(net, 2) if is_credit else None,
        "netDebit": round(-net, 2) if not is_credit else None,
        "maxProfit": max_profit,
        "maxLoss": max_loss,
        "breakEven": break_even,
        "creditWidthPct": credit_width,
        "riskReward": risk_reward,
        "pop": pop,
        "netDelta": net_delta,
        "netTheta": net_theta,
        "netVega": net_vega,
        "shortDelta": round(short_delta, 3),
        "capitalRequired": max_loss,
        "legs": [
            {"action": "sell", "type": opt_type, "strike": sk, "premium": round(float(short_row["mid"]), 2),
             "iv": round(float(short_row["impliedVolatility"]), 4)},
            {"action": "buy", "type": opt_type, "strike": lk, "premium": round(float(long_row["mid"]), 2),
             "iv": round(float(long_row["impliedVolatility"]), 4)},
        ],
    }


def _iron_condor(bull_put: dict, bear_call: dict, spot: float, exp: str, dte: int) -> dict:
    total_credit = (bull_put["netCredit"] or 0) + (bear_call["netCredit"] or 0)
    max_loss = round(max(bull_put["maxLoss"], bear_call["maxLoss"]), 2)
    max_profit = round(total_credit * 100, 2)
    return {
        "type": "iron_condor",
        "strategy": "iron_condor",
        "expiration": exp,
        "dte": dte,
        "putShortStrike": bull_put["shortStrike"],
        "putLongStrike": bull_put["longStrike"],
        "callShortStrike": bear_call["shortStrike"],
        "callLongStrike": bear_call["longStrike"],
        "netCredit": round(total_credit, 2),
        "maxProfit": max_profit,
        "maxLoss": max_loss,
        "lowerBreakEven": bull_put["breakEven"],
        "upperBreakEven": bear_call["breakEven"],
        "wingWidth": bull_put["width"],
        "riskReward": round(max_profit / max_loss, 2) if max_loss > 0 else None,
        "netDelta": round(bull_put["netDelta"] + bear_call["netDelta"], 3),
        "netTheta": round(bull_put["netTheta"] + bear_call["netTheta"], 2),
        "netVega": round(bull_put["netVega"] + bear_call["netVega"], 2),
        "pop": round((bull_put["pop"] or 0) + (bear_call["pop"] or 0) - 100, 1)
               if bull_put["pop"] and bear_call["pop"] else None,
        "capitalRequired": max_loss,
        "legs": bull_put["legs"] + bear_call["legs"],
    }


def _straddle_strangle(calls: pd.DataFrame, puts: pd.DataFrame, spot: float,
                       exp: str, dte: int, wide: bool) -> dict | None:
    """买入跨式(wide=False)/宽跨(wide=True)：财报前 / 预期大波动时用。"""
    if calls.empty or puts.empty:
        return None
    if wide:
        call_target, put_target = spot * 1.05, spot * 0.95
    else:
        call_target = put_target = spot
    call_row = calls.iloc[(calls["strike"] - call_target).abs().argmin()]
    put_row = puts.iloc[(puts["strike"] - put_target).abs().argmin()]

    debit = float(call_row["mid"]) + float(put_row["mid"])
    if debit <= 0.05:
        return None
    ck, pk = float(call_row["strike"]), float(put_row["strike"])
    cg = _leg_greeks(spot, ck, dte, float(call_row["impliedVolatility"]), "call")
    pg = _leg_greeks(spot, pk, dte, float(put_row["impliedVolatility"]), "put")
    if not cg or not pg:
        return None

    exp_move = spot * ((float(call_row["impliedVolatility"]) + float(put_row["impliedVolatility"])) / 2) * math.sqrt(dte / 365)
    return {
        "type": "strangle" if wide else "straddle",
        "strategy": "long_strangle" if wide else "long_straddle",
        "expiration": exp,
        "dte": dte,
        "callStrike": ck,
        "putStrike": pk,
        "netDebit": round(debit, 2),
        "maxLoss": round(debit * 100, 2),
        "maxProfit": None,
        "lowerBreakEven": round(pk - debit, 2),
        "upperBreakEven": round(ck + debit, 2),
        "expectedMove": round(exp_move, 2),
        "breakEvenMove": round(debit, 2),
        "moveEdge": round((exp_move - debit) / debit * 100, 1) if debit > 0 else None,
        "netDelta": round(cg["delta"] + pg["delta"], 3),
        "netVega": round((cg["vega_1pct"] + pg["vega_1pct"]) * 100, 2),
        "netTheta": round((cg["theta_day"] + pg["theta_day"]) * 100, 2),
        "capitalRequired": round(debit * 100, 2),
        "legs": [
            {"action": "buy", "type": "call", "strike": ck, "premium": round(float(call_row["mid"]), 2),
             "iv": round(float(call_row["impliedVolatility"]), 4)},
            {"action": "buy", "type": "put", "strike": pk, "premium": round(float(put_row["mid"]), 2),
             "iv": round(float(put_row["impliedVolatility"]), 4)},
        ],
    }


# ─── 评分 ─────────────────────────────────────────────────────────────────────

def _score_spread(s: dict) -> float:
    t = s["type"]
    if t in ("vertical", "iron_condor"):
        if s.get("netCredit"):
            cw = (s.get("creditWidthPct") or
                  (s["netCredit"] / s.get("wingWidth", 1) * 100 if t == "iron_condor" else 0))
            cw_score = min(1.0, cw / 40) if cw else 0.3
            pop_score = (s.get("pop") or 60) / 100
            rr_score = min(1.0, (s.get("riskReward") or 0.3) / 0.6)
            sd = s.get("shortDelta", 0.25)
            delta_score = 1.0 if 0.15 <= sd <= 0.30 else 0.5
            return round(cw_score * 0.35 + pop_score * 0.30 + rr_score * 0.20 + delta_score * 0.15, 4)
        else:  # debit vertical
            rr_score = min(1.0, (s.get("riskReward") or 0.5) / 1.5)
            return round(rr_score * 0.6 + 0.4, 4)
    # straddle/strangle：波动率相对便宜（预期波动 > 盈亏平衡）时得分高
    edge = s.get("moveEdge") or 0
    return round(min(1.0, max(0.0, 0.5 + edge / 100)), 4)


# ─── 单标的价差构建 ──────────────────────────────────────────────────────────

def _build_for_ticker(symbol: str, strategy: str, dte_min: int, dte_max: int) -> list[dict]:
    try:
        data = cboe.fetch(symbol)
        if not data:
            return []
        spot = data.get("current_price")
        chains = data.get("chains") or {}
        if not spot or not chains:
            return []

        today = datetime.now()
        valid = [(e, (datetime.strptime(e, "%Y-%m-%d") - today).days) for e in sorted(chains.keys())]
        valid = [(e, d) for e, d in valid if dte_min <= d <= dte_max]
        if len(valid) > 3:
            valid = [valid[0], valid[len(valid) // 2], valid[-1]]

        out = []
        for exp, dte in valid:
            calls = _clean(chains[exp]["calls"])
            puts = _clean(chains[exp]["puts"])

            if strategy in ("bull_put", "iron_condor"):
                out.extend(_scan_credit_verticals(puts, spot, dte, "bull_put", exp))
            if strategy in ("bear_call", "iron_condor"):
                out.extend(_scan_credit_verticals(calls, spot, dte, "bear_call", exp))
            if strategy == "bull_call":
                out.extend(_scan_debit_verticals(calls, spot, dte, "bull_call", exp))
            if strategy == "bear_put":
                out.extend(_scan_debit_verticals(puts, spot, dte, "bear_put", exp))
            if strategy == "iron_condor":
                out.extend(_scan_iron_condors(calls, puts, spot, dte, exp))
            if strategy in ("long_straddle", "long_strangle"):
                s = _straddle_strangle(calls, puts, spot, exp, dte, wide=(strategy == "long_strangle"))
                if s:
                    out.append(s)

        for s in out:
            s["symbol"] = symbol
            s["spot"] = round(spot, 2)
            s["score"] = _score_spread(s)
        return out
    except Exception as e:
        logger.warning("[spreads] %s 错误: %s", symbol, e)
        return []


def _scan_credit_verticals(df: pd.DataFrame, spot: float, dte: int, kind: str, exp: str) -> list[dict]:
    """短腿在 0.15–0.35 Delta 附近，长腿再向 OTM 挪 1–3 档。"""
    if len(df) < 2:
        return []
    out = []
    for i in range(len(df)):
        sk = float(df.iloc[i]["strike"])
        # 短腿方向性筛选：bull_put 卖 OTM put（strike<spot）；bear_call 卖 OTM call（strike>spot）
        if kind == "bull_put" and not (spot * 0.85 <= sk < spot):
            continue
        if kind == "bear_call" and not (spot < sk <= spot * 1.15):
            continue
        sg = calc_black_scholes(spot, sk, dte, float(df.iloc[i]["impliedVolatility"]), "put" if kind == "bull_put" else "call")
        if not sg or not (0.12 <= abs(sg["delta"]) <= 0.38):
            continue
        # 长腿：更 OTM 方向
        for j in (i - 1, i - 2, i + 1, i + 2):
            if not (0 <= j < len(df)):
                continue
            lk = float(df.iloc[j]["strike"])
            if kind == "bull_put" and lk >= sk:
                continue
            if kind == "bear_call" and lk <= sk:
                continue
            v = _vertical(df.iloc[i], df.iloc[j], spot, dte, kind, exp)
            if v and v["maxLoss"] > 0 and (v.get("creditWidthPct") or 0) >= 15:
                out.append(v)
    return out


def _scan_debit_verticals(df: pd.DataFrame, spot: float, dte: int, kind: str, exp: str) -> list[dict]:
    if len(df) < 2:
        return []
    out = []
    for i in range(len(df)):
        buy_k = float(df.iloc[i]["strike"])
        # bull_call 买接近 ATM 的 call；bear_put 买接近 ATM 的 put
        if kind == "bull_call" and not (spot * 0.95 <= buy_k <= spot * 1.05):
            continue
        if kind == "bear_put" and not (spot * 0.95 <= buy_k <= spot * 1.05):
            continue
        # bull_call 卖更高行权价 call；bear_put 卖更低行权价 put，方向相反
        candidates = (i + 1, i + 2, i + 3) if kind == "bull_call" else (i - 1, i - 2, i - 3)
        for j in candidates:
            if not (0 <= j < len(df)):
                continue
            sell_k = float(df.iloc[j]["strike"])
            if kind == "bull_call" and sell_k <= buy_k:
                continue
            if kind == "bear_put" and sell_k >= buy_k:
                continue
            short_row, long_row = df.iloc[j], df.iloc[i]
            v = _vertical(short_row, long_row, spot, dte, kind, exp)
            if v and v["maxLoss"] > 0:
                out.append(v)
    return out


def _scan_iron_condors(calls: pd.DataFrame, puts: pd.DataFrame, spot: float, dte: int, exp: str) -> list[dict]:
    bull_puts = _scan_credit_verticals(puts, spot, dte, "bull_put", exp)
    bear_calls = _scan_credit_verticals(calls, spot, dte, "bear_call", exp)
    if not bull_puts or not bear_calls:
        return []
    # 各取评分最高的一个组合成对称 IC
    bp = max(bull_puts, key=lambda x: _score_spread(x))
    bc = max(bear_calls, key=lambda x: _score_spread(x))
    return [_iron_condor(bp, bc, spot, exp, dte)]


# ─── 主扫描 ───────────────────────────────────────────────────────────────────

_SPREAD_STRATEGIES = {
    "bull_put", "bear_call", "bull_call", "bear_put",
    "iron_condor", "long_straddle", "long_strangle",
}


def scan_spreads(strategy: str = "bull_put", dte_min: int = 20, dte_max: int = 55,
                 limit: int = 40) -> list[dict]:
    if strategy not in _SPREAD_STRATEGIES:
        strategy = "bull_put"

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_build_for_ticker, sym, strategy, dte_min, dte_max): sym
            for sym in TICKERS
        }
        for fut in as_completed(futures):
            results.extend(fut.result())

    results.sort(key=lambda x: x["score"], reverse=True)

    # 每个标的每种结构只保留最优一条
    seen: set[tuple] = set()
    top: list[dict] = []
    for r in results:
        key = (r["symbol"], r["type"])
        if key not in seen:
            top.append(r)
            seen.add(key)
        if len(top) >= limit:
            break
    return top
