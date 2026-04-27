"""
/api/positions  —  持仓 CRUD（SQLite 存储）
"""
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_conn

router = APIRouter()

STRATEGY_LABELS = {
    "sell_put": "卖出 Put",
    "buy_call": "买入 Call",
    "sell_call": "卖出 Call",
    "buy_put": "买入 Put",
}


class PositionIn(BaseModel):
    symbol: str
    strategy: str
    strike: float
    premium: float
    quantity: int = 1
    expiration_date: str   # YYYY-MM-DD
    open_date: str         # YYYY-MM-DD
    notes: str = ""


@router.get("/api/positions")
def list_positions():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions ORDER BY expiration_date ASC"
        ).fetchall()
    return {"data": [dict(r) for r in rows]}


@router.post("/api/positions")
def add_position(pos: PositionIn):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO positions (symbol, strategy, strike, premium, quantity,
                                   expiration_date, open_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pos.symbol.upper(), pos.strategy, pos.strike, pos.premium,
                pos.quantity, pos.expiration_date, pos.open_date, pos.notes,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM positions WHERE id = ?", (new_id,)).fetchone()
    return {"data": dict(row)}


@router.delete("/api/positions/{position_id}")
def delete_position(position_id: int):
    with get_conn() as conn:
        affected = conn.execute(
            "DELETE FROM positions WHERE id = ?", (position_id,)
        ).rowcount
        conn.commit()
    if affected == 0:
        raise HTTPException(status_code=404, detail="找不到该持仓记录")
    return {"ok": True}


@router.patch("/api/positions/{position_id}")
def update_position(position_id: int, pos: PositionIn):
    with get_conn() as conn:
        affected = conn.execute(
            """
            UPDATE positions
            SET symbol=?, strategy=?, strike=?, premium=?, quantity=?,
                expiration_date=?, open_date=?, notes=?
            WHERE id=?
            """,
            (
                pos.symbol.upper(), pos.strategy, pos.strike, pos.premium,
                pos.quantity, pos.expiration_date, pos.open_date, pos.notes,
                position_id,
            ),
        ).rowcount
        conn.commit()
    if affected == 0:
        raise HTTPException(status_code=404, detail="找不到该持仓记录")
    return {"ok": True}
