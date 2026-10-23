"""
/api/positions  —  持仓 CRUD + 实时 PnL + 组合 Greeks（SQLite 存储）
"""
import os
from typing import Optional

import requests
import yfinance as yf

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import get_conn

router = APIRouter()

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")

STRATEGY_LABELS = {
    "sell_put": "卖出 Put",
    "buy_call": "买入 Call",
    "sell_call": "卖出 Call",
    "buy_put": "买入 Put",
}

# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _fetch_current_prices(symbols: list[str]) -> dict[str, float]:
    """FMP batch quote → yfinance fallback。"""
    prices: dict[str, float] = {}
    if FMP_API_KEY and symbols:
        try:
            resp = requests.get(
                "https://financialmodelingprep.com/api/v3/quote-short/" + ",".join(symbols),
                params={"apikey": FMP_API_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                for item in resp.json():
                    sym = item.get("symbol", "")
                    p = item.get("price")
                    if sym and p:
                        prices[sym] = float(p)
        except Exception:
            pass

    for sym in [s for s in symbols if s not in prices]:
        try:
            hist = yf.Ticker(sym).history(period="2d")
            if not hist.empty:
                prices[sym] = float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return prices


# ── CRUD 模型 ─────────────────────────────────────────────────────────────────

class PositionIn(BaseModel):
    symbol: str
    strategy: str
    strike: float
    premium: float
    quantity: int = 1
    expiration_date: str
    open_date: str
    notes: str = ""
    wheel_cycle_id: Optional[int] = None
    protection_strike: Optional[float] = None


class ClosePositionIn(BaseModel):
    exit_premium: float
    exit_date: str
    close_reason: str = "manual"


# ── CRUD 端点 ─────────────────────────────────────────────────────────────────

@router.get("/api/positions")
def list_positions():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM positions ORDER BY expiration_date ASC").fetchall()
    return {"data": [dict(r) for r in rows]}


@router.post("/api/positions")
def add_position(pos: PositionIn):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO positions (symbol, strategy, strike, premium, quantity,
                                   expiration_date, open_date, notes,
                                   wheel_cycle_id, protection_strike)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pos.symbol.upper(), pos.strategy, pos.strike, pos.premium,
             pos.quantity, pos.expiration_date, pos.open_date, pos.notes,
             pos.wheel_cycle_id, pos.protection_strike),
        )
        conn.commit()
        new_id = cur.lastrowid
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM positions WHERE id = ?", (new_id,)).fetchone()
    return {"data": dict(row)}


@router.delete("/api/positions/{position_id}")
def delete_position(position_id: int):
    with get_conn() as conn:
        affected = conn.execute("DELETE FROM positions WHERE id = ?", (position_id,)).rowcount
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
            (pos.symbol.upper(), pos.strategy, pos.strike, pos.premium,
             pos.quantity, pos.expiration_date, pos.open_date, pos.notes,
             position_id),
        ).rowcount
        conn.commit()
    if affected == 0:
        raise HTTPException(status_code=404, detail="找不到该持仓记录")
    return {"ok": True}


@router.post("/api/positions/{position_id}/close")
def close_position(position_id: int, body: ClosePositionIn):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="找不到该持仓记录")
        pos = dict(row)
        is_sell = pos["strategy"].startswith("sell_")
        qty = pos["quantity"]
        realized = round(
            (pos["premium"] - body.exit_premium) * qty * 100 if is_sell
            else (body.exit_premium - pos["premium"]) * qty * 100,
            2,
        )
        conn.execute(
            "UPDATE positions SET status='closed', exit_premium=?, exit_date=?, realized_pnl=?, close_reason=? WHERE id=?",
            (body.exit_premium, body.exit_date, realized, body.close_reason, position_id),
        )
        conn.commit()
    return {"ok": True, "realized_pnl": realized}


@router.post("/api/positions/{position_id}/assign-to-wheel")
def assign_to_wheel(position_id: int):
    """将被行权的 Put 关联到一个新的 Wheel 循环，返回 wheel_cycle_id。
    如果该 Put 已有 wheel_cycle_id 则直接返回现有 ID。"""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="找不到该持仓记录")
        pos = dict(row)
        if pos.get("wheel_cycle_id"):
            return {"wheel_cycle_id": pos["wheel_cycle_id"]}
        # 新建 cycle：以 position_id 本身作为 cycle_id（简单唯一性保证）
        cycle_id = position_id
        conn.execute(
            "UPDATE positions SET wheel_cycle_id=? WHERE id=?",
            (cycle_id, position_id),
        )
        conn.commit()
    return {"wheel_cycle_id": cycle_id}


# ── 老虎 CSV 导入 + 正股持仓 ──────────────────────────────────────────────────

class ImportIn(BaseModel):
    content: str


@router.post("/api/positions/import-tiger")
def import_tiger(body: ImportIn):
    from services import tiger_import

    parsed = tiger_import.parse(body.content)
    opt_added = 0
    stock_added = 0
    snapshot_saved = False

    with get_conn() as conn:
        for o in parsed["options"]:
            dup = conn.execute(
                "SELECT 1 FROM positions WHERE symbol=? AND strategy=? AND strike=? AND expiration_date=? AND (status='open' OR status IS NULL)",
                (o["symbol"], o["strategy"], o["strike"], o["expiration_date"]),
            ).fetchone()
            if dup:
                continue
            conn.execute(
                """
                INSERT INTO positions (symbol, strategy, strike, premium, quantity,
                                       expiration_date, open_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (o["symbol"], o["strategy"], o["strike"], o["premium"], o["quantity"],
                 o["expiration_date"], o["open_date"], o["notes"]),
            )
            opt_added += 1
        for s in parsed["stocks"]:
            conn.execute(
                """
                INSERT INTO stock_holdings (symbol, quantity, avg_price, notes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET quantity=excluded.quantity, avg_price=excluded.avg_price
                """,
                (s["symbol"], s["quantity"], s["avg_price"], s["notes"]),
            )
            stock_added += 1
        snap = parsed.get("account_snapshot")
        if snap:
            conn.execute(
                """
                INSERT INTO account_snapshots
                    (net_asset_value, total_market_value, total_margin_requirement,
                     implied_margin_loan, leverage)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snap["net_asset_value"], snap["total_market_value"],
                 snap["total_margin_requirement"], snap["implied_margin_loan"],
                 snap["leverage"]),
            )
            snapshot_saved = True
        conn.commit()

    return {"options_imported": opt_added, "stocks_imported": stock_added, "skipped": parsed["skipped"], "account_snapshot_saved": snapshot_saved}


@router.get("/api/stocks")
def list_stocks():
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM stock_holdings ORDER BY symbol ASC").fetchall()]
    prices = _fetch_current_prices([r["symbol"] for r in rows]) if rows else {}
    for r in rows:
        cur = prices.get(r["symbol"])
        r["current_price"] = round(cur, 2) if cur else None
        if cur:
            r["market_value"] = round(cur * r["quantity"], 2)
            cost = r["avg_price"] * r["quantity"]
            r["pnl"] = round((cur - r["avg_price"]) * r["quantity"], 2)
            r["pnl_pct"] = round((cur - r["avg_price"]) / r["avg_price"] * 100, 2) if r["avg_price"] else None
        else:
            r["market_value"] = r["pnl"] = r["pnl_pct"] = None
    return {"data": rows}


@router.delete("/api/stocks/{stock_id}")
def delete_stock(stock_id: int):
    with get_conn() as conn:
        affected = conn.execute("DELETE FROM stock_holdings WHERE id = ?", (stock_id,)).rowcount
        conn.commit()
    if affected == 0:
        raise HTTPException(status_code=404, detail="找不到该正股记录")
    return {"ok": True}


# ── 财报提醒 ─────────────────────────────────────────────────────────────────

@router.get("/api/positions/earnings-alerts")
def positions_earnings_alerts():
    """持仓标的的下次财报日（{symbol: date}），用于标记财报落在到期日前的仓位。"""
    from routers.earnings import _fetch_fmp_earnings, _get_next_earnings_yf
    from services import cache as cache_svc
    from services.scanner import ETFS

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM positions WHERE status='open' OR status IS NULL"
        ).fetchall()
    symbols = sorted({r[0] for r in rows} - ETFS)
    if not symbols:
        return {"data": {}}

    cache_key = f"pos-earnings:{','.join(symbols)}"
    cached = cache_svc.get(cache_key, ttl_seconds=7200)
    if cached is not None:
        return {"data": cached, "cached": True}

    fmp_map = _fetch_fmp_earnings()
    result: dict[str, str] = {}
    for sym in symbols:
        if sym in fmp_map:
            result[sym] = fmp_map[sym]
            continue
        dt = _get_next_earnings_yf(yf.Ticker(sym))
        if dt:
            result[sym] = dt.strftime("%Y-%m-%d")
    cache_svc.set(cache_key, result)
    return {"data": result, "cached": False}


# ── 同一行情快照驱动持仓盈亏与 Greeks ──────────────────────────────────────

def _portfolio_snapshot(force_refresh: bool = False) -> dict:
    from services.position_quotes import build_snapshot
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE status='open' OR status IS NULL ORDER BY expiration_date ASC"
        ).fetchall()
    return build_snapshot([dict(row) for row in rows], force_refresh=force_refresh)


@router.get("/api/portfolio/snapshot")
def portfolio_snapshot(force_refresh: bool = False):
    return JSONResponse(_portfolio_snapshot(force_refresh), headers={"Cache-Control": "no-store"})


@router.get("/api/portfolio/pnl")
def portfolio_pnl(force_refresh: bool = False):
    snapshot = _portfolio_snapshot(force_refresh=force_refresh)
    return JSONResponse({"data": snapshot["data"], "fetchedAt": snapshot["fetchedAt"]},
                        headers={"Cache-Control": "no-store"})


@router.get("/api/portfolio/greeks")
def portfolio_greeks(force_refresh: bool = False):
    snapshot = _portfolio_snapshot(force_refresh=force_refresh)
    return JSONResponse({"data": snapshot["greeks"], "fetchedAt": snapshot["fetchedAt"]},
                        headers={"Cache-Control": "no-store"})
