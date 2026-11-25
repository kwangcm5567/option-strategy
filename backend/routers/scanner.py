"""
/api/scan  —  期权扫描主接口
"""
import logging
import math
import os
import threading
from datetime import datetime
from typing import Literal

import pandas as pd
import requests
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from services import cache as cache_svc, chains
from services.scanner import scan_options, _calc_empirical_win_rate
from services.greeks import calc_black_scholes

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")


def _fmp_history(symbol: str) -> pd.DataFrame:
    """从 FMP 获取约 2 年日线数据（504 交易日），转换为与 yfinance 兼容的 DataFrame。"""
    if not FMP_API_KEY:
        return pd.DataFrame()
    try:
        url = (
            f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"
            f"?timeseries=504&apikey={FMP_API_KEY}"
        )
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            return pd.DataFrame()
        data = resp.json().get("historical", [])
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.rename(columns={
            "close": "Close", "open": "Open",
            "high": "High", "low": "Low", "volume": "Volume",
        })
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception:
        return pd.DataFrame()


def _fmp_news(symbol: str) -> list[dict]:
    """从 FMP 获取最新 10 条新闻。"""
    if not FMP_API_KEY:
        return []
    try:
        url = (
            f"https://financialmodelingprep.com/api/v3/stock_news"
            f"?tickers={symbol}&limit=10&apikey={FMP_API_KEY}"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        return resp.json()
    except Exception:
        return []

logger = logging.getLogger("scanner")
router = APIRouter()

STRATEGY_LABELS = {
    "sell_put": "卖出 Put（收权利金）",
    "buy_call": "买入 Call（看涨）",
    "sell_call": "卖出 Call（收权利金）",
    "buy_put": "买入 Put（看跌）",
}


_refresh_lock = threading.Lock()
_refreshing: set[str] = set()
_refresh_errors: dict[str, str] = {}


def _claim(key: str) -> bool:
    with _refresh_lock:
        if key in _refreshing:
            return False
        _refreshing.add(key)
        _refresh_errors.pop(key, None)
        return True


def _scan_claimed(key: str, params: dict) -> None:
    try:
        cache_svc.set(key, scan_options(**params))
    except Exception as e:
        logger.warning("[scan] 扫描失败 %s: %s", key, e)
        _refresh_errors[key] = str(e) or type(e).__name__
    finally:
        with _refresh_lock:
            _refreshing.discard(key)


def _refresh_in_background(key: str, params: dict) -> None:
    if _claim(key):
        threading.Thread(target=_scan_claimed, args=(key, params), daemon=True).start()


@router.get("/api/scan")
def scan(
    strategies: str = Query(default="sell_put", description="逗号分隔：sell_put,buy_call,sell_call,buy_put"),
    dte_min: int = Query(default=7, ge=1, le=365),
    dte_max: int = Query(default=60, ge=1, le=365),
    min_iv_rank: float = Query(default=0, ge=0, le=100),
    relaxed: bool = Query(default=False, description="放宽筛选门槛（市场平静期使用）"),
    force_refresh: bool = Query(default=False),
    profile: Literal["simple", "advanced"] = "advanced",
    fee_per_contract: float = Query(default=0.65, ge=0, le=100, allow_inf_nan=False),
    slippage_per_share: float = Query(default=0.01, ge=0, le=10, allow_inf_nan=False),
    max_capital: float = Query(default=0, ge=0, allow_inf_nan=False),
):
    return run_scan(strategies, dte_min, dte_max, min_iv_rank, relaxed, force_refresh, profile,
                    fee_per_contract, slippage_per_share, max_capital, background_refresh=True)


def run_scan(
    strategies: str = "sell_put",
    dte_min: int = 7,
    dte_max: int = 60,
    min_iv_rank: float = 0,
    relaxed: bool = False,
    force_refresh: bool = False,
    profile: str = "advanced",
    fee_per_contract: float = 0.65,
    slippage_per_share: float = 0.01,
    max_capital: float = 0,
    background_refresh: bool = False,
) -> dict:
    """background_refresh=True（HTTP）时缓存未命中不阻塞：立即返回旧结果或空列表并在后台扫描；
    False（预热）时同步扫描。同一 key 同时只跑一次扫描。"""
    strategy_list = sorted({s.strip() for s in strategies.split(",") if s.strip()})
    if not strategy_list or any(s not in STRATEGY_LABELS for s in strategy_list):
        raise HTTPException(422, "请选择有效策略")
    if dte_min > dte_max:
        raise HTTPException(422, "最短到期天数不能大于最长到期天数")
    if profile == "simple":
        if strategy_list != ["sell_put"] or relaxed or min_iv_rank != 0:
            raise HTTPException(422, "简单模式仅支持现金担保 Put，不放宽筛选或使用 IV Rank")
        dte_min, dte_max = max(30, dte_min), min(45, dte_max)
        if dte_min > dte_max:
            raise HTTPException(422, "简单模式到期范围为 30–45 天")

    key = (f"scan:v2:{profile}:{'|'.join(strategy_list)}:{dte_min}:{dte_max}:"
           f"{float(min_iv_rank)}:{'rx' if relaxed else 'std'}:{float(fee_per_contract)}:"
           f"{float(slippage_per_share)}:{float(max_capital)}")
    params = dict(strategies=strategy_list, dte_min=dte_min, dte_max=dte_max,
                  min_iv_rank=min_iv_rank, relaxed=relaxed, profile=profile,
                  fee_per_contract=fee_per_contract, slippage_per_share=slippage_per_share,
                  max_capital=max_capital)

    def _is_stale(rows) -> bool:
        return bool(rows) and all(r.get("stale") for r in rows)

    def _is_best_effort(rows) -> bool:
        return bool(rows) and all(r.get("bestEffort") for r in rows)

    def _dominant_source(rows) -> str | None:
        srcs = [r.get("source") for r in rows if r.get("source")]
        return max(set(srcs), key=srcs.count) if srcs else None

    def _resp(rows, *, cached: bool, updated_at: datetime, refreshing: bool = False) -> dict:
        return {
            "data": rows,
            "cached": cached,
            "relaxed": relaxed,
            "stale": _is_stale(rows),
            "bestEffort": _is_best_effort(rows),
            "source": _dominant_source(rows),
            "profile": profile,
            "noTrade": not rows,
            "refreshing": refreshing,
            "updatedAt": updated_at.isoformat(timespec="seconds"),
        }

    def _fresh(entry) -> bool:
        ttl = 300 if profile == "simple" or _is_stale(entry["data"]) else 3600
        return (datetime.now() - entry["ts"]).total_seconds() <= ttl

    entry = cache_svc.peek(key)
    if not force_refresh and entry is not None and _fresh(entry):
        return _resp(entry["data"], cached=True, updated_at=entry["ts"])

    if not background_refresh:
        if not _claim(key):
            rows = entry["data"] if entry is not None else []
            return _resp(rows, cached=entry is not None,
                         updated_at=entry["ts"] if entry else datetime.now(), refreshing=True)
        _scan_claimed(key, params)
        entry = cache_svc.peek(key)
        if entry is None:
            raise HTTPException(502, _refresh_errors.pop(key, "扫描失败"))
        return _resp(entry["data"], cached=False, updated_at=entry["ts"])

    if not force_refresh and key not in _refreshing and key in _refresh_errors:
        raise HTTPException(502, f"扫描失败：{_refresh_errors.pop(key)}")

    # 扫描耗时数分钟，不让 HTTP 请求挂着等：后台跑，先回旧结果（或空），前端轮询。
    _refresh_in_background(key, params)
    rows = entry["data"] if entry is not None else []
    # 扫描可能在响应前就结束了；仍回 refreshing=True，让前端再拉一次取结果
    return _resp(rows, cached=entry is not None, updated_at=entry["ts"] if entry else datetime.now(),
                 refreshing=True)


@router.get("/api/analyze/{symbol}")
def analyze_option(
    symbol: str,
    strike: float,
    dte: int,
    current_price: float,
    strategy: str = "sell_put",
):
    """
    单条期权的深度分析：历史验证 + 价格图表 + 新闻情绪 + Greeks
    """
    from fastapi import HTTPException
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    # ── 历史数据：优先 FMP，fallback yfinance ──
    history = _fmp_history(symbol)
    if history.empty:
        try:
            history = yf.Ticker(symbol).history(period="2y")
        except Exception:
            history = pd.DataFrame()
    if history.empty:
        raise HTTPException(status_code=404, detail="找不到历史数据，请稍后重试")

    # ── 历史回测 ──
    win_stats = _calc_empirical_win_rate(history, dte, current_price, strike)
    win_rate = win_stats["win_rate"]
    total = win_stats["total_windows"]
    safe = win_stats["safe_windows"]
    triggered = win_stats["triggered_events"]

    # ── 价格图表 ──
    chart_data = [
        {"date": d.strftime("%Y-%m-%d"), "price": round(float(row["Close"]), 2)}
        for d, row in history.iterrows()
    ]

    # ── 新闻情绪：优先 FMP，fallback yfinance ──
    AUTHORITATIVE = {
        "Bloomberg", "Reuters", "The Wall Street Journal",
        "CNBC", "Financial Times", "MarketWatch", "Barron's", "Forbes",
    }
    analyzer = SentimentIntensityAnalyzer()
    articles = []

    fmp_news = _fmp_news(symbol)
    if fmp_news:
        for item in fmp_news:
            title = item.get("title", "")
            publisher = item.get("site", "")
            link = item.get("url", "")
            if not title:
                continue
            score = analyzer.polarity_scores(title)["compound"]
            articles.append({"title": title, "publisher": publisher, "link": link, "sentimentScore": score})
    else:
        try:
            raw_news = yf.Ticker(symbol).news or []
            for item in raw_news:
                content = item.get("content", {})
                publisher = content.get("provider", {}).get("displayName", "") if content else item.get("publisher", "")
                title = content.get("title", "") if content else item.get("title", "")
                link = content.get("canonicalUrl", {}).get("url", "") if content else item.get("link", "")
                if not title:
                    continue
                score = analyzer.polarity_scores(title)["compound"]
                articles.append({"title": title, "publisher": publisher, "link": link, "sentimentScore": score})
        except Exception:
            pass

    articles.sort(key=lambda x: 0 if x["publisher"] in AUTHORITATIVE else 1)
    top_articles = articles[:5]
    avg_sentiment = (
        sum(a["sentimentScore"] for a in top_articles) / len(top_articles)
        if top_articles else 0
    )
    overall_sentiment = (
        "看涨" if avg_sentiment > 0.15 else
        "看跌" if avg_sentiment < -0.15 else
        "中性"
    )

    # ── 即时 Greeks ──
    daily_ret = history["Close"].pct_change().dropna()
    hist_vol = float(daily_ret.std() * math.sqrt(252))
    iv_approx = hist_vol   # 用 HV 近似（详细分析时 IV 来自 yfinance 实时数据）
    bs_type = "put" if "put" in strategy else "call"
    greeks = calc_black_scholes(current_price, strike, dte, iv_approx, bs_type)

    return {
        "symbol": symbol.upper(),
        "strike": strike,
        "strategy": strategy,
        "historicalStats": {
            "totalWindows": total,
            "safeWindows": safe,
            "triggeredWindows": total - safe,
            "winRate": round(win_rate * 100, 2) if win_rate is not None else None,
            "triggeredEvents": triggered,
        } if strategy == "sell_put" else None,
        "chartData": chart_data,
        "newsAnalysis": {
            "overallSentiment": overall_sentiment,
            "articles": top_articles,
        },
        "greeks": greeks,
        "histVolatility": round(hist_vol * 100, 1),
    }

@router.get("/api/simulate-roll/{symbol}")
def simulate_roll(
    symbol: str,
    strike: float,
    premium: float,
    dte: int,
):
    """
    模拟 Roll Down & Out 备用计划（数据走 CBOE）。

    平仓成本 (Buy To Close) 取当前持仓 put 的真实市价（bid/ask 中间价），
    再在比当前 DTE 多 20~60 天的远期里，找能覆盖该成本、行权价更低的新 put。
    """
    data, _ = chains.fetch(symbol, max(0, dte - 7), dte + 60, 8)
    chain_map = (data or {}).get("chains")
    if not chain_map:
        return {"status": "error", "message": "无法获取期权链数据（数据源暂不可用）。"}

    today = datetime.now()

    def _exp_dte(exp: str) -> int:
        return (datetime.strptime(exp, "%Y-%m-%d") - today).days

    def _mid(row) -> float:
        bid, ask = float(row["bid"]), float(row["ask"])
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return float(row["lastPrice"])

    def _nearest_strike(df, target: float):
        if df.empty:
            return None
        return df.loc[(df["strike"] - target).abs().idxmin()]

    # 平仓成本 = 当前这张 put 的实时市价（找最接近持仓到期日的那条链）
    cur_exp = min(chain_map, key=lambda e: abs(_exp_dte(e) - dte))
    cur_row = _nearest_strike(chain_map[cur_exp]["puts"], strike)
    btc_cost = _mid(cur_row) if cur_row is not None else strike * 0.02

    target_premium = btc_cost + premium * 0.2  # 滚后还想多赚 20% 原权利金

    best_roll = None
    for exp, slot in chain_map.items():
        roll_dte = _exp_dte(exp)
        if not (dte + 20 <= roll_dte <= dte + 60):
            continue
        puts = slot["puts"]
        if puts.empty:
            continue
        puts = puts.assign(mid=puts.apply(_mid, axis=1))
        valid = puts[(puts["mid"] >= target_premium) & (puts["strike"] <= strike)]
        if valid.empty:
            continue
        best = valid.sort_values(by="strike").iloc[0]  # 行权价最低 = 最安全
        if best_roll is None or best["strike"] < best_roll["roll_strike"]:
            best_roll = {
                "roll_date": exp,
                "roll_dte": roll_dte,
                "roll_strike": float(best["strike"]),
                "roll_premium": round(float(best["mid"]), 2),
                "btc_cost": round(btc_cost, 2),
                "net_credit": round(float(best["mid"]) - btc_cost, 2),
            }

    if not best_roll:
        return {"status": "error", "message": "在当前波动率下，难以找到理想的向下延期 (Roll Down & Out) 机会。建议接盘做 Wheel Strategy。"}

    return {"status": "success", "data": best_roll}

