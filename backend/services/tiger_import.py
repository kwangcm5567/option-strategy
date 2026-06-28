"""解析老虎证券 (Tiger Trade) 导出的 Portfolio Details CSV。

正股 → stocks，期权 → options（按持仓方向 + PUT/CALL 映射成本项目策略）。
"""
import csv
import io
import re
from datetime import datetime


def _clean_symbol(raw: str) -> str:
    """='AMD'  /  ="AMD"  →  AMD。"""
    m = re.search(r"[A-Z][A-Z.]*", raw.replace('="', "").replace('"', ""))
    return m.group(0) if m else raw.strip()


def _parse_expiry(raw: str) -> str | None:
    """DD/MM/YYYY → YYYY-MM-DD。"""
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _to_int(raw: str) -> int:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 0


def _to_float(raw: str) -> float:
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _strategy(option_style: str, holdings: int) -> str | None:
    side = option_style.strip().upper()
    if side == "PUT":
        return "sell_put" if holdings < 0 else "buy_put"
    if side == "CALL":
        return "sell_call" if holdings < 0 else "buy_call"
    return None


def parse(content: str) -> dict:
    """返回 {options: [...], stocks: [...], skipped: int}。"""
    options: list[dict] = []
    stocks: list[dict] = []
    skipped = 0

    reader = csv.DictReader(io.StringIO(content))
    today = datetime.now().strftime("%Y-%m-%d")

    for row in reader:
        symbol = _clean_symbol(row.get("Symbol", ""))
        instrument = (row.get("Instrument") or "").strip()
        holdings = _to_int(row.get("Holdings", "0"))
        if not symbol or holdings == 0:
            skipped += 1
            continue

        if instrument.startswith("Option"):
            strategy = _strategy(row.get("Option Style", ""), holdings)
            expiry = _parse_expiry(row.get("Expiry", ""))
            strike = _to_float(row.get("Strike", "0"))
            if not strategy or not expiry or strike <= 0:
                skipped += 1
                continue
            options.append({
                "symbol": symbol,
                "strategy": strategy,
                "strike": strike,
                "premium": _to_float(row.get("Avg Price", "0")),
                "quantity": abs(holdings),
                "expiration_date": expiry,
                "open_date": today,
                "notes": "老虎导入",
            })
        elif instrument.startswith("Stock"):
            stocks.append({
                "symbol": symbol,
                "quantity": holdings,
                "avg_price": _to_float(row.get("Avg Price", "0")),
                "notes": "老虎导入",
            })
        else:
            skipped += 1

    return {"options": options, "stocks": stocks, "skipped": skipped}
