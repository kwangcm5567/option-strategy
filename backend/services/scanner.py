"""
期权扫描核心逻辑：支持 sell_put / buy_call / sell_call / buy_put 四种策略。
"""
import math
import os
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

from .greeks import calc_black_scholes, calc_iv_rank, calc_expected_move, calc_p50

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")

TICKERS = [
    "AAPL", "MSFT", "NVDA", "JPM", "V", "JNJ", "UNH",
    "AMZN", "TSLA", "GOOGL", "META", "XOM", "CVX",
    "PG", "KO", "HD", "COST", "ABBV", "CRM", "NFLX",
]

# ─── 批量拉取财报日期（FMP 优先，yfinance fallback）────────────────────────

def _fetch_earnings_map() -> dict[str, int]:
    """返回 {symbol: days_to_earnings}，1 次 FMP API 替代 20 次 yfinance 调用。"""
    today = datetime.now()
    result: dict[str, int] = {}

    if FMP_API_KEY:
        try:
            end = today + timedelta(days=180)
            resp = requests.get(
                "https://financialmodelingprep.com/api/v3/earning_calendar",
                params={
                    "from": today.strftime("%Y-%m-%d"),
                    "to": end.strftime("%Y-%m-%d"),
                    "apikey": FMP_API_KEY,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                for item in resp.json():
                    sym = item.get("symbol", "").upper()
                    date_str = item.get("date", "")
                    if sym in TICKERS and date_str and sym not in result:
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        result[sym] = (dt - today).days
        except Exception:
            pass

    for sym in [s for s in TICKERS if s not in result]:
        try:
            cal = yf.Ticker(sym).calendar
            dt = None
            if isinstance(cal, dict):
                dates = cal.get("Earnings Date") or cal.get("earningsDate") or []
                if dates:
                    d = dates[0]
                    if isinstance(d, str):
                        dt = datetime.strptime(d[:10], "%Y-%m-%d")
                    elif hasattr(d, "tzinfo"):
                        dt = d.replace(tzinfo=None)
                    else:
                        dt = d
            elif hasattr(cal, "iloc") and "Earnings Date" in cal.index:
                d = cal.loc["Earnings Date"].iloc[0]
                dt = d.replace(tzinfo=None) if hasattr(d, "tzinfo") else d
            if dt is not None:
                result[sym] = (dt - today).days
        except Exception:
            pass

    return result


# ─── 批量拉取除息日（FMP 优先）────────────────────────────────────────────

def _fetch_dividend_map() -> dict[str, str]:
    """返回 {symbol: ex_div_date_str}，未来 90 天内最近一次除息日。"""
    if not FMP_API_KEY:
        return {}
    try:
        today = datetime.now()
        end = today + timedelta(days=90)
        resp = requests.get(
            "https://financialmodelingprep.com/api/v3/stock_dividend_calendar",
            params={
                "from": today.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
                "apikey": FMP_API_KEY,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return {}
        result: dict[str, str] = {}
        for item in resp.json():
            sym = item.get("symbol", "").upper()
            date_str = item.get("date", "")
            if sym in TICKERS and date_str and sym not in result:
                result[sym] = date_str
        return result
    except Exception:
        return {}


# ─── 流动性综合评分（1–10）────────────────────────────────────────────────

def _liquidity_score(volume: int, oi: int, spread_pct: float) -> int:
    v = min(4, volume // 100)
    o = min(3, oi // 200)
    s = max(0, 3 - int(spread_pct / 5))
    return min(10, v + o + s)


# ─── 历史窗口预计算（下行 + 上行）────────────────────────────────────────

def _precompute_windows(history_df: pd.DataFrame, dte: int) -> list[tuple]:
    """预计算每个下行窗口 (start_date, start_price, window_min, drop_pct)。"""
    if history_df.empty:
        return []
    trading_dte = max(1, int(dte * 252 / 365))
    windows = []
    for i in range(len(history_df) - trading_dte):
        window = history_df.iloc[i: i + trading_dte]
        start_price = float(window["Close"].iloc[0])
        if start_price <= 0:
            continue
        window_min = float(window["Low"].min())
        drop_pct = (start_price - window_min) / start_price
        windows.append((window.index[0], start_price, window_min, drop_pct))
    return windows


def _precompute_up_windows(history_df: pd.DataFrame, dte: int) -> list[tuple]:
    """预计算每个上行窗口 (start_date, start_price, window_max, gain_pct)。"""
    if history_df.empty:
        return []
    trading_dte = max(1, int(dte * 252 / 365))
    windows = []
    for i in range(len(history_df) - trading_dte):
        window = history_df.iloc[i: i + trading_dte]
        start_price = float(window["Close"].iloc[0])
        if start_price <= 0:
            continue
        window_max = float(window["High"].max())
        gain_pct = (window_max - start_price) / start_price
        windows.append((window.index[0], start_price, window_max, gain_pct))
    return windows


def _calc_empirical_win_rate(history_df: pd.DataFrame, dte: int, current_price: float, strike: float,
                              _windows: list[tuple] | None = None):
    """sell_put 经验胜率：股价从未跌破行权价的窗口比例。"""
    if history_df.empty or current_price <= 0:
        return 1.0, 0, 0, []

    required_drop_pct = (current_price - strike) / current_price
    if required_drop_pct <= 0:
        return 0.0, 0, 0, []

    if _windows is None:
        _windows = _precompute_windows(history_df, dte)

    total_windows = len(_windows)
    safe_windows = 0
    triggered_events: list[dict] = []
    trading_dte = max(1, int(dte * 252 / 365))

    for start_date, start_price, window_min, drop_pct in _windows:
        if drop_pct < required_drop_pct:
            safe_windows += 1
        else:
            if not triggered_events or (
                start_date - datetime.strptime(triggered_events[-1]["date"], "%Y-%m-%d")
                .replace(tzinfo=start_date.tzinfo)
            ).days > trading_dte:
                triggered_events.append({
                    "date": start_date.strftime("%Y-%m-%d"),
                    "start_price": round(start_price, 2),
                    "min_price": round(window_min, 2),
                    "drawdown_pct": round(drop_pct * 100, 2),
                })
            else:
                last = triggered_events[-1]
                if drop_pct * 100 > last["drawdown_pct"]:
                    last["min_price"] = round(window_min, 2)
                    last["drawdown_pct"] = round(drop_pct * 100, 2)

    if total_windows == 0:
        return 1.0, 0, 0, []

    return safe_windows / total_windows, total_windows, safe_windows, triggered_events


def _empirical_win_call(up_windows: list[tuple], distance_pct: float) -> float | None:
    """buy_call / sell_call 经验胜率：基于上行窗口。"""
    if not up_windows:
        return None
    target = distance_pct / 100
    # buy_call: wins if stock DID gain >= target
    wins = sum(1 for _, _, _, gain in up_windows if gain >= target)
    return round(wins / len(up_windows) * 100, 1)


def _empirical_win_put_buy(down_windows: list[tuple], distance_pct: float) -> float | None:
    """buy_put 经验胜率：基于下行窗口。"""
    if not down_windows:
        return None
    target = distance_pct / 100
    wins = sum(1 for _, _, _, drop in down_windows if drop >= target)
    return round(wins / len(down_windows) * 100, 1)


# ─── 技术指标辅助（Buy Call timing）────────────────────────────────────────────

def _calc_rsi(closes: pd.Series, period: int = 14) -> float:
    """RSI-14。数据不足时返回中性值 50.0。"""
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    last_loss = float(loss.iloc[-1])
    rs  = float(gain.iloc[-1]) / last_loss if last_loss > 0 else 100.0
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return round(rsi, 1) if not math.isnan(rsi) else 50.0


def _calc_macd(closes: pd.Series) -> dict:
    """MACD 12-26-9。返回 histogram、bullish、accelerating。"""
    ema12  = closes.ewm(span=12, adjust=False).mean()
    ema26  = closes.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    h_last = float(hist.iloc[-1])
    h_prev = float(hist.iloc[-2]) if len(hist) >= 2 else h_last
    return {
        "histogram":    round(h_last, 4),
        "bullish":      h_last > 0,
        "accelerating": h_last > h_prev,
    }


# ─── 综合评分算法 ─────────────────────────────────────────────────────────────

def _score(opt: dict) -> float:
    """
    机构级评分：卖方策略以 ROC / IV溢价 / σ-距离甜点 为核心权重；
    买方策略以 技术时机（RSI/MACD/趋势）/ IV 便宜度 / Delta 甜点 为核心权重。
    """
    strategy = opt.get("strategy", "sell_put")
    liq = opt.get("liquidityScore", 5) / 10

    if strategy in ("sell_put", "sell_call"):
        # ROC 甜点：12-25%（过低无意义，过高风险大）
        roc_val = opt.get("roc") or opt.get("annualizedReturn") or 0
        if roc_val < 12:
            roc_score = max(0.0, roc_val / 12) * 0.4
        elif roc_val <= 25:
            roc_score = 0.4 + (roc_val - 12) / 13 * 0.6
        else:
            roc_score = max(0.3, 1.0 - (roc_val - 25) / 30 * 0.7)

        # IV 溢价（IV 相对 HV 的超额）：越高越好（卖方时机判断核心指标）
        iv_prem = opt.get("ivPremium") or 0
        if iv_prem <= 0:
            iv_prem_score = max(0.0, 0.3 + iv_prem / 100 * 0.3)
        elif iv_prem <= 50:
            iv_prem_score = 0.3 + iv_prem / 50 * 0.7
        else:
            iv_prem_score = max(0.7, 1.0 - (iv_prem - 50) / 100 * 0.3)

        # Delta 甜点：0.15-0.30
        delta_abs = abs(opt.get("delta") or 0.20)
        if 0.15 <= delta_abs <= 0.30:
            delta_score = 1.0
        elif delta_abs < 0.15:
            delta_score = max(0.2, delta_abs / 0.15)
        else:
            delta_score = max(0.2, 1.0 - (delta_abs - 0.30) / 0.25)

        # σ-距离甜点：1.0-1.5σ，峰值 1.2σ
        std_dist = opt.get("stdDistance") or 0
        if std_dist <= 0:
            std_dist_score = 0.0
        elif std_dist < 1.0:
            std_dist_score = std_dist / 1.0 * 0.4
        elif std_dist <= 1.2:
            std_dist_score = 0.4 + (std_dist - 1.0) / 0.2 * 0.6
        elif std_dist <= 1.5:
            std_dist_score = max(0.7, 1.0 - (std_dist - 1.2) / 0.3 * 0.3)
        else:
            std_dist_score = max(0.3, 1.0 - (std_dist - 1.5) / 1.5 * 0.7)

        return (
            roc_score * 0.30
            + iv_prem_score * 0.25
            + delta_score * 0.20
            + std_dist_score * 0.15
            + liq * 0.10
        )

    # ── 买方策略：技术时机主导，IV 便宜度次之 ──
    # 技术时机（RSI + MACD + 双均线）
    rsi_val = opt.get("rsi") or 50.0
    rsi_s = (
        1.0 if 45 <= rsi_val <= 65 else
        0.6 if (35 <= rsi_val < 45 or 65 < rsi_val <= 70) else
        0.2 if rsi_val > 70 else 0.1
    )
    macd_s = (
        1.0 if (opt.get("macdBullish") and opt.get("macdAccel")) else
        0.7 if opt.get("macdBullish") else 0.3
    )
    above50  = opt.get("aboveSma50", False)
    above200 = opt.get("aboveSma200")
    trend_s  = 1.0 if (above50 and above200) else 0.65 if above50 else 0.2
    tech_score = rsi_s * 0.40 + macd_s * 0.35 + trend_s * 0.25

    # IV 便宜度（买方要低 IV Rank — 期权便宜才买）
    iv_cheap = 1.0 - min(opt.get("ivRank", 50) / 100.0, 1.0)

    # Delta 甜点（0.35-0.55：足够方向性但不过度高 gamma）
    delta_abs = abs(opt.get("delta") or 0.40)
    delta_s = (
        1.0 if 0.35 <= delta_abs <= 0.55 else
        0.75 if 0.30 <= delta_abs <= 0.65 else 0.35
    )

    pop_e = (opt.get("popEmpirical") or 40) / 100

    return (
        tech_score * 0.35
        + iv_cheap  * 0.25
        + delta_s   * 0.25
        + pop_e     * 0.10
        + liq       * 0.05
    )


# ─── 单条期权行处理 ───────────────────────────────────────────────────────────

def _process_row(
    row,
    symbol: str,
    current_price: float,
    history_1y: pd.DataFrame,
    hist_vol: float,
    support_level: float,
    sma50: float,
    strategy: str,
    date_str: str,
    today: datetime,
    down_windows: list[tuple] | None = None,
    up_windows: list[tuple] | None = None,
    earnings_date_str: str | None = None,
    days_to_earnings: int = 999,
    gap_risk_count: int = 0,
    ex_div_date: str | None = None,
    days_to_div: int = 999,
    rsi: float = 50.0,
    macd_info: dict | None = None,
    sma200: float | None = None,
) -> dict | None:
    dte = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
    if dte <= 0:
        return None

    strike = float(row["strike"])
    last_price = float(row["lastPrice"]) if not pd.isna(row["lastPrice"]) else 0.0
    bid = float(row["bid"]) if not pd.isna(row.get("bid", float("nan"))) else 0.0
    ask = float(row["ask"]) if not pd.isna(row.get("ask", float("nan"))) else 0.0
    iv = float(row["impliedVolatility"]) if not pd.isna(row["impliedVolatility"]) else 0.0
    volume = int(row["volume"]) if not pd.isna(row.get("volume", float("nan"))) else 0
    oi = int(row["openInterest"]) if not pd.isna(row.get("openInterest", float("nan"))) else 0

    # 用 mid 兜底（许多活跃期权近期无成交但 bid/ask 有效）
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
    premium = last_price if last_price > 0.05 else mid
    if premium < 0.05:
        return None

    # IV：yfinance 原始值优先，不可靠时用历史波动率
    if iv < 0.005:
        iv = hist_vol

    if volume < 3 or oi < 10:
        return None

    bid_ask_spread = round(ask - bid, 2)
    bid_ask_spread_pct = round((bid_ask_spread / premium * 100) if premium > 0 else 100, 1)

    is_put = strategy in ("sell_put", "buy_put")
    bs_type = "put" if is_put else "call"

    if is_put:
        if strike >= current_price:
            return None
        distance_pct = round((current_price - strike) / current_price * 100, 1)
        break_even = round(strike - premium, 2)
        if strategy == "sell_put":
            max_profit = round(premium * 100, 2)
            max_loss = round((strike - premium) * 100, 2)
        else:
            max_profit = round((strike - premium) * 100, 2)
            max_loss = round(premium * 100, 2)
    else:
        if strike <= current_price:
            return None
        distance_pct = round((strike - current_price) / current_price * 100, 1)
        break_even = round(strike + premium, 2)
        if strategy == "sell_call":
            max_profit = round(premium * 100, 2)
            max_loss = None
        else:
            max_profit = None
            max_loss = round(premium * 100, 2)

    if strategy in ("sell_put", "sell_call"):
        if not (7 <= dte <= 60):
            return None
    else:
        if not (14 <= dte <= 180):
            return None

    return_pct = round(premium / strike * 100, 2)
    annualized_return = round(return_pct * (365 / max(dte, 1)), 1)

    # 距离过滤（避免深 OTM 垃圾期权）
    if strategy in ("sell_put", "sell_call"):
        if not (2.0 <= distance_pct <= 20.0):
            return None
        if strategy == "sell_put" and (annualized_return < 8 or annualized_return > 80):
            return None
        if strategy == "sell_call" and (annualized_return < 3 or annualized_return > 80):
            return None
    else:
        if distance_pct > 15.0:  # 买方不要太深 OTM
            return None

    if strategy == "buy_call" and current_price < sma50:
        return None

    # ── 机构标准：σ-标准化距离（1.2σ 为甜点，≥ 1.0σ 为最低准入）──
    exp_move_pct_raw = iv * math.sqrt(dte / 365) * 100
    std_distance = round(distance_pct / exp_move_pct_raw, 2) if exp_move_pct_raw > 0 else None
    if strategy in ("sell_put", "sell_call") and std_distance is not None and std_distance < 1.0:
        return None

    # ── 机构标准：ROC（权利金/最大亏损 年化）──
    if strategy == "sell_put" and (strike - premium) > 0:
        roc = round(premium / (strike - premium) * (365 / dte) * 100, 1)
    elif strategy == "sell_call":
        roc = round(premium / strike * (365 / dte) * 100, 1)
    else:
        roc = None
    if strategy in ("sell_put", "sell_call") and roc is not None and roc > 40:
        return None

    # IV 溢价（IV 相对历史波动率的超额；正值对卖方有利）
    iv_premium = round((iv - hist_vol) / hist_vol * 100, 1) if hist_vol > 0 else None

    iv_hv_ratio = round(iv / hist_vol, 2) if hist_vol > 0 and iv > 0 else None
    iv_rank = calc_iv_rank(history_1y, iv)
    greeks = calc_black_scholes(current_price, strike, dte, iv, bs_type)
    exp_move = calc_expected_move(current_price, iv, dte)

    # Delta 过滤（核心质量门槛）
    if greeks:
        d_abs = abs(greeks["delta"])
        if strategy in ("sell_put", "sell_call"):
            # 卖方甜点：Delta 0.10-0.40（太低=深OTM低回报，太高=高风险）
            if not (0.10 <= d_abs <= 0.40):
                return None
        elif strategy == "buy_call":
            # 买方需要足够方向性敞口
            if d_abs < 0.30:
                return None
        elif strategy == "buy_put":
            if d_abs < 0.30:
                return None

    # ── 四种策略的经验胜率 ──
    if strategy == "sell_put":
        win_rate, _, _, _ = _calc_empirical_win_rate(history_1y, dte, current_price, strike, down_windows)
        pop_empirical = round(win_rate * 100, 1)
        if pop_empirical < 70:
            return None
    elif strategy == "buy_put":
        pop_empirical = _empirical_win_put_buy(down_windows, distance_pct)
    elif strategy == "buy_call":
        pop_empirical = _empirical_win_call(up_windows, distance_pct)
    elif strategy == "sell_call":
        # sell_call: win if stock did NOT rise above strike
        if up_windows:
            wins = sum(1 for _, _, _, gain in up_windows if gain < distance_pct / 100)
            pop_empirical = round(wins / len(up_windows) * 100, 1)
        else:
            pop_empirical = greeks["pop"] if greeks else None
    else:
        pop_empirical = greeks["pop"] if greeks else None

    # ── P50（仅卖出策略）──
    p50 = calc_p50(current_price, strike, premium, dte, iv, strategy)

    theta_per_contract = None
    vega_per_contract = None
    if greeks:
        theta_per_contract = round(greeks["theta_day"] * 100, 2)
        vega_per_contract = round(greeks["vega_1pct"] * 100, 2)

    liquidity_score = _liquidity_score(volume, oi, bid_ask_spread_pct)
    dividend_risk = bool(ex_div_date and 0 <= days_to_div <= dte)

    # 每合约所需资金
    if strategy == "sell_put":
        capital_required = round(strike * 100, 0)
    elif strategy in ("buy_call", "buy_put"):
        capital_required = round(premium * 100, 0)
    else:
        capital_required = None   # sell_call 需要保证金，各券商不同

    result = {
        "symbol": symbol,
        "strategy": strategy,
        "currentPrice": round(current_price, 2),
        "strike": strike,
        "premium": round(premium, 2),
        "bid": round(bid, 2),
        "ask": round(ask, 2),
        "expirationDate": date_str,
        "dte": dte,
        "distancePct": distance_pct,
        "breakEven": break_even,
        "expectedMoveUpper": exp_move["upper"],
        "expectedMoveLower": exp_move["lower"],
        "expectedMovePct": exp_move["move_pct"],
        "maxProfit": max_profit,
        "maxLoss": max_loss,
        "annualizedReturn": annualized_return,
        "returnPct": return_pct,
        "delta": greeks["delta"] if greeks else None,
        "gamma": greeks["gamma"] if greeks else None,
        "thetaPerDay": theta_per_contract,
        "vegaPerPct": vega_per_contract,
        "impliedVolatility": round(iv * 100, 1),
        "histVolatility": round(hist_vol * 100, 1),
        "ivHvRatio": iv_hv_ratio,
        "ivRank": iv_rank,
        "bidAskSpread": bid_ask_spread,
        "bidAskSpreadPct": bid_ask_spread_pct,
        "popTheoretical": greeks["pop"] if greeks else None,
        "popEmpirical": pop_empirical,
        "p50": p50,
        "volume": volume,
        "openInterest": oi,
        "liquidityScore": liquidity_score,
        "supportLevel": round(support_level, 2),
        "riskScore": round(strike / support_level, 2) if support_level > 0 else 1.0,
        "capitalRequired": capital_required,
        "aboveSma50": current_price >= sma50,
        "earningsDate": earnings_date_str,
        "earningsRisk": bool(dte >= days_to_earnings and days_to_earnings >= 0),
        "exDivDate": ex_div_date,
        "dividendRisk": dividend_risk,
        "gapRiskCount": gap_risk_count,
        "gapRisk": gap_risk_count >= 3,
        "stdDistance": std_distance,
        "roc": roc,
        "ivPremium": iv_premium,
        "rsi": rsi,
        "macdBullish":   macd_info.get("bullish")      if macd_info else None,
        "macdAccel":     macd_info.get("accelerating") if macd_info else None,
        "macdHistogram": macd_info.get("histogram")    if macd_info else None,
        "aboveSma200":   (current_price >= sma200)     if sma200 is not None else None,
    }
    result["score"] = round(_score(result), 4)
    return result


# ─── 主扫描函数 ───────────────────────────────────────────────────────────────

def scan_options(
    strategies: list[str] | None = None,
    dte_min: int = 7,
    dte_max: int = 60,
    min_iv_rank: float = 0,
) -> list[dict]:
    if strategies is None:
        strategies = ["sell_put"]

    today = datetime.now()
    results = []

    earnings_map = _fetch_earnings_map()
    dividend_map = _fetch_dividend_map()

    needs_down = any(s in strategies for s in ("sell_put", "buy_put"))
    needs_up   = any(s in strategies for s in ("buy_call", "sell_call"))

    for symbol in TICKERS:
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period="1y")
            if history.empty:
                continue

            current_price = float(history["Close"].iloc[-1])
            daily_ret = history["Close"].pct_change().dropna()
            hist_vol = float(daily_ret.std() * math.sqrt(252))
            sma50 = float(history["Close"].tail(50).mean())
            support_level = float(history["Close"].tail(126).quantile(0.20))
            rsi       = _calc_rsi(history["Close"])
            macd_info = _calc_macd(history["Close"])
            sma200    = float(history["Close"].tail(200).mean()) if len(history) >= 200 else None

            days_to_earnings = earnings_map.get(symbol, 999)
            earnings_date_str = (
                (today + timedelta(days=days_to_earnings)).strftime("%Y-%m-%d")
                if days_to_earnings < 999 else None
            )

            ex_div_date = dividend_map.get(symbol)
            days_to_div = 999
            if ex_div_date:
                try:
                    days_to_div = (datetime.strptime(ex_div_date, "%Y-%m-%d") - today).days
                except ValueError:
                    ex_div_date = None

            gap_risk_count = int((daily_ret < -0.05).sum())

            exp_dates = ticker.options

            # 先筛出有效到期日，并限制最多 4 个（避免每只股票 8+ 次 option_chain API 调用）
            valid_dates = []
            for date_str in exp_dates:
                dte_check = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
                if dte_min <= dte_check <= dte_max:
                    valid_dates.append((date_str, dte_check))
            if not valid_dates:
                continue

            # 取最多 4 个到期日（首、中前、中后、末），覆盖短中长期
            if len(valid_dates) > 4:
                indices = [0, len(valid_dates) // 3, len(valid_dates) * 2 // 3, len(valid_dates) - 1]
                valid_dates = [valid_dates[i] for i in sorted(set(indices))]

            # 用中位数 DTE 预计算历史窗口（一次/股票，不再每个到期日重复）
            rep_dte = valid_dates[len(valid_dates) // 2][1]
            down_win = _precompute_windows(history, rep_dte) if needs_down else None
            up_win   = _precompute_up_windows(history, rep_dte) if needs_up else None

            for date_str, dte_val in valid_dates:
                try:
                    chain = ticker.option_chain(date_str)
                except Exception as e:
                    print(f"[scanner] {symbol} {date_str} option_chain 失败: {e}")
                    continue

                for strategy in strategies:
                    rows = chain.puts if strategy in ("sell_put", "buy_put") else chain.calls
                    for _, row in rows.iterrows():
                        item = _process_row(
                            row, symbol, current_price, history,
                            hist_vol, support_level, sma50,
                            strategy, date_str, today,
                            down_windows=down_win,
                            up_windows=up_win,
                            earnings_date_str=earnings_date_str,
                            days_to_earnings=days_to_earnings,
                            gap_risk_count=gap_risk_count,
                            ex_div_date=ex_div_date,
                            days_to_div=days_to_div,
                            rsi=rsi,
                            macd_info=macd_info,
                            sma200=sma200,
                        )
                        if item:
                            results.append(item)

        except Exception as e:
            print(f"[scanner] {symbol} 错误: {e}")
            continue

    results.sort(key=lambda x: x["score"], reverse=True)

    seen = set()
    top = []
    for r in results:
        key = (r["symbol"], r["strategy"])
        if key not in seen:
            top.append(r)
            seen.add(key)
        if len(top) >= 30:
            break

    for r in results:
        if r not in top:
            top.append(r)
        if len(top) >= 30:
            break

    return top
