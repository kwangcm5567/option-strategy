"""DB 集成测试：用 monkeypatch 隔离出临时 sqlite 文件，不碰真实 positions.db。"""
import database


def test_init_db_creates_account_snapshots_table(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.init_db()

    with database.get_conn() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(account_snapshots)").fetchall()}

    assert cols == {
        "id", "imported_at", "net_asset_value", "total_market_value",
        "total_margin_requirement", "implied_margin_loan", "leverage",
    }
