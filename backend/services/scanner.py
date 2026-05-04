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
            if cal and "Earnings Date" in cal and cal["Earnings Date"]:
                dt = cal["Earnings Date"][0].replace(tzinfo=None)
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


# ─── 综合评分算法 ─────────────────────────────────────────────────────────────

def _score(opt: dict) -> float:
    """
    评分逻辑：奖励"甜点区间"，惩罚极端值。
    sell_put / sell_call: 偏好 Delta 接近 0.20、年化 10-25%、IV Rank 高。
    """
    strategy = opt.get("strategy", "sell_put")
    iv_rank = opt.get("ivRank", 50) / 100
    spread_pct = opt.get("bidAskSpreadPct", 10)
    liq = opt.get("liquidityScore", 5) / 10

    if strategy in ("sell_put", "sell_call"):
        ann_ret = opt.get("annualizedReturn", 0)
        delta_abs = abs(opt.get("delta") or 0.20)
        pop_e = (opt.get("popEmpirical") or 50) / 100

        # 年化回报甜点：12-25%
        if ann_ret < 8:
            ann_score = max(0.0, ann_ret / 8) * 0.4
        elif ann_ret <= 25:
            ann_score = 0.4 + (ann_ret - 8) / 17 * 0.6
        else:
            ann_score = max(0.5, 1.0 - (ann_ret - 25) / 35 * 0.5)

        # Delta 甜点：0.15-0.30
        if 0.15 <= delta_abs <= 0.30:
            delta_score = 1.0
        elif delta_abs < 0.15:
            delta_score = max(0.2, delta_abs / 0.15)
        else:
            delta_score = max(0.2, 1.0 - (delta_abs - 0.30) / 0.25)

        return (
            ann_score * 0.35
            + delta_score * 0.25
            + iv_rank * 0.15
            + pop_e * 0.10
            + liq * 0.10
            - min(spread_pct / 100, 0.5) * 0.05
        )

    # 买方策略：偏好高 Delta、高 IV Rank
    delta_abs = abs(opt.get("delta") or 0.50)
    pop_e = (opt.get("popEmpirical") or 30) / 100
    if delta_abs >= 0.45:
        delta_score = 1.0
    elif delta_abs >= 0.30:
        delta_score = 0.5 + (delta_abs - 0.30) / 0.15 * 0.5
    else:
        delta_score = max(0.0, delta_abs / 0.30 * 0.5)

    return (
        delta_score * 0.40
        + iv_rank * 0.20
        + pop_e * 0.20
        + liq * 0.15
        - min(spread_pct / 100, 0.5) * 0.05
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
        if annualized_return < 8 or annualized_return > 80:
            return None
    else:
        if distance_pct > 15.0:  # 买方不要太深 OTM
            return None

    if strategy == "buy_call" and current_price < sma50:
        return None

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
        if pop_empirical < 50:
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
