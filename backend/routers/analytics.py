"""
收入分析与绩效归因 API。
"""
from fastapi import APIRouter
from database import get_conn

router = APIRouter(prefix="/api/analytics")


def _profit_factor(gross_profit: float, gross_loss: float) -> float | None:
    if gross_loss and gross_loss > 0:
        return round(gross_profit / gross_loss, 2)
    return None


@router.get("/monthly")
def get_monthly_income():
    """按月汇总已实现盈亏，用于绘制月度收入柱状图。"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                strftime('%Y-%m', exit_date)                                      AS month,
                SUM(realized_pnl)                                                 AS total_pnl,
                COUNT(*)                                                          AS trade_count,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)               AS wins,
                SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END)    AS gross_profit,
                SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END) AS gross_loss,
                SUM(premium * quantity * 100)                                     AS premium_collected
            FROM positions
            WHERE status = 'closed' AND exit_date IS NOT NULL
            GROUP BY month
            ORDER BY month ASC
        """).fetchall()

    monthly = []
    for row in rows:
        month, total_pnl, count, wins, gp, gl, premium = row
        monthly.append({
            "month": month,
            "totalPnl": round(total_pnl or 0, 2),
            "tradeCount": count,
            "winRate": round(wins / count * 100, 1) if count else 0,
            "grossProfit": round(gp or 0, 2),
            "grossLoss": round(gl or 0, 2),
            "profitFactor": _profit_factor(gp or 0, gl or 0),
            "premiumCollected": round(premium or 0, 2),
        })

    return {"data": monthly}


@router.get("/performance")
def get_performance():
    """按策略和标的统计绩效，含利润因子、平均盈亏、胜率。"""
    with get_conn() as conn:
        strat_rows = conn.execute("""
            SELECT
                strategy,
                COUNT(*)                                                              AS trades,
                SUM(realized_pnl)                                                     AS total_pnl,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)                   AS wins,
                AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE NULL END)      AS avg_win,
                AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE NULL END)      AS avg_loss,
                SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END)        AS gross_profit,
                SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END)   AS gross_loss
            FROM positions WHERE status = 'closed'
            GROUP BY strategy
            ORDER BY total_pnl DESC
        """).fetchall()

        sym_rows = conn.execute("""
            SELECT
                symbol,
                COUNT(*)                                                              AS trades,
                SUM(realized_pnl)                                                     AS total_pnl,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)                   AS wins,
                AVG(realized_pnl)                                                     AS avg_pnl,
                SUM(premium * quantity * 100)                                         AS premium_collected
            FROM positions WHERE status = 'closed'
            GROUP BY symbol
            ORDER BY total_pnl DESC
            LIMIT 20
        """).fetchall()

        summary_row = conn.execute("""
            SELECT
                COUNT(*),
                SUM(realized_pnl),
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END),
                SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END),
                SUM(premium * quantity * 100)
            FROM positions WHERE status = 'closed'
        """).fetchone()

        open_row = conn.execute("""
            SELECT
                COUNT(*),
                SUM(premium * quantity * 100)
            FROM positions WHERE status = 'open'
        """).fetchone()

    total_trades, total_pnl, total_wins, gp, gl, total_premium = summary_row
    open_count, open_premium = open_row

    by_strategy = []
    for row in strat_rows:
        strat, trades, total, wins, avg_win, avg_loss, rgp, rgl = row
        by_strategy.append({
            "strategy": strat,
            "trades": trades,
            "totalPnl": round(total or 0, 2),
            "winRate": round(wins / trades * 100, 1) if trades else 0,
            "avgWin": round(avg_win or 0, 2),
            "avgLoss": round(avg_loss or 0, 2),
            "profitFactor": _profit_factor(rgp or 0, rgl or 0),
        })

    by_symbol = []
    for row in sym_rows:
        sym, trades, total, wins, avg_pnl, premium = row
        by_symbol.append({
            "symbol": sym,
            "trades": trades,
            "totalPnl": round(total or 0, 2),
            "winRate": round(wins / trades * 100, 1) if trades else 0,
            "avgPnl": round(avg_pnl or 0, 2),
            "premiumCollected": round(premium or 0, 2),
        })

    return {
        "summary": {
            "totalTrades": total_trades or 0,
            "totalPnl": round(total_pnl or 0, 2),
            "overallWinRate": round(total_wins / total_trades * 100, 1) if total_trades else 0,
            "profitFactor": _profit_factor(gp or 0, gl or 0),
            "totalPremiumCollected": round(total_premium or 0, 2),
            "openPositions": open_count or 0,
            "openPremiumAtRisk": round(open_premium or 0, 2),
        },
        "byStrategy": by_strategy,
        "bySymbol": by_symbol,
    }


@router.get("/wheel-cycles")
def get_wheel_cycles():
    """返回所有 Wheel 循环（按 wheel_cycle_id 分组）。"""
    with get_conn() as conn:
        # 检查列是否存在
        cols = {row[1] for row in conn.execute("PRAGMA table_info(positions)").fetchall()}
        if "wheel_cycle_id" not in cols:
            return {"data": []}

        rows = conn.execute("""
            SELECT id, symbol, strategy, strike, premium, quantity,
                   expiration_date, open_date, status,
                   exit_premium, exit_date, realized_pnl, close_reason,
                   wheel_cycle_id, protection_strike
            FROM positions
            WHERE wheel_cycle_id IS NOT NULL
            ORDER BY wheel_cycle_id, open_date ASC
        """).fetchall()

    cycles: dict = {}
    for row in rows:
        (pid, symbol, strategy, strike, premium, qty,
         exp_date, open_date, status, exit_prem, exit_date,
         realized_pnl, close_reason, cycle_id, prot_strike) = tuple(row)
        if cycle_id not in cycles:
            cycles[cycle_id] = {
                "cycleId": cycle_id,
                "symbol": symbol,
                "legs": [],
                "totalPremium": 0.0,
                "status": "active",
            }
        premium_income = (premium - (exit_prem or 0)) * qty * 100
        cycles[cycle_id]["totalPremium"] = round(
            cycles[cycle_id]["totalPremium"] + (realized_pnl or premium_income), 2
        )
        cycles[cycle_id]["legs"].append({
            "id": pid,
            "strategy": strategy,
            "strike": strike,
            "premium": premium,
            "quantity": qty,
            "expirationDate": exp_date,
            "openDate": open_date,
            "status": status,
            "exitPremium": exit_prem,
            "exitDate": exit_date,
            "realizedPnl": realized_pnl,
            "closeReason": close_reason,
        })
        if status == "open":
            cycles[cycle_id]["status"] = "active"
        elif close_reason in ("assignment", "exercised") and status == "closed":
            cycles[cycle_id]["status"] = "assigned"

    return {"data": list(cycles.values())}
