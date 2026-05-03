"""
新闻抓取与风险分析服务：优先华尔街见闻，回退 FMP。
"""
import os
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")

# Ticker → 中文名/英文别名 用于在华尔街见闻全量流里过滤
TICKER_CN_MAP: dict[str, list[str]] = {
    "AAPL":  ["苹果", "Apple"],
    "MSFT":  ["微软", "Microsoft"],
    "NVDA":  ["英伟达", "Nvidia", "NVIDIA"],
    "AMZN":  ["亚马逊", "Amazon"],
    "TSLA":  ["特斯拉", "Tesla"],
    "GOOGL": ["谷歌", "Google", "Alphabet"],
    "META":  ["Meta", "脸书", "Facebook"],
    "JPM":   ["摩根大通", "JPMorgan", "摩根"],
    "V":     ["Visa"],
    "JNJ":   ["强生", "Johnson"],
    "UNH":   ["联合健康", "UnitedHealth"],
    "XOM":   ["埃克森", "Exxon"],
    "CVX":   ["雪佛龙", "Chevron"],
    "PG":    ["宝洁", "Procter"],
    "KO":    ["可口可乐", "Coca-Cola", "Coca Cola"],
    "HD":    ["家得宝", "Home Depot"],
    "COST":  ["好市多", "Costco"],
    "ABBV":  ["艾伯维", "AbbVie"],
    "CRM":   ["Salesforce"],
    "NFLX":  ["奈飞", "Netflix"],
}

NEGATIVE_KW = [
    "暴跌", "崩盘", "大跌", "下跌", "熔断", "危机", "亏损", "衰退",
    "降级", "违约", "制裁", "调查", "起诉", "罚款", "看空", "抛售",
    "下调", "警告", "风险", "抵制", "禁令", "竞争加剧", "裁员", "减产",
    "暴雷", "暴亏", "跌停", "做空", "空头", "崩溃",
]
POSITIVE_KW = [
    "上涨", "突破", "创新高", "上调", "超预期", "盈利", "强劲",
    "看涨", "买入", "回购", "增长", "利好", "涨价", "扩张",
    "超预期", "大涨", "新高", "反弹", "做多", "多头",
]

_WSCN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://wallstreetcn.com/",
    "Origin":  "https://wallstreetcn.com",
    "Accept":  "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_vader = SentimentIntensityAnalyzer()


def _keyword_score(text: str) -> float:
    neg = sum(1 for kw in NEGATIVE_KW if kw in text)
    pos = sum(1 for kw in POSITIVE_KW if kw in text)
    total = neg + pos
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def _is_relevant(text: str, symbol: str) -> bool:
    keywords = [symbol] + TICKER_CN_MAP.get(symbol.upper(), [])
    text_upper = text.upper()
    return any(kw.upper() in text_upper for kw in keywords)


def fetch_wscn_news(symbol: str) -> list[dict]:
    """从华尔街见闻抓取与 symbol 相关的新闻（快讯流 + 文章）。"""
    articles: list[dict] = []

    # ── 快讯流 (lives) ──
    try:
        resp = requests.get(
            "https://api-prod.wallstreetcn.com/apiv1/content/lives",
            params={"channel": "us-stock", "limit": 50},
            headers=_WSCN_HEADERS,
            timeout=12,
        )
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("items", [])
            for item in items:
                content = item.get("content", "") or ""
                if not _is_relevant(content, symbol):
                    continue
                score = _keyword_score(content)
                if score == 0:
                    score = _vader.polarity_scores(content)["compound"]
                articles.append({
                    "title": (content[:100] + "…") if len(content) > 100 else content,
                    "content": content,
                    "publishedAt": item.get("created_at", ""),
                    "source": "wallstreetcn",
                    "link": f"https://wallstreetcn.com/articles/{item.get('id', '')}",
                    "sentimentScore": round(float(score), 3),
                })
    except Exception:
        pass

    # ── 文章搜索（按中文关键词）──
    if len(articles) < 3:
        keywords = [symbol] + TICKER_CN_MAP.get(symbol.upper(), [])
        for kw in keywords[:3]:
            if len(articles) >= 8:
                break
            try:
                resp = requests.get(
                    "https://api-prod.wallstreetcn.com/apiv1/content/articles",
                    params={"tag": kw, "limit": 5},
                    headers=_WSCN_HEADERS,
                    timeout=12,
                )
                if resp.status_code != 200:
                    continue
                items = resp.json().get("data", {}).get("items", [])
                for item in items:
                    title = item.get("title", "")
                    if not title:
                        continue
                    score = _keyword_score(title)
                    if score == 0:
                        score = _vader.polarity_scores(title)["compound"]
                    articles.append({
                        "title": title,
                        "content": item.get("summary", "")[:200],
                        "publishedAt": item.get("created_at", ""),
                        "source": "wallstreetcn",
                        "link": item.get("uri", ""),
                        "sentimentScore": round(float(score), 3),
                    })
            except Exception:
                continue

    return articles[:8]


def fetch_fmp_news(symbol: str) -> list[dict]:
    """从 FMP 获取新闻（回退方案）。"""
    if not FMP_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://financialmodelingprep.com/api/v3/stock_news",
            params={"tickers": symbol, "limit": 10, "apikey": FMP_API_KEY},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        articles = []
        for item in resp.json():
            title = item.get("title", "")
            if not title:
                continue
            score = _vader.polarity_scores(title)["compound"]
            articles.append({
                "title": title,
                "content": (item.get("text", "") or "")[:200],
                "publishedAt": item.get("publishedDate", ""),
                "source": "fmp",
                "link": item.get("url", ""),
                "sentimentScore": round(score, 3),
            })
        return articles[:8]
    except Exception:
        return []


def analyze_news_risk(articles: list[dict], strategy: str) -> dict:
    """根据文章情绪和关键词输出 riskLevel / riskScore / overallSentiment。"""
    if not articles:
        return {
            "riskLevel": "低",
            "riskScore": 0.0,
            "overallSentiment": "中性",
            "articleCount": 0,
            "topRiskKeywords": [],
        }

    scores = [a["sentimentScore"] for a in articles]
    avg_score = sum(scores) / len(scores)

    combined = " ".join(
        (a.get("title", "") + " " + a.get("content", "")) for a in articles
    )
    found_neg = [kw for kw in NEGATIVE_KW if kw in combined]
    found_pos = [kw for kw in POSITIVE_KW if kw in combined]

    neg_count = len(found_neg)
    # 负面关键词每个 +1.5 分，平均情绪偏负面再加分
    risk_score = min(10.0, neg_count * 1.5 + max(0.0, -avg_score * 5))

    # 卖出期权（sell_put / sell_call）：负面新闻直接威胁仓位
    if "sell" in strategy:
        if risk_score >= 5 or avg_score < -0.25:
            risk_level = "高"
        elif risk_score >= 2.5 or avg_score < -0.08:
            risk_level = "中"
        else:
            risk_level = "低"
    else:
        # 买入期权：负面新闻对 put 有利，对 call 不利；统一用情绪判断
        if avg_score < -0.25 or risk_score >= 5:
            risk_level = "高"
        elif avg_score < -0.08 or risk_score >= 2.5:
            risk_level = "中"
        else:
            risk_level = "低"

    if avg_score > 0.15:
        overall_sentiment = "看涨"
    elif avg_score < -0.15:
        overall_sentiment = "看跌"
    else:
        overall_sentiment = "中性"

    return {
        "riskLevel": risk_level,
        "riskScore": round(risk_score, 1),
        "overallSentiment": overall_sentiment,
        "articleCount": len(articles),
        "topRiskKeywords": found_neg[:5],
    }
