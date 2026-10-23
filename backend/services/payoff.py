"""
盈亏图 / 情景分析：给定任意腿组合，计算到期盈亏曲线 + 用 Black-Scholes
估算「当前 / 到期前中途」的盈亏面（价格网格 × IV 档 × 剩余时间）。
"""
import math

from .greeks import calc_black_scholes, _norm_cdf

_R = 0.05


def _bs_price(spot: float, strike: float, dte: int, iv: float, opt_type: str) -> float:
    """Black-Scholes 期权理论价（per share）。"""
    T = dte / 365.0
    if T <= 0:
        # 到期日：内在价值
        return max(0.0, (spot - strike) if opt_type == "call" else (strike - spot))
    if iv <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (_R + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if opt_type == "call":
        return spot * _norm_cdf(d1) - strike * math.exp(-_R * T) * _norm_cdf(d2)
    return strike * math.exp(-_R * T) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def _leg_value(leg: dict, spot: float, dte: int, iv_shift: float = 0.0) -> float:
    """单腿在给定现价/剩余天数下的价值（含方向符号，per contract=×100）。"""
    strike = leg["strike"]
    opt_type = leg["type"]
    iv = max(0.01, leg.get("iv", 0.3) + iv_shift)
    price = _bs_price(spot, strike, dte, iv, opt_type)
    sign = 1 if leg["action"] == "buy" else -1
    return sign * price * 100 * leg.get("quantity", 1)


def _net_entry_cost(legs: list[dict]) -> float:
    """建仓净成本（正=借记付出，负=信用收到），per position。"""
    cost = 0.0
    for leg in legs:
        sign = 1 if leg["action"] == "buy" else -1
        cost += sign * leg["premium"] * 100 * leg.get("quantity", 1)
    return cost


def compute(legs: list[dict], spot: float, dte: int,
            price_range_pct: float = 0.30, points: int = 61) -> dict:
    """
    legs: [{action:'buy'/'sell', type:'call'/'put', strike, premium, iv?, quantity?}]
    返回到期盈亏曲线 + 当前(T=dte)/中途(T=dte/2)曲线 + 盈亏平衡点 + 关键指标。
    """
    entry_cost = _net_entry_cost(legs)   # >0 借记, <0 信用
    lo, hi = spot * (1 - price_range_pct), spot * (1 + price_range_pct)
    step = (hi - lo) / (points - 1)
    prices = [round(lo + i * step, 2) for i in range(points)]

    mid_dte = max(1, dte // 2)
    curve = []
    for p in prices:
        exp_val = sum(_leg_value(l, p, 0) for l in legs)          # 到期
        now_val = sum(_leg_value(l, p, dte) for l in legs)        # 当前
        mid_val = sum(_leg_value(l, p, mid_dte) for l in legs)    # 中途
        curve.append({
            "price": p,
            "expiryPnl": round(exp_val - entry_cost, 2),
            "currentPnl": round(now_val - entry_cost, 2),
            "midPnl": round(mid_val - entry_cost, 2),
        })

    exp_pnls = [c["expiryPnl"] for c in curve]
    max_profit = max(exp_pnls)
    max_loss = min(exp_pnls)

    # 盈亏平衡点：到期曲线穿越 0 的价格（线性插值）
    breakevens = []
    for i in range(1, len(curve)):
        a, b = curve[i - 1], curve[i]
        if (a["expiryPnl"] <= 0 <= b["expiryPnl"]) or (a["expiryPnl"] >= 0 >= b["expiryPnl"]):
            if b["expiryPnl"] != a["expiryPnl"]:
                t = -a["expiryPnl"] / (b["expiryPnl"] - a["expiryPnl"])
                breakevens.append(round(a["price"] + t * (b["price"] - a["price"]), 2))

    return {
        "spot": round(spot, 2),
        "dte": dte,
        "netEntry": round(entry_cost, 2),
        "isCredit": entry_cost < 0,
        "maxProfit": round(max_profit, 2),
        "maxLoss": round(max_loss, 2),
        "breakEvens": sorted(set(breakevens)),
        "curve": curve,
    }


def scenario_grid(legs: list[dict], spot: float, dte: int) -> dict:
    """
    情景矩阵：价格冲击 × IV 冲击 下的组合盈亏（当前时点）。
    行=IV 变动，列=价格变动，值=盈亏。用于压力测试单个结构。
    """
    entry_cost = _net_entry_cost(legs)
    price_shocks = [-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15]
    iv_shocks = [0.10, 0.05, 0.0, -0.05, -0.10]   # 绝对 IV 变动（+10 vol pts 等）

    grid = []
    for iv_s in iv_shocks:
        row = []
        for p_s in price_shocks:
            p = spot * (1 + p_s)
            val = sum(_leg_value(l, p, dte, iv_shift=iv_s) for l in legs)
            row.append(round(val - entry_cost, 2))
        grid.append({"ivShift": round(iv_s * 100, 0), "pnls": row})

    return {
        "priceShocks": [round(s * 100, 0) for s in price_shocks],
        "grid": grid,
    }
