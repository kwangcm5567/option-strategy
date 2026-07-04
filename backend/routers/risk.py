"""
/api/portfolio/risk — Beta 加权 Delta、相关性/集中度、VaR、情景压力测试。
"""
from fastapi import APIRouter

from services import risk

router = APIRouter()


@router.get("/api/portfolio/risk")
def portfolio_risk():
    return {"data": risk.analyze_portfolio()}
