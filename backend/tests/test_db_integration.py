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


def test_import_tiger_persists_account_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test2.db")
    database.init_db()

    from routers.positions import import_tiger, ImportIn

    csv_text = (
        "Symbol,Instrument,Option Style,Expiry,Strike,Holdings,Avg Price,"
        "Market Value,Position Percentage,Margin Amount\n"
        '="QQQ",Stock,,,,402,694.41,274927.80,274.12%,68731.95\n'
    )
    result = import_tiger(ImportIn(content=csv_text))

    assert result["stocks_imported"] == 1
    assert result["account_snapshot_saved"] is True

    with database.get_conn() as conn:
        row = conn.execute("SELECT * FROM account_snapshots").fetchone()
    assert row is not None
    assert row["net_asset_value"] > 0


def test_fingerprint_changes_when_stock_added(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test3.db")
    database.init_db()

    from routers.risk import _positions_fingerprint

    fp1 = _positions_fingerprint()
    with database.get_conn() as conn:
        conn.execute(
            "INSERT INTO stock_holdings (symbol, quantity, avg_price) VALUES ('QQQ', 10, 600.0)"
        )
        conn.commit()
    fp2 = _positions_fingerprint()

    assert fp1 != fp2
