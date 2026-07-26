"""tiger_import 纯函数单测：CSV 解析 + 账户快照反推，无网络/DB 依赖。"""
from services.tiger_import import parse, compute_account_snapshot

_SAMPLE_CSV = (
    "Symbol,Instrument,Option Style,Expiry,Strike,Holdings,Avg Price,"
    "Market Value,Position Percentage,Margin Amount\n"
    '="AMD",Stock,,,,14,203.15,7301.15,7.28%,1825.29\n'
    '="QQQ",Stock,,,,402,694.41,274927.80,274.12%,68731.95\n'
)


def test_compute_account_snapshot_derives_median_nav():
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(_SAMPLE_CSV)))
    snap = compute_account_snapshot(rows)

    assert snap is not None
    # AMD: 7301.15/0.0728≈100290.8；QQQ: 274927.80/2.7412≈100291.7；中位数取二者平均
    assert abs(snap["net_asset_value"] - 100291) < 5
    assert snap["total_market_value"] == round(7301.15 + 274927.80, 2)
    assert snap["total_margin_requirement"] == round(1825.29 + 68731.95, 2)
    assert snap["implied_margin_loan"] == round(snap["total_market_value"] - snap["net_asset_value"], 2)
    assert snap["leverage"] > 1.0


def test_compute_account_snapshot_none_when_columns_missing():
    rows = [{"Symbol": '="AMD"', "Market Value": "7301.15"}]  # 缺 Position Percentage / Margin Amount
    assert compute_account_snapshot(rows) is None


def test_compute_account_snapshot_none_on_empty_rows():
    assert compute_account_snapshot([]) is None


def test_parse_includes_account_snapshot():
    result = parse(_SAMPLE_CSV)
    assert len(result["stocks"]) == 2
    assert result["account_snapshot"] is not None
    assert result["account_snapshot"]["net_asset_value"] > 0
