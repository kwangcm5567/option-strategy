"""
Black-Scholes Greeks 计算模块
所有函数都基于标准 Black-Scholes 公式。
"""
import math
import pandas as pd

_RISK_FREE_RATE = 0.05  # 无风险利率近似值（美国国债收益率）


def _norm_cdf(x: float) -> float:
    """标准正态分布累积分布函数"""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_pdf(x: float) -> float:
    """标准正态分布概率密度函数"""
    return math.exp(-0.5 * x ** 2) / math.sqrt(2 * math.pi)


def calc_black_scholes(
    current_price: float,
    strike: float,
    dte: int,
    iv: float,           # 隐含波动率，小数形式（如 0.28 = 28%）
    option_type: str,    # 'put' or 'call'
    r: float = _RISK_FREE_RATE,
) -> dict | None:
    """
    计算 Black-Scholes Greeks 和理论获利概率。

    返回值（均为 per-share）：
      delta         - 股价变动 $1 时期权价格变动量
      gamma         - delta 的变化速度
      theta_day     - 每天时间衰减（期权买方视角为负数）
      vega_1pct     - IV 每变动 1% 时期权价格变动量（per share）
      pop           - 理论获利概率（%），short put/call = 到期 OTM 的概率
    """
    T = dte / 365.0
    if T <= 0 or iv <= 0 or current_price <= 0 or strike <= 0:
        return None
    try:
        d1 = (math.log(current_price / strike) + (r + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
        d2 = d1 - iv * math.sqrt(T)

        gamma = _norm_pdf(d1) / (current_price * iv * math.sqrt(T))
        # vega per share per 1% IV change
        vega_1pct = current_price * _norm_pdf(d1) * math.sqrt(T) * 0.01

        if option_type == "put":
            delta = _norm_cdf(d1) - 1.0                            # 负数（OTM put）
            theta_day = (
                -(current_price * _norm_pdf(d1) * iv) / (2 * math.sqrt(T))
                + r * strike * math.exp(-r * T) * _norm_cdf(-d2)
            ) / 365
            pop = _norm_cdf(d2) * 100       # P(S_T > K)，卖 put 的获利概率
        else:  # call
            delta = _norm_cdf(d1)                                   # 正数
            theta_day = (
                -(current_price * _norm_pdf(d1) * iv) / (2 * math.sqrt(T))
                - r * strike * math.exp(-r * T) * _norm_cdf(d2)
            ) / 365
            pop = _norm_cdf(d2) * 100       # P(S_T > K)，买 call 的获利概率

        return {
            "delta": round(delta, 3),
            "gamma": round(gamma, 5),
            "theta_day": round(theta_day, 4),   # per share per day（买方视角负数）
            "vega_1pct": round(vega_1pct, 4),   # per share per 1% IV
            "pop": round(pop, 1),
        }
    except Exception:
        return None


def calc_iv_rank(history_df: pd.DataFrame, current_iv_decimal: float) -> float:
    """
    用过去一年的滚动21日实现波动率（HV）作为 IV 历史分布的代理，
    计算当前 IV 在过去一年中处于多高的百分位（0–100）。

    yfinance 不提供历史 IV 数据，用 HV 作为近似替代。
    """
    if history_df is None or history_df.empty or len(history_df) < 30:
        return 50.0
    try:
        daily_ret = history_df["Close"].pct_change().dropna()
        rolling_hv = daily_ret.rolling(window=21).std() * math.sqrt(252)
        rolling_hv = rolling_hv.dropna()

        if rolling_hv.empty:
            return 50.0

        min_hv = float(rolling_hv.min())
        max_hv = float(rolling_hv.max())

        if max_hv <= min_hv:
            return 50.0

        rank = (current_iv_decimal - min_hv) / (max_hv - min_hv) * 100
        return round(float(min(max(rank, 0.0), 100.0)), 1)
    except Exception:
        return 50.0


def calc_p50(
    current_price: float,
    strike: float,
    premium: float,
    dte: int,
    iv: float,
    strategy: str,
    r: float = _RISK_FREE_RATE,
) -> float | None:
    """
    P50：到期时实现至少 50% 最大获利的概率。
    sell_put  : P(S_T >= K - P/2)  → stock stays above 50%-profit threshold
    sell_call : P(S_T <= K + P/2)  → stock stays below 50%-profit threshold
    """
    T = dte / 365.0
    if T <= 0 or iv <= 0 or current_price <= 0:
        return None
    try:
        if strategy == "sell_put":
            k_adj = strike - premium / 2
            if k_adj <= 0:
                return 99.9
            d2 = (math.log(current_price / k_adj) + (r - 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
            return round(_norm_cdf(d2) * 100, 1)
        if strategy == "sell_call":
            k_adj = strike + premium / 2
            d2 = (math.log(current_price / k_adj) + (r - 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
            return round(_norm_cdf(-d2) * 100, 1)
        return None
    except Exception:
        return None


def calc_expected_move(current_price: float, iv_decimal: float, dte: int) -> dict:
    """
    计算基于 IV 的到期前 ±1σ 预期波动区间（约 68% 概率股价在此范围内）。
    """
    dte = max(dte, 1)
    move = current_price * iv_decimal * math.sqrt(dte / 365)
    return {
        "upper": round(current_price + move, 2),
        "lower": round(current_price - move, 2),
        "move_pct": round((move / current_price) * 100, 1),
    }
