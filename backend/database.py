"""
SQLite 持仓数据库（使用 Python 内置 sqlite3，无需额外依赖）。
数据库文件存放在 backend/positions.db。
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "positions.db"


def get_conn() -> sqlite3.Connection:
    # timeout：写锁被占用时最多等 10s 再报错（替代立刻 "database is locked"）
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row   # 让查询结果可以用列名访问
    # WAL：读写不互斥，扫描并发期间其它请求不再被锁死
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库，创建 positions 表（若不存在）并迁移平仓字段。"""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT    NOT NULL,
                strategy        TEXT    NOT NULL,
                strike          REAL    NOT NULL,
                premium         REAL    NOT NULL,
                quantity        INTEGER NOT NULL DEFAULT 1,
                expiration_date TEXT    NOT NULL,
                open_date       TEXT    NOT NULL,
                notes           TEXT,
                created_at      TEXT    DEFAULT (datetime('now')),
                status          TEXT    NOT NULL DEFAULT 'open',
                exit_premium    REAL,
                exit_date       TEXT,
                realized_pnl    REAL,
                close_reason    TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_holdings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT    NOT NULL UNIQUE,
                quantity    INTEGER NOT NULL,
                avg_price   REAL    NOT NULL,
                notes       TEXT,
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        # 为旧表补齐新列（迁移兼容）
        existing = {row[1] for row in conn.execute("PRAGMA table_info(positions)").fetchall()}
        for col, definition in [
            ("status",           "TEXT NOT NULL DEFAULT 'open'"),
            ("exit_premium",     "REAL"),
            ("exit_date",        "TEXT"),
            ("realized_pnl",     "REAL"),
            ("close_reason",     "TEXT"),
            ("wheel_cycle_id",   "INTEGER"),
            ("protection_strike","REAL"),
        ]:
            if col not in existing:
                conn.execute(f"ALTER TABLE positions ADD COLUMN {col} {definition}")
        conn.commit()
