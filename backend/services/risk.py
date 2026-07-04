"""
专业组合风险台：Beta 加权 Delta（SPY 等价敞口）、相关性/行业集中度、
历史模拟 VaR、情景压力测试（2008/COVID/利率冲击）。

价格与 Beta 用 CBOE 日线历史（不封机房 IP）；持仓来自 SQLite。
"""
import logging
import math
from datetime import datetime

import pandas as pd

from database import get_conn
from . import cboe
from .greeks import calc_black_scholes

logger = logging.getLogger(__name__)

# 简化行业映射（用于集中度分析）
SECTOR_MAP = {
    "AAPL": "科技", "MSFT": "科技", "NVDA": "科技", "AMZN": "消费", "GOOGL": "科技",
    "META": "科技", "TSLA": "消费", "CRM": "科技", "NFLX": "科技", "AVGO": "科技",
    "AMD": "科技", "ORCL": "科技", "ADBE": "科技", "CSCO": "科技", "INTC": "科技",
    "QCOM": "科技", "NOW": "科技", "UBER": "科技", "PLTR": "科技", "SMCI": "科技",
    "SPY": "指数ETF", "QQQ": "指数ETF", "IWM": "指数ETF", "GLD": "商品",
    "COIN": "加密", "MSTR": "加密",
    "JPM": "金融", "V": "金融", "BAC": "金融", "GS": "金融", "MS": "金融",
    "WFC": "金融", "BLK": "金融", "SCHW": "金融", "BX": "金融",
    "UNH": "医疗", "LLY": "医疗", "ABBV": "医疗", "TMO": "医疗",
    "COST": "消费", "HD": "消费", "NKE": "消费", "SBUX": "消费", "TGT": "消费",
    "DIS": "消费", "XOM": "能源", "CVX": "能源", "SLB": "能源",
    "BA": "工业", "CAT": "工业", "GE": "工业", "LIN": "材料",
}

# 历史压力情景（标的价格冲击 + VIX/IV 冲击的绝对波动点数）
STRESS_SCENARIOS = {
    "2008金融危机": {"priceShock": -0.40, "ivShock": 0.40},
    "2020疫情暴跌": {"priceShock": -0.30, "ivShock": 0.50},
    "2018Q4回调": {"priceShock": -0.15, "ivShock": 0.15},
    "闪崩-10%": {"priceShock": -0.10, "ivShock": 0.10},
    "温和上涨+5%": {"priceShock": 0.05, "ivShock": -0.05},
    "强势上涨+10%": {"priceShock": 0.10, "ivShock": -0.08},
}


def _returns(symbol: str) -> pd.Series | None:
    hist = cboe.fetch_history(symbol)
    if hist.empty or len(hist) < 30:
        return None
    return hist["Close"].pct_change().dropna()


def _beta(stock_ret: pd.Series, spy_ret: pd.Series) -> float | None:
    aligned = pd.concat([stock_ret, spy_ret], axis=1, join="inner").dropna()
    if len(aligned) < 30:
        return None
    s, m = aligned.iloc[:, 0], aligned.iloc[:, 1]
    var_m = m.var()
    if var_m <= 0:
        return None
    return round(float(s.cov(m) / var_m), 2)


def _load_open_positions() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE status='open' OR status IS NULL"
        ).fetchall()
    return [dict(r) for r in rows]


def analyze_portfolio() -> dict:
    positions = _load_open_positions()
    if not positions:
        return {"empty": True}

    symbols = sorted({p["symbol"] for p in positions})
    today = datetime.now().date()

    spy_ret = _returns("SPY")
    ret_map = {sym: _returns(sym) for sym in symbols}
    beta_map = {
        sym: (_beta(r, spy_ret) if (r is not None and spy_ret is not None) else None)
        for sym, r in ret_map.items()
    }

    # 现价：用各标的历史最后一根收盘（CBOE），兜底用行权价
    price_map = {}
    for sym in symbols:
        hist = cboe.fetch_history(sym)
        price_map[sym] = float(hist["Close"].iloc[-1]) if not hist.empty else None

    total_delta = total_theta = total_vega = 0.0
    beta_weighted_delta = 0.0
    spy_price = price_map.get("SPY") or 500.0
    by_sector: dict[str, float] = {}
    by_symbol_exposure: dict[str, float] = {}
    position_details = []

    for pos in positions:
        sym = pos["symbol"]
        S = price_map.get(sym) or pos["strike"]
        exp = datetime.strptime(pos["expiration_date"], "%Y-%m-%d").date()
        dte = max(1, (exp - today).days)
        r = ret_map.get(sym)
        sigma = float(r.tail(21).std() * math.sqrt(252)) if r is not None and len(r) >= 21 else 0.3
        opt_type = "put" if "put" in pos["strategy"] else "call"
        bs = calc_black_scholes(S, pos["strike"], dte, sigma, opt_type)
        if not bs:
            continue

        qty = pos["quantity"]
        mult = qty * 100
        sign = -1 if pos["strategy"].startswith("sell_") else 1
        pos_delta = bs["delta"] * mult * sign

        total_delta += pos_delta
        total_theta += bs["theta_day"] * mult * sign
        total_vega += bs["vega_1pct"] * mult * sign

        beta = beta_map.get(sym) or 1.0
        # Beta 加权 Delta：折算成 SPY 等价 delta（$ 敞口/SPY价）
        dollar_delta = pos_delta * S
        beta_weighted_delta += dollar_delta * beta / spy_price

        notional = abs(pos_delta) * S
        by_sector[SECTOR_MAP.get(sym, "其他")] = by_sector.get(SECTOR_MAP.get(sym, "其他"), 0) + notional
        by_symbol_exposure[sym] = by_symbol_exposure.get(sym, 0) + notional

        position_details.append({
            "id": pos["id"], "symbol": sym, "strategy": pos["strategy"],
            "beta": beta, "delta": round(pos_delta, 1),
            "betaWeightedDelta": round(dollar_delta * beta / spy_price, 2),
        })

    # ── 集中度：Herfindahl 指数 + top 占比 ──
    total_notional = sum(by_symbol_exposure.values()) or 1
    hhi = sum((v / total_notional) ** 2 for v in by_symbol_exposure.values())
    sector_pct = {k: round(v / total_notional * 100, 1) for k, v in sorted(by_sector.items(), key=lambda x: -x[1])}
    top_symbol = max(by_symbol_exposure.items(), key=lambda x: x[1]) if by_symbol_exposure else (None, 0)

    # ── 相关性矩阵（标的日收益）──
    corr = _correlation_matrix(ret_map)

    # ── 历史模拟 VaR（组合 delta 敞口 × 各标的日收益）──
    var_metrics = _historical_var(positions, price_map, ret_map, today)

    # ── 情景压力测试 ──
    stress = _stress_test(positions, price_map, ret_map, today)

    return {
        "empty": False,
        "greeks": {
            "totalDelta": round(total_delta, 1),
            "totalTheta": round(total_theta, 2),
            "totalVega": round(total_vega, 2),
            "betaWeightedDelta": round(beta_weighted_delta, 2),
            "spyEquivalent": round(beta_weighted_delta * spy_price, 0),
        },
        "concentration": {
            "hhi": round(hhi, 3),
            "hhiLabel": "高度集中" if hhi > 0.25 else "中度集中" if hhi > 0.15 else "分散",
            "topSymbol": top_symbol[0],
            "topSymbolPct": round(top_symbol[1] / total_notional * 100, 1),
            "bySector": sector_pct,
        },
        "correlation": corr,
        "var": var_metrics,
        "stress": stress,
        "positions": position_details,
    }


def _correlation_matrix(ret_map: dict) -> dict:
    valid = {s: r for s, r in ret_map.items() if r is not None}
    if len(valid) < 2:
        return {"symbols": [], "matrix": []}
    df = pd.concat(valid.values(), axis=1, join="inner")
    df.columns = list(valid.keys())
    c = df.corr()
    syms = list(c.columns)
    matrix = [[round(float(c.iloc[i, j]), 2) for j in range(len(syms))] for i in range(len(syms))]
    return {"symbols": syms, "matrix": matrix}


def _position_dollar_delta(pos: dict, price_map: dict, ret_map: dict, today) -> tuple[float, str]:
    sym = pos["symbol"]
    S = price_map.get(sym) or pos["strike"]
    exp = datetime.strptime(pos["expiration_date"], "%Y-%m-%d").date()
    dte = max(1, (exp - today).days)
    r = ret_map.get(sym)
    sigma = float(r.tail(21).std() * math.sqrt(252)) if r is not None and len(r) >= 21 else 0.3
    opt_type = "put" if "put" in pos["strategy"] else "call"
    bs = calc_black_scholes(S, pos["strike"], dte, sigma, opt_type)
    if not bs:
        return 0.0, sym
    sign = -1 if pos["strategy"].startswith("sell_") else 1
    return bs["delta"] * pos["quantity"] * 100 * sign * S, sym


def _historical_var(positions, price_map, ret_map, today, confidence=0.95) -> dict:
    """一日历史模拟 VaR：用各标的过去 1 年日收益 × 持仓 $Delta 求组合日 P&L 分布。"""
    dollar_deltas = {}
    for pos in positions:
        dd, sym = _position_dollar_delta(pos, price_map, ret_map, today)
        dollar_deltas[sym] = dollar_deltas.get(sym, 0) + dd

    valid_syms = [s for s in dollar_deltas if ret_map.get(s) is not None]
    if not valid_syms:
        return {"oneDayVar95": None, "expectedShortfall": None}

    df = pd.concat([ret_map[s] for s in valid_syms], axis=1, join="inner")
    df.columns = valid_syms
    port_pnl = sum(df[s] * dollar_deltas[s] for s in valid_syms).dropna()
    if port_pnl.empty:
        return {"oneDayVar95": None, "expectedShortfall": None}

    var = float(port_pnl.quantile(1 - confidence))
    es = float(port_pnl[port_pnl <= var].mean()) if (port_pnl <= var).any() else var
    return {
        "oneDayVar95": round(-var, 2),
        "expectedShortfall": round(-es, 2),
        "sampleDays": len(port_pnl),
    }


def _stress_test(positions, price_map, ret_map, today) -> list[dict]:
    """各历史情景下的组合 P&L（用 BS 全重估，非线性 delta 近似）。"""
    out = []
    for name, sc in STRESS_SCENARIOS.items():
        total_pnl = 0.0
        for pos in positions:
            sym = pos["symbol"]
            S = price_map.get(sym) or pos["strike"]
            exp = datetime.strptime(pos["expiration_date"], "%Y-%m-%d").date()
            dte = max(1, (exp - today).days)
            r = ret_map.get(sym)
            base_sigma = float(r.tail(21).std() * math.sqrt(252)) if r is not None and len(r) >= 21 else 0.3
            opt_type = "put" if "put" in pos["strategy"] else "call"

            base = calc_black_scholes(S, pos["strike"], dte, base_sigma, opt_type)
            shocked = calc_black_scholes(
                S * (1 + sc["priceShock"]), pos["strike"], dte,
                max(0.05, base_sigma + sc["ivShock"]), opt_type,
            )
            if not base or not shocked:
                continue
            base_px = _reval_price(S, pos["strike"], dte, base_sigma, opt_type)
            shk_px = _reval_price(S * (1 + sc["priceShock"]), pos["strike"], dte,
                                  max(0.05, base_sigma + sc["ivShock"]), opt_type)
            sign = -1 if pos["strategy"].startswith("sell_") else 1
            # 期权持有者 P&L = (新价 - 旧价) × sign × 合约数
            total_pnl += (shk_px - base_px) * sign * pos["quantity"] * 100
        out.append({"scenario": name, "pnl": round(total_pnl, 2), **sc})
    return out


def _reval_price(S, K, dte, sigma, opt_type) -> float:
    T = dte / 365.0
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, (S - K) if opt_type == "call" else (K - S))
    d1 = (math.log(S / K) + (0.05 + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    nc = lambda x: (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
    if opt_type == "call":
        return S * nc(d1) - K * math.exp(-0.05 * T) * nc(d2)
    return K * math.exp(-0.05 * T) * nc(-d2) - S * nc(-d1)
