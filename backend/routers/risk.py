"""
/api/portfolio/risk — Beta 加权 Delta、相关性/集中度、VaR、情景压力测试。

缓存 key 带持仓指纹：持仓一变 key 就变，旧缓存自然失效，无需手动清。
"""
from fastapi import APIRouter

from database import get_conn
from services import risk
from services import cache as cache_svc

router = APIRouter()


def _positions_fingerprint() -> str:
    with get_conn() as conn:
        pos_row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(strike * quantity + premium), 0)
            FROM positions WHERE status='open' OR status IS NULL
            """
        ).fetchone()
        stock_row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(quantity * avg_price), 0)
            FROM stock_holdings
            """
        ).fetchone()
        snap_row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM account_snapshots").fetchone()
    return (
        f"{pos_row[0]}:{pos_row[1]}:{round(pos_row[2], 4)}:"
        f"{stock_row[0]}:{stock_row[1]}:{round(stock_row[2], 4)}:{snap_row[0]}"
    )


@router.get("/api/portfolio/risk")
def portfolio_risk():
    cache_key = f"risk:{_positions_fingerprint()}"
    cached = cache_svc.get(cache_key, ttl_seconds=900)
    if cached is not None:
        return {"data": cached, "cached": True}

    result = risk.analyze_portfolio()
    cache_svc.set(cache_key, result)
    return {"data": result, "cached": False}
