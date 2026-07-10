"""
/api/positions  —  持仓 CRUD + 实时 PnL + 组合 Greeks（SQLite 存储）
"""
import math
import os
from datetime import datetime
from typing import Optional

import requests
import yfinance as yf

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_conn
from services.greeks import calc_black_scholes

router = APIRouter()

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
_RISK_FREE_RATE = 0.05

STRATEGY_LABELS = {
    "sell_put": "卖出 Put",
    "buy_call": "买入 Call",
    "sell_call": "卖出 Call",
    "buy_put": "买入 Put",
}

# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _ncdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _bs_price(S: float, K: float, T: float, sigma: float, option_type: str, r: float = _RISK_FREE_RATE) -> float:
    """Black-Scholes 期权理论价格（per share）。"""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "put":
        price = K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)
    else:
        price = S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return max(0.0, price)


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


def _hist_vol(symbol: str) -> float:
    """21 日历史波动率（年化），用作 IV 近似。"""
    try:
        hist = yf.Ticker(symbol).history(period="3mo")
        if hist.empty or len(hist) < 22:
            return 0.30
        returns = hist["Close"].pct_change().dropna()
        return float(returns.tail(21).std() * math.sqrt(252))
    except Exception:
        return 0.30


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
        conn.commit()

    return {"options_imported": opt_added, "stocks_imported": stock_added, "skipped": parsed["skipped"]}


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


# ── 实时 PnL ─────────────────────────────────────────────────────────────────

@router.get("/api/portfolio/pnl")
def portfolio_pnl():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE status='open' OR status IS NULL ORDER BY expiration_date ASC"
        ).fetchall()
    positions = [dict(r) for r in rows]
    if not positions:
        return {"data": []}

    symbols = list({p["symbol"] for p in positions})
    prices = _fetch_current_prices(symbols)
    today = datetime.now().date()
    results = []

    for pos in positions:
        sym = pos["symbol"]
        S = prices.get(sym)
        if not S:
            results.append({"id": pos["id"], "error": "无法获取当前价格"})
            continue

        exp = datetime.strptime(pos["expiration_date"], "%Y-%m-%d").date()
        dte = max(1, (exp - today).days)
        sigma = _hist_vol(sym)
        T = dte / 365.0
        option_type = "put" if "put" in pos["strategy"] else "call"

        current_premium = _bs_price(S, pos["strike"], T, sigma, option_type)

        bs = calc_black_scholes(
            current_price=S, strike=pos["strike"], dte=dte, iv=sigma, option_type=option_type
        )

        is_sell = pos["strategy"].startswith("sell_")
        qty = pos["quantity"]
        entry = pos["premium"]
        unrealized = round(
            (entry - current_premium) * qty * 100 if is_sell
            else (current_premium - entry) * qty * 100,
            2,
        )
        max_profit = entry * qty * 100
        profit_progress = round(unrealized / max_profit * 100, 1) if max_profit > 0 and is_sell else None

        results.append({
            "id": pos["id"],
            "symbol": sym,
            "currentPrice": round(S, 2),
            "currentPremium": round(current_premium, 4),
            "unrealizedPnl": unrealized,
            "unrealizedPnlPct": round(unrealized / max_profit * 100, 1) if max_profit > 0 else 0,
            "profitProgress": profit_progress,
            "theta": bs.get("theta_day") if bs else None,
            "delta": bs.get("delta") if bs else None,
        })

    return {"data": results}


# ── 组合 Greeks ───────────────────────────────────────────────────────────────

@router.get("/api/portfolio/greeks")
def portfolio_greeks():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE status='open' OR status IS NULL"
        ).fetchall()
    positions = [dict(r) for r in rows]
    if not positions:
        return {"data": {"totalDelta": 0, "totalTheta": 0, "totalVega": 0,
                         "dailyThetaIncome": 0, "totalCapitalAtRisk": 0,
                         "sellPutCount": 0, "buyCallCount": 0}}

    symbols = list({p["symbol"] for p in positions})
    prices = _fetch_current_prices(symbols)
    today = datetime.now().date()
    total_delta = total_theta = total_vega = total_capital = 0.0
    sell_put_count = buy_call_count = 0

    for pos in positions:
        sym = pos["symbol"]
        S = prices.get(sym, pos["strike"])
        exp = datetime.strptime(pos["expiration_date"], "%Y-%m-%d").date()
        dte = max(1, (exp - today).days)
        sigma = _hist_vol(sym)
        option_type = "put" if "put" in pos["strategy"] else "call"

        bs = calc_black_scholes(current_price=S, strike=pos["strike"], dte=dte, iv=sigma, option_type=option_type)
        if not bs:
            continue

        qty = pos["quantity"]
        mult = qty * 100
        sign = -1 if pos["strategy"].startswith("sell_") else 1

        total_delta += bs["delta"] * mult * sign
        total_theta += bs["theta_day"] * mult * sign
        total_vega  += bs["vega_1pct"] * mult * sign

        if pos["strategy"] == "sell_put":
            sell_put_count += qty
            total_capital += pos["strike"] * mult
        elif pos["strategy"] == "buy_call":
            buy_call_count += qty
            total_capital += pos["premium"] * mult

    return {
        "data": {
            "totalDelta": round(total_delta, 3),
            "totalTheta": round(total_theta, 2),
            "totalVega":  round(total_vega, 2),
            "dailyThetaIncome": round(-total_theta, 2),
            "totalCapitalAtRisk": round(total_capital, 2),
            "sellPutCount": sell_put_count,
            "buyCallCount": buy_call_count,
        }
    }
