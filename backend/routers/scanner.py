"""
/api/scan  —  期权扫描主接口
"""
import math
import os
from datetime import datetime

import pandas as pd
import requests
import yfinance as yf
from fastapi import APIRouter, Query

from services import cache as cache_svc
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

router = APIRouter()

STRATEGY_LABELS = {
    "sell_put": "卖出 Put（收权利金）",
    "buy_call": "买入 Call（看涨）",
    "sell_call": "卖出 Call（收权利金）",
    "buy_put": "买入 Put（看跌）",
}


@router.get("/api/scan")
def scan(
    strategies: str = Query(default="sell_put", description="逗号分隔：sell_put,buy_call,sell_call,buy_put"),
    dte_min: int = Query(default=7, ge=1),
    dte_max: int = Query(default=60, le=365),
    min_iv_rank: float = Query(default=0, ge=0, le=100),
    force_refresh: bool = Query(default=False),
):
    strategy_list = [s.strip() for s in strategies.split(",") if s.strip()]
    cache_key = f"scan:{'|'.join(sorted(strategy_list))}:{dte_min}:{dte_max}:{min_iv_rank}"

    if not force_refresh:
        cached = cache_svc.get(cache_key, ttl_seconds=3600)
        if cached is not None:
            return {"data": cached, "cached": True}

    results = scan_options(
        strategies=strategy_list,
        dte_min=dte_min,
        dte_max=dte_max,
        min_iv_rank=min_iv_rank,
    )

    cache_svc.set(cache_key, results)
    return {"data": results, "cached": False}


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
    win_rate, total, safe, triggered = _calc_empirical_win_rate(
        history, dte, current_price, strike
    )

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
            "winRate": round(win_rate * 100, 2),
            "triggeredEvents": triggered,
        },
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
    模拟 Rolling Out 备用计划。
    假设股票在到期时跌破行权价 2% (即 S = strike * 0.98)。
    平仓成本 (Buy To Close) 约等于内在价值 (strike - S) = strike * 0.02。
    寻找 30-60 天后到期的期权，找到能覆盖此平仓成本的新行权价。
    """
    import yfinance as yf
    from datetime import datetime
    
    ticker = yf.Ticker(symbol)
    today = datetime.now()
    exp_dates = ticker.options
    
    # 模拟平仓成本 (假设到期时跌破行权价2%，时间价值几乎为0)
    simulated_stock_price = strike * 0.98
    btc_cost = strike - simulated_stock_price
    
    # 我们希望找到一个 Net Credit
    target_premium = btc_cost + (premium * 0.2) # 尝试多赚 20% 原权利金
    
    best_roll = None
    
    for date_str in exp_dates:
        roll_dte = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
        # 寻找比当前 DTE 多 30~60 天的远期合约
        if dte + 20 <= roll_dte <= dte + 60:
            try:
                chain = ticker.option_chain(date_str)
                puts = chain.puts
                
                # 寻找能覆盖 target_premium 的最低行权价
                # 优先满足：Premium >= target_premium 且 Strike <= current_strike
                valid_puts = puts[
                    (puts['lastPrice'] >= target_premium) & 
                    (puts['strike'] <= strike)
                ]
                
                if not valid_puts.empty:
                    # 取行权价最低的那个 (最安全)
                    best_put = valid_puts.sort_values(by='strike', ascending=True).iloc[0]
                    
                    if best_roll is None or best_put['strike'] < best_roll['strike']:
                        best_roll = {
                            "roll_date": date_str,
                            "roll_dte": roll_dte,
                            "roll_strike": float(best_put['strike']),
                            "roll_premium": float(best_put['lastPrice']),
                            "btc_cost": round(btc_cost, 2),
                            "net_credit": round(float(best_put['lastPrice']) - btc_cost, 2)
                        }
            except Exception:
                continue
                
    if not best_roll:
        return {"status": "error", "message": "在当前保守波动率下，难以找到理想的向下延期 (Roll Down & Out) 机会。建议接盘做 Wheel Strategy。"}
        
    return {
        "status": "success",
        "data": best_roll
    }

