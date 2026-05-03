"""
GET /api/news/{symbol}  —  华尔街见闻新闻风险分析
"""
from fastapi import APIRouter

from services.news import fetch_wscn_news, fetch_fmp_news, analyze_news_risk
from services import cache as cache_svc

router = APIRouter()


@router.get("/api/news/{symbol}")
def get_news(symbol: str, strategy: str = "sell_put"):
    sym = symbol.upper()
    cache_key = f"news:{sym}"

    # 文章列表缓存 30 分钟
    cached_articles = cache_svc.get(cache_key, ttl_seconds=1800)
    if cached_articles is not None:
        analysis = analyze_news_risk(cached_articles["articles"], strategy)
        return {
            "symbol": sym,
            "source": cached_articles["source"],
            "articles": cached_articles["articles"],
            "cached": True,
            **analysis,
        }

    articles = fetch_wscn_news(sym)
    source = "wallstreetcn"

    if not articles:
        articles = fetch_fmp_news(sym)
        source = "fmp" if articles else "none"

    cache_svc.set(cache_key, {"articles": articles, "source": source})

    analysis = analyze_news_risk(articles, strategy)
    return {
        "symbol": sym,
        "source": source,
        "articles": articles,
        "cached": False,
        **analysis,
    }
