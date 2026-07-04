"""
波动率分析：期限结构、skew（偏斜）、真实 IV 历史快照。

数据来自 CBOE 期权链（已含每个 strike 的 IV）。CBOE 不提供历史 IV，
因此每次分析时把当日 ATM IV30 快照进 iv_history 表，逐步积累出真实的
IV Rank / Percentile（替代原先用历史波动率 HV 近似的做法）。
"""
import logging
import math
from datetime import datetime

import pandas as pd

from database import get_conn
from . import cboe

logger = logging.getLogger(__name__)


# ─── IV 历史快照表 ────────────────────────────────────────────────────────────

def init_iv_history():
    """建 iv_history 表（若不存在）。由 main 启动时调用。"""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS iv_history (
                symbol      TEXT NOT NULL,
                date        TEXT NOT NULL,
                iv30        REAL NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (symbol, date)
            )
        """)
        conn.commit()


def snapshot_iv(symbol: str, iv30: float) -> None:
    """把当日 ATM IV30 写入快照表（一天一条，重复则覆盖）。"""
    if not iv30 or iv30 <= 0:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO iv_history (symbol, date, iv30) VALUES (?, ?, ?)",
            (symbol.upper(), today, round(iv30, 2)),
        )
        conn.commit()


def real_iv_rank(symbol: str, current_iv30: float) -> dict | None:
    """基于快照表的真实 IV Rank / Percentile。数据不足 20 天返回 None。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT iv30 FROM iv_history WHERE symbol = ? ORDER BY date DESC LIMIT 252",
            (symbol.upper(),),
        ).fetchall()
    ivs = [r[0] for r in rows if r[0] and r[0] > 0]
    if len(ivs) < 20:
        return None
    lo, hi = min(ivs), max(ivs)
    iv_rank = (current_iv30 - lo) / (hi - lo) * 100 if hi > lo else 50.0
    iv_pct = sum(1 for v in ivs if v < current_iv30) / len(ivs) * 100
    return {
        "ivRank": round(max(0.0, min(100.0, iv_rank)), 1),
        "ivPercentile": round(iv_pct, 1),
        "sampleDays": len(ivs),
        "ivHigh": round(hi, 1),
        "ivLow": round(lo, 1),
    }


# ─── 期限结构 & skew ──────────────────────────────────────────────────────────

def _atm_iv(chain_df: pd.DataFrame, spot: float) -> float | None:
    """取最接近现价的行权价的 IV（十进制）。"""
    if chain_df.empty or spot <= 0:
        return None
    df = chain_df.copy()
    df["_dist"] = (df["strike"] - spot).abs()
    valid = df[df["impliedVolatility"] > 0.005]
    if valid.empty:
        return None
    row = valid.nsmallest(1, "_dist").iloc[0]
    return float(row["impliedVolatility"])


def _skew_curve(chain_df: pd.DataFrame, spot: float) -> list[dict]:
    """同一到期的 IV skew 曲线：按 moneyness (strike/spot) 排列的 IV 点。"""
    if chain_df.empty or spot <= 0:
        return []
    df = chain_df[chain_df["impliedVolatility"] > 0.005].copy()
    if df.empty:
        return []
    # 只取现价 ±25% 范围，避免深度 OTM 的垃圾 IV
    df = df[(df["strike"] >= spot * 0.75) & (df["strike"] <= spot * 1.25)]
    df = df.sort_values("strike")
    return [
        {
            "strike": round(float(r["strike"]), 2),
            "moneyness": round(float(r["strike"]) / spot, 3),
            "iv": round(float(r["impliedVolatility"]) * 100, 1),
        }
        for _, r in df.iterrows()
    ]


def analyze(symbol: str) -> dict | None:
    """
    返回 {symbol, spot, termStructure, skew, ivRank}。
    termStructure: 各到期的 ATM IV（call/put 平均）+ DTE。
    skew: 最近一个 30–45 DTE 到期的 put/call IV 曲线 + 25Δ risk reversal。
    """
    data = cboe.fetch(symbol)
    if not data:
        return None

    spot = data.get("current_price")
    chains = data.get("chains") or {}
    if not spot or not chains:
        return None

    today = datetime.now()
    term = []
    for exp in sorted(chains.keys()):
        dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
        if dte < 1:
            continue
        cc = chains[exp]
        call_iv = _atm_iv(cc["calls"], spot)
        put_iv = _atm_iv(cc["puts"], spot)
        ivs = [v for v in (call_iv, put_iv) if v]
        if not ivs:
            continue
        term.append({
            "expiration": exp,
            "dte": dte,
            "atmIv": round(sum(ivs) / len(ivs) * 100, 1),
        })

    # 选一个 25–55 DTE 的到期做 skew（最能代表市场偏斜）
    skew_exp = None
    for t in term:
        if 25 <= t["dte"] <= 55:
            skew_exp = t["expiration"]
            break
    if skew_exp is None and term:
        skew_exp = min(term, key=lambda t: abs(t["dte"] - 40))["expiration"]

    skew_data = None
    if skew_exp:
        cc = chains[skew_exp]
        put_curve = _skew_curve(cc["puts"], spot)
        call_curve = _skew_curve(cc["calls"], spot)
        # 25Δ risk reversal 近似：OTM call IV − OTM put IV（用 ±5% moneyness 代理）
        otm_put = _iv_at_moneyness(put_curve, 0.95)
        otm_call = _iv_at_moneyness(call_curve, 1.05)
        rr = round(otm_call - otm_put, 1) if (otm_put and otm_call) else None
        skew_data = {
            "expiration": skew_exp,
            "putCurve": put_curve,
            "callCurve": call_curve,
            "riskReversal25d": rr,
            "putSkew": round(otm_put - _iv_at_moneyness(put_curve, 1.0), 1)
                       if otm_put and _iv_at_moneyness(put_curve, 1.0) else None,
        }

    iv30 = data.get("iv30")
    if iv30:
        snapshot_iv(symbol, iv30)
    iv_rank = real_iv_rank(symbol, iv30) if iv30 else None

    # 期限结构形态：contango（远期 IV 更高，正常）vs backwardation（近期更高，紧张）
    structure_shape = None
    if len(term) >= 2:
        near = term[0]["atmIv"]
        far = term[-1]["atmIv"]
        structure_shape = "backwardation" if near > far + 1 else "contango" if far > near + 1 else "flat"

    return {
        "symbol": symbol.upper(),
        "spot": round(spot, 2),
        "iv30": iv30,
        "ivRank": iv_rank,
        "termStructure": term,
        "structureShape": structure_shape,
        "skew": skew_data,
    }


def _iv_at_moneyness(curve: list[dict], target: float) -> float | None:
    """取曲线上最接近 target moneyness 的 IV 点。"""
    if not curve:
        return None
    closest = min(curve, key=lambda p: abs(p["moneyness"] - target))
    return closest["iv"]
