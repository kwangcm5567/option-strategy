"""
/api/vol-surface/{symbol} — IV 期限结构 + skew + 真实 IV Rank。
"""
from fastapi import APIRouter, HTTPException

from services import vol
from services import cache as cache_svc

router = APIRouter()


@router.get("/api/vol-surface/{symbol}")
def vol_surface(symbol: str):
    sym = symbol.upper()
    cache_key = f"vol:{sym}"
    cached = cache_svc.get(cache_key, ttl_seconds=900)
    if cached is not None:
        return cached

    result = vol.analyze(sym)
    if result is None:
        raise HTTPException(status_code=404, detail=f"无法获取 {sym} 的期权链数据")

    cache_svc.set(cache_key, result)
    return result
