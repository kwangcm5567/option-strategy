"""
/api/scan-spreads — 多腿价差扫描（垂直价差 / Iron Condor / 跨式）。
"""
from fastapi import APIRouter, Query

from services import spreads
from services import cache as cache_svc

router = APIRouter()


@router.get("/api/scan-spreads")
def scan_spreads(
    strategy: str = Query(default="bull_put"),
    dte_min: int = Query(default=20, ge=1),
    dte_max: int = Query(default=55, le=120),
):
    cache_key = f"spreads:{strategy}:{dte_min}:{dte_max}"
    cached = cache_svc.get(cache_key, ttl_seconds=1800)
    if cached is not None:
        return {"strategy": strategy, "results": cached, "cached": True}

    results = spreads.scan_spreads(strategy, dte_min, dte_max)
    cache_svc.set(cache_key, results)
    return {"strategy": strategy, "results": results, "cached": False}
