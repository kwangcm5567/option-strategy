"""
/api/payoff — 给定腿组合，返回盈亏图曲线 + 情景矩阵。
"""
from pydantic import BaseModel, Field
from fastapi import APIRouter

from services import payoff

router = APIRouter()


class Leg(BaseModel):
    action: str        # 'buy' | 'sell'
    type: str          # 'call' | 'put'
    strike: float
    premium: float
    iv: float = Field(default=0.3)
    quantity: int = Field(default=1, ge=1)


class PayoffRequest(BaseModel):
    legs: list[Leg]
    spot: float
    dte: int = Field(ge=0)
    priceRangePct: float = Field(default=0.30, gt=0, le=1.0)


@router.post("/api/payoff")
def compute_payoff(req: PayoffRequest):
    legs = [l.model_dump() for l in req.legs]
    result = payoff.compute(legs, req.spot, req.dte, price_range_pct=req.priceRangePct)
    result["scenario"] = payoff.scenario_grid(legs, req.spot, req.dte)
    return result
