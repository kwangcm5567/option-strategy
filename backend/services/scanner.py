"""
期权扫描核心逻辑：支持 sell_put / buy_call / sell_call / buy_put 四种策略。
"""
import math
import os
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

from .greeks import calc_black_scholes, calc_iv_rank, calc_expected_move

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
            if cal and "Earnings Date" in cal and cal["Earnings Date"]:
                dt = cal["Earnings Date"][0].replace(tzinfo=None)
                result[sym] = (dt - today).days
        except Exception:
            pass

    return result


# ─── 批量拉取除息日（FMP 优先）────────────────────────────────────────────

def _fetch_dividend_map() -> dict[str, str]:
    """
    返回 {symbol: ex_div_date_str}（未来 90 天内的最近一次除息日）。
    不支持股息的成长股自然不会出现在返回字典里。
    """
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
            date_str = item.get("date", "")   # ex-dividend date
            if sym in TICKERS and date_str and sym not in result:
                result[sym] = date_str
        return result
    except Exception:
        return {}


# ─── 流动性综合评分（1–10）────────────────────────────────────────────────

def _liquidity_score(volume: int, oi: int, spread_pct: float) -> int:
    """
    基于成交量、持仓量、买卖价差综合打分。
    - volume  ：每 100 手 +1 分，上限 4 分
    - OI      ：每 200 张 +1 分，上限 3 分
    - spread%  ：每 5% +1 分惩罚，上限 3 分
    """
    v = min(4, volume // 100)
    o = min(3, oi // 200)
    s = max(0, 3 - int(spread_pct / 5))
    return min(10, v + o + s)


# ─── 历史滚动窗口回测（计算经验胜率） ────────────────────────────────────────

def _precompute_windows(history_df: pd.DataFrame, dte: int) -> list[tuple]:
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


def _calc_empirical_win_rate(history_df: pd.DataFrame, dte: int, current_price: float, strike: float,
                              _windows: list[tuple] | None = None):
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


# ─── 综合评分算法 ─────────────────────────────────────────────────────────────

def _score(opt: dict) -> float:
    iv_rank = opt.get("ivRank", 50) / 100
    pop_t = opt.get("popTheoretical", 50) / 100
    pop_e = opt.get("popEmpirical", 50) / 100
    ann_norm = min(opt.get("annualizedReturn", 0) / 50, 1.0)
    spread_penalty = min(opt.get("bidAskSpreadPct", 10) / 100, 1.0)
    # 流动性低时额外惩罚
    liq_penalty = max(0.0, (5 - opt.get("liquidityScore", 5)) * 0.02)

    return (
        iv_rank * 0.30
        + pop_t * 0.25
        + pop_e * 0.20
        + ann_norm * 0.15
        - spread_penalty * 0.10
        - liq_penalty
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
    precomputed_windows: list[tuple] | None = None,
    earnings_date_str: str | None = None,
    days_to_earnings: int = 999,
    gap_risk_count: int = 0,
    ex_div_date: str | None = None,
    days_to_div: int = 999,
) -> dict | None:
    dte = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
    if dte <= 0:
        return None

    strike = float(row["strike"])
    premium = float(row["lastPrice"]) if not pd.isna(row["lastPrice"]) else 0.0
    bid = float(row["bid"]) if not pd.isna(row.get("bid", float("nan"))) else 0.0
    ask = float(row["ask"]) if not pd.isna(row.get("ask", float("nan"))) else 0.0
    iv = float(row["impliedVolatility"]) if not pd.isna(row["impliedVolatility"]) else 0.0
    volume = int(row["volume"]) if not pd.isna(row.get("volume", float("nan"))) else 0
    oi = int(row["openInterest"]) if not pd.isna(row.get("openInterest", float("nan"))) else 0

    if premium <= 0.05 or bid <= 0.0 or iv <= 0:
        return None
    if volume < 5 or oi < 25:
        return None

    bid_ask_spread = round(ask - bid, 2)
    bid_ask_spread_pct = round((bid_ask_spread / premium * 100) if premium > 0 else 100, 1)

    # ── 方向与距离 ──
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

    # ── DTE 范围过滤 ──
    if strategy in ("sell_put", "sell_call"):
        if not (7 <= dte <= 60):
            return None
    else:
        if not (14 <= dte <= 180):
            return None

    # ── 年化回报 ──
    return_pct = round(premium / strike * 100, 2)
    annualized_return = round(return_pct * (365 / max(dte, 1)), 1)

    if strategy in ("sell_put", "sell_call"):
        if annualized_return < 3 or annualized_return > 60:
            return None

    if strategy == "buy_call" and current_price < sma50:
        return None

    # ── IV vs HV ──
    iv_hv_ratio = round(iv / hist_vol, 2) if hist_vol > 0 and iv > 0 else None

    # ── IV Rank ──
    iv_rank = calc_iv_rank(history_1y, iv)

    # ── Black-Scholes Greeks ──
    greeks = calc_black_scholes(current_price, strike, dte, iv, bs_type)

    # ── 预期波动区间 ──
    exp_move = calc_expected_move(current_price, iv, dte)

    # ── 经验胜率 ──
    if strategy == "sell_put":
        win_rate, _, _, _ = _calc_empirical_win_rate(history_1y, dte, current_price, strike, precomputed_windows)
        pop_empirical = round(win_rate * 100, 1)
        if pop_empirical < 60:
            return None
    else:
        pop_empirical = greeks["pop"] if greeks else None

    # ── theta/vega 每合约 ──
    theta_per_contract = None
    vega_per_contract = None
    if greeks:
        theta_per_contract = round(greeks["theta_day"] * 100, 2)
        vega_per_contract = round(greeks["vega_1pct"] * 100, 2)

    # ── 流动性评分 ──
    liquidity_score = _liquidity_score(volume, oi, bid_ask_spread_pct)

    # ── 除息日风险：除息日落在 DTE 窗口内 ──
    dividend_risk = bool(ex_div_date and 0 <= days_to_div <= dte)

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
        "volume": volume,
        "openInterest": oi,
        "liquidityScore": liquidity_score,
        "riskScore": round(strike / support_level, 2) if support_level > 0 else 1.0,
        "aboveSma50": current_price >= sma50,
        # 财报风险
        "earningsDate": earnings_date_str,
        "earningsRisk": bool(dte >= days_to_earnings and days_to_earnings >= 0),
        # 除息风险
        "exDivDate": ex_div_date,
        "dividendRisk": dividend_risk,
        # 跳空风险
        "gapRiskCount": gap_risk_count,
        "gapRisk": gap_risk_count >= 3,
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

    # 两次批量 API：财报日期 + 除息日期
    earnings_map = _fetch_earnings_map()
    dividend_map = _fetch_dividend_map()

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

            # 财报
            days_to_earnings = earnings_map.get(symbol, 999)
            earnings_date_str = (
                (today + timedelta(days=days_to_earnings)).strftime("%Y-%m-%d")
                if days_to_earnings < 999 else None
            )

            # 除息
            ex_div_date = dividend_map.get(symbol)
            days_to_div = 999
            if ex_div_date:
                try:
                    days_to_div = (datetime.strptime(ex_div_date, "%Y-%m-%d") - today).days
                except ValueError:
                    ex_div_date = None

            # 跳空风险：过去 1 年单日跌幅超 5% 的天数
            gap_risk_count = int((daily_ret < -0.05).sum())

            exp_dates = ticker.options

            for date_str in exp_dates:
                dte_check = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
                if not (dte_min <= dte_check <= dte_max):
                    continue

                chain = ticker.option_chain(date_str)

                dte_val = dte_check
                win_windows = (
                    _precompute_windows(history, dte_val)
                    if any(s == "sell_put" for s in strategies) else None
                )

                for strategy in strategies:
                    rows = chain.puts if strategy in ("sell_put", "buy_put") else chain.calls
                    for _, row in rows.iterrows():
                        item = _process_row(
                            row, symbol, current_price, history,
                            hist_vol, support_level, sma50,
                            strategy, date_str, today,
                            precomputed_windows=win_windows if strategy == "sell_put" else None,
                            earnings_date_str=earnings_date_str,
                            days_to_earnings=days_to_earnings,
                            gap_risk_count=gap_risk_count,
                            ex_div_date=ex_div_date,
                            days_to_div=days_to_div,
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
