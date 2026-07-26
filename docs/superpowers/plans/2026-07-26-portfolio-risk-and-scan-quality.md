# 正股/保证金接入风险台 + 扫描胜率统计口径修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让正股/保证金持仓（老虎证券 CSV 导入）纳入组合风险台（Delta/集中度/VaR/压力测试），新增"距保证金追缴缓冲"指标；并修复期权扫描经验胜率的重叠窗口统计问题，向用户暴露真实（独立）样本量。

**Architecture:** 新增 `account_snapshots` 表存每次 CSV 导入反推出的账户级快照（NAV/总保证金要求/隐含杠杆）；`services/risk.py` 新增纯函数 `_stock_exposure`/`_margin_buffer`，并给已有的 `_historical_var`/`_stress_test` 加一个可选的 `stock_holdings` 参数（默认 `None`，向后兼容，不破坏现有调用和测试）；`scanner.py` 的 `_calc_empirical_win_rate` 从 4 元组改成 dict 返回值，新增独立样本计数。

**Tech Stack:** Python 3.14 / FastAPI / SQLite（内置 sqlite3）/ pandas；前端 React 19（本计划仅涉及 `OptionCard.jsx` 一处小改动）。

## Global Constraints

- Python 遵循 PEP 8，函数签名加类型注解，字符串用 f-string（项目 CLAUDE.md）。
- 不加不必要的注释、不加多余 try/except、不做"为了将来扩展"的抽象（项目 CLAUDE.md）。
- Git commit 用 Conventional Commits 前缀（`feat:`/`fix:`/`test:`/`refactor:`）。
- 本项目后端依赖管理用现有的 `venv` + `pip`（不是 uv——项目已有既定约定，见 `backend/requirements.txt`）。
- 测试运行命令（WSL 环境）：`cd backend && ./venv/Scripts/python.exe -m pytest tests/ -v`（也可用 `-k <test_name>` 跑单个测试）。
- 现有测试分两类：`tests/test_core.py`、`tests/test_advanced.py` 是无网络、无 DB 依赖的纯函数单测；本计划新增的 DB 相关测试通过 `monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")` 隔离，不碰真实的 `backend/positions.db`。

## 与 design spec 的偏差说明

Design spec（`docs/superpowers/specs/2026-07-26-portfolio-risk-and-scan-quality-design.md`）里提到给 `stock_holdings` 表和 options 解析结果加 `margin_amount`/`position_pct` 字段，"供以后风险台/持仓页展示用"。写这份实施计划时发现：账户级快照（NAV/总保证金/杠杆）完全由 `compute_account_snapshot()` 直接从 CSV 原始行计算得出，不依赖这两个逐仓位字段；而且本计划范围内没有任何地方会真正读取它们。按项目 CLAUDE.md"不做面向未来的抽象"的要求，这两个字段本次不加——只加 `account_snapshots` 表和它需要的列。如果以后风险台要做"哪个仓位吃掉最多保证金"这类明细展示，到时候再单独加。

---

### Task 1: `account_snapshots` 表

**Files:**
- Modify: `backend/database.py:20-66`（`init_db()` 函数）
- Test: `backend/tests/test_db_integration.py`（新建）

**Interfaces:**
- Produces: `account_snapshots` 表，列为 `id, imported_at, net_asset_value, total_market_value, total_margin_requirement, implied_margin_loan, leverage`。后续任务通过 `INSERT INTO account_snapshots (net_asset_value, total_market_value, total_margin_requirement, implied_margin_loan, leverage) VALUES (?, ?, ?, ?, ?)` 写入。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_db_integration.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_db_integration.py -v`
Expected: FAIL（`account_snapshots` 表不存在，`cols` 为空集）

- [ ] **Step 3: 实现**

在 `backend/database.py` 的 `init_db()` 里，紧跟在 `stock_holdings` 表的 `CREATE TABLE IF NOT EXISTS` 语句之后（第 51 行 `""")` 之后）插入：

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_snapshots (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                imported_at               TEXT    NOT NULL DEFAULT (datetime('now')),
                net_asset_value           REAL    NOT NULL,
                total_market_value        REAL    NOT NULL,
                total_margin_requirement  REAL    NOT NULL,
                implied_margin_loan       REAL    NOT NULL,
                leverage                  REAL
            )
        """)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_db_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd backend && git add database.py tests/test_db_integration.py
git commit -m "feat: 新增 account_snapshots 表，存老虎 CSV 导入的账户级保证金快照"
```

---

### Task 2: `tiger_import.compute_account_snapshot()`

**Files:**
- Modify: `backend/services/tiger_import.py`
- Test: `backend/tests/test_tiger_import.py`（新建）

**Interfaces:**
- Consumes: 无（纯函数，输入是 `csv.DictReader` 产出的 dict 列表）
- Produces: `compute_account_snapshot(rows: list[dict]) -> dict | None`，返回值 keys：`net_asset_value, total_market_value, total_margin_requirement, implied_margin_loan, leverage`（无有效行时返回 `None`）。`parse(content: str) -> dict` 的返回值新增 `"account_snapshot"` key。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_tiger_import.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_tiger_import.py -v`
Expected: FAIL（`compute_account_snapshot` 不存在 / `parse()` 返回值没有 `account_snapshot` key）

- [ ] **Step 3: 实现**

在 `backend/services/tiger_import.py` 里，`_to_float` 函数之后（第 37 行之后）新增：

```python
def compute_account_snapshot(rows: list[dict]) -> dict | None:
    """从老虎 CSV 原始行反推账户级快照：用各行 Market Value / Position Percentage
    反推 NAV 取中位数（抗单行四舍五入噪音），Margin Amount 求和得总保证金要求。
    缺列或没有可用行时返回 None，调用方据此跳过快照写入，不影响其余导入流程。"""
    implied_navs: list[float] = []
    total_mv = 0.0
    total_margin = 0.0

    for row in rows:
        mv_raw = row.get("Market Value", "")
        pct_raw = row.get("Position Percentage", "")
        margin_raw = row.get("Margin Amount", "")
        if not mv_raw or not pct_raw or not margin_raw:
            continue
        mv = _to_float(mv_raw)
        pct = _to_float(pct_raw.replace("%", ""))
        margin = _to_float(margin_raw)
        if mv <= 0 or pct <= 0:
            continue
        implied_navs.append(mv / (pct / 100))
        total_mv += mv
        total_margin += margin

    if not implied_navs:
        return None

    implied_navs.sort()
    n = len(implied_navs)
    mid = n // 2
    nav = implied_navs[mid] if n % 2 == 1 else (implied_navs[mid - 1] + implied_navs[mid]) / 2

    return {
        "net_asset_value": round(nav, 2),
        "total_market_value": round(total_mv, 2),
        "total_margin_requirement": round(total_margin, 2),
        "implied_margin_loan": round(total_mv - nav, 2),
        "leverage": round(total_mv / nav, 4) if nav > 0 else None,
    }
```

然后修改 `parse()` 函数末尾（第 90-92 行）的 `return` 语句。原来：

```python
    return {"options": options, "stocks": stocks, "skipped": skipped}
```

改成：

```python
    snapshot = compute_account_snapshot(list(csv.DictReader(io.StringIO(content))))
    return {"options": options, "stocks": stocks, "skipped": skipped, "account_snapshot": snapshot}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_tiger_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/tiger_import.py tests/test_tiger_import.py
git commit -m "feat: tiger_import 反推账户级保证金快照 (NAV/总保证金/隐含杠杆)"
```

---

### Task 3: `import_tiger` 端点持久化快照

**Files:**
- Modify: `backend/routers/positions.py:220-258`
- Test: `backend/tests/test_db_integration.py`

**Interfaces:**
- Consumes: `tiger_import.parse(content) -> dict`（含 Task 2 新增的 `"account_snapshot"` key）
- Produces: `POST /api/positions/import-tiger` 响应体新增 `"account_snapshot_saved": bool`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_db_integration.py` 追加：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_db_integration.py -v`
Expected: FAIL（`result` 没有 `account_snapshot_saved` key，或 `account_snapshots` 表为空）

- [ ] **Step 3: 实现**

在 `backend/routers/positions.py` 的 `import_tiger` 函数（第 220-258 行）里做两处改动：

1. 函数开头（第 224-226 行）加一个计数变量：

```python
    parsed = tiger_import.parse(body.content)
    opt_added = 0
    stock_added = 0
    snapshot_saved = False
```

2. 在 `with get_conn() as conn:` 块内、`conn.commit()`（第 256 行）之前，`for s in parsed["stocks"]:` 循环结束之后插入：

```python
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
```

3. 函数末尾的 `return` 语句（第 258 行）：

```python
    return {"options_imported": opt_added, "stocks_imported": stock_added,
            "skipped": parsed["skipped"], "account_snapshot_saved": snapshot_saved}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_db_integration.py -v`
Expected: PASS（两个测试都过）

- [ ] **Step 5: Commit**

```bash
cd backend && git add routers/positions.py tests/test_db_integration.py
git commit -m "feat: 老虎 CSV 导入时落地账户保证金快照"
```

---

### Task 4: `risk.py` 正股敞口 + marginBuffer

**Files:**
- Modify: `backend/services/risk.py`
- Test: `backend/tests/test_advanced.py`

**Interfaces:**
- Consumes: `stock_holdings` 表行（`{id, symbol, quantity, avg_price, notes}`），`account_snapshots` 最新行
- Produces:
  - `_stock_exposure(holdings: list[dict], price_map: dict, beta_map: dict, spy_price: float) -> dict`（keys: `totalDelta, betaWeightedDelta, bySector, bySymbolExposure, details`）
  - `_historical_var(positions, price_map, ret_map, today, stock_holdings=None, confidence=0.95) -> dict`（签名新增可选参数，向后兼容）
  - `_stress_test(positions, price_map, ret_map, today, stock_holdings=None) -> list[dict]`（签名新增可选参数，向后兼容）
  - `_margin_buffer(snapshot: dict | None) -> dict | None`
  - `analyze_portfolio()` 返回值新增 `"marginBuffer"` key，`concentration`/`greeks`/`var`/`stress` 里包含正股贡献

#### Step 组 1：`_stock_exposure`

- [ ] **Step 1.1: 写失败测试**

在 `backend/tests/test_advanced.py` 的 `# ═══ risk ═══` 分区（约第 189 行 `_ret_series` 定义附近）追加：

```python
def test_stock_exposure_adds_delta_and_sector():
    from services.risk import _stock_exposure
    holdings = [{"symbol": "QQQ", "quantity": 402}]
    price_map = {"QQQ": 683.90}
    beta_map = {"QQQ": 1.0}
    exp = _stock_exposure(holdings, price_map, beta_map, spy_price=650.0)

    assert exp["totalDelta"] == 402
    assert exp["bySector"]["指数ETF"] == 402 * 683.90
    assert exp["bySymbolExposure"]["QQQ"] == 402 * 683.90
    assert exp["details"][0]["symbol"] == "QQQ"


def test_stock_exposure_skips_missing_price():
    from services.risk import _stock_exposure
    holdings = [{"symbol": "ZZZ", "quantity": 10}]
    exp = _stock_exposure(holdings, {}, {}, spy_price=500.0)
    assert exp["totalDelta"] == 0.0
    assert exp["bySector"] == {}
```

- [ ] **Step 1.2: 跑测试确认失败**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_advanced.py -k stock_exposure -v`
Expected: FAIL（`_stock_exposure` 不存在）

- [ ] **Step 1.3: 实现**

在 `backend/services/risk.py` 的 `_load_open_positions()` 函数（第 64-69 行）之后插入：

```python
def _load_stock_holdings() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM stock_holdings").fetchall()
    return [dict(r) for r in rows]


def _latest_account_snapshot() -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM account_snapshots ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _stock_exposure(holdings: list[dict], price_map: dict, beta_map: dict, spy_price: float) -> dict:
    """正股在 delta / beta加权delta / 行业与个股集中度 上的贡献（delta=1/股，多头持仓）。"""
    total_delta = 0.0
    beta_weighted_delta = 0.0
    by_sector: dict[str, float] = {}
    by_symbol_exposure: dict[str, float] = {}
    details = []

    for h in holdings:
        sym = h["symbol"]
        S = price_map.get(sym)
        if not S:
            continue
        qty = h["quantity"]
        total_delta += qty

        beta = beta_map.get(sym) or 1.0
        dollar_delta = qty * S
        bwd = dollar_delta * beta / spy_price
        beta_weighted_delta += bwd

        notional = abs(qty) * S
        sector = SECTOR_MAP.get(sym, "其他")
        by_sector[sector] = by_sector.get(sector, 0) + notional
        by_symbol_exposure[sym] = by_symbol_exposure.get(sym, 0) + notional

        details.append({
            "symbol": sym, "quantity": qty, "beta": beta,
            "delta": round(float(qty), 1), "betaWeightedDelta": round(bwd, 2),
        })

    return {
        "totalDelta": total_delta,
        "betaWeightedDelta": beta_weighted_delta,
        "bySector": by_sector,
        "bySymbolExposure": by_symbol_exposure,
        "details": details,
    }
```

- [ ] **Step 1.4: 跑测试确认通过**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_advanced.py -k stock_exposure -v`
Expected: PASS

#### Step 组 2：`_historical_var` / `_stress_test` 加 `stock_holdings` 参数

- [ ] **Step 2.1: 写失败测试**

在 `backend/tests/test_advanced.py` 里紧跟 `test_historical_var_no_data`（约第 210 行）之后追加：

```python
def test_historical_var_includes_stock_holdings():
    ret_map = {"QQQ": _ret_series([0.01, -0.03, 0.02, -0.015, 0.025] * 60)}
    var_with_stock = _historical_var(
        [], {"QQQ": 100.0}, ret_map, datetime.now().date(),
        stock_holdings=[{"symbol": "QQQ", "quantity": 10}],
    )
    var_without = _historical_var([], {"QQQ": 100.0}, ret_map, datetime.now().date())

    assert var_with_stock["oneDayVar95"] is not None
    assert var_without["oneDayVar95"] is None  # 没有期权也没传正股参数 → 无敞口
```

紧跟 `test_stress_test_sell_put_loses_in_crash`（约第 220 行）之后追加：

```python
def test_stress_test_includes_stock_holdings_linear_pnl():
    out = _stress_test(
        [], {"QQQ": 100.0}, {}, datetime.now().date(),
        stock_holdings=[{"symbol": "QQQ", "quantity": 10}],
    )
    by_name = {o["scenario"]: o["pnl"] for o in out}
    assert by_name["2008金融危机"] == round(10 * 100.0 * -0.40, 2)
    assert by_name["强势上涨+10%"] == round(10 * 100.0 * 0.10, 2)
```

- [ ] **Step 2.2: 跑测试确认失败**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_advanced.py -k "stock_holdings" -v`
Expected: FAIL（`_historical_var`/`_stress_test` 不接受 `stock_holdings` 参数）

- [ ] **Step 2.3: 实现**

修改 `backend/services/risk.py` 的 `_historical_var` 函数签名（第 201 行）：

原来：
```python
def _historical_var(positions, price_map, ret_map, today, confidence=0.95) -> dict:
```

改成：
```python
def _historical_var(positions, price_map, ret_map, today, stock_holdings=None, confidence=0.95) -> dict:
```

在函数内部（第 202-207 行，构建 `dollar_deltas` 的 for 循环之后、`valid_syms = ...` 之前）插入：

```python
    for h in (stock_holdings or []):
        sym = h["symbol"]
        S = price_map.get(sym)
        if S:
            dollar_deltas[sym] = dollar_deltas.get(sym, 0) + h["quantity"] * S
```

修改 `_stress_test` 函数签名（第 227 行）：

原来：
```python
def _stress_test(positions, price_map, ret_map, today) -> list[dict]:
```

改成：
```python
def _stress_test(positions, price_map, ret_map, today, stock_holdings=None) -> list[dict]:
```

在函数内部，`for name, sc in STRESS_SCENARIOS.items():` 循环体里，`for pos in positions:` 循环（第 232-253 行）结束之后、`out.append(...)`（第 254 行）之前插入：

```python
        for h in (stock_holdings or []):
            sym = h["symbol"]
            S = price_map.get(sym)
            if not S:
                continue
            total_pnl += h["quantity"] * S * sc["priceShock"]
```

- [ ] **Step 2.4: 跑测试确认通过**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_advanced.py -v`
Expected: PASS（全部通过，包括原有的 `test_historical_var_positive_for_delta_exposure` 等——因为新参数默认 `None`，行为不变）

#### Step 组 3：`_margin_buffer`

- [ ] **Step 3.1: 写失败测试**

在 `backend/tests/test_advanced.py` 的 risk 分区末尾追加：

```python
def test_margin_buffer_computes_pct_to_call():
    from services.risk import _margin_buffer
    snapshot = {
        "net_asset_value": 100000.0,
        "total_market_value": 300000.0,
        "total_margin_requirement": 60000.0,
        "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    result = _margin_buffer(snapshot)
    assert result["excessLiquidityEstimate"] == 40000.0
    assert result["stale"] is False
    # avg_margin_rate = 60000/300000 = 0.2 → buffer_pct = 40000/(300000*0.8)*100 ≈ 16.7
    assert abs(result["bufferPctToMarginCall"] - 16.7) < 0.5


def test_margin_buffer_none_when_no_snapshot():
    from services.risk import _margin_buffer
    assert _margin_buffer(None) is None


def test_margin_buffer_flags_stale_after_24h():
    from services.risk import _margin_buffer
    old = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
    snapshot = {
        "net_asset_value": 100.0, "total_market_value": 100.0,
        "total_margin_requirement": 10.0, "imported_at": old,
    }
    assert _margin_buffer(snapshot)["stale"] is True
```

- [ ] **Step 3.2: 跑测试确认失败**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_advanced.py -k margin_buffer -v`
Expected: FAIL（`_margin_buffer` 不存在）

- [ ] **Step 3.3: 实现**

在 `backend/services/risk.py` 的 `_stress_test` 函数之后、`_reval_price` 函数之前插入：

```python
def _margin_buffer(snapshot: dict | None) -> dict | None:
    """基于最新账户快照估算距保证金追缴的缓冲空间（线性近似：假设组合按现有比例整体涨跌，
    保证金要求随市值等比例变化）。没有快照时返回 None，风险台其余部分不受影响。"""
    if snapshot is None:
        return None

    nav = snapshot["net_asset_value"]
    total_margin_req = snapshot["total_margin_requirement"]
    total_mv = snapshot["total_market_value"]
    excess = nav - total_margin_req

    avg_margin_rate = total_margin_req / total_mv if total_mv > 0 else None
    buffer_pct = None
    if avg_margin_rate is not None and avg_margin_rate < 1:
        buffer_pct = round(excess / (total_mv * (1 - avg_margin_rate)) * 100, 1)

    imported_at = datetime.strptime(snapshot["imported_at"], "%Y-%m-%d %H:%M:%S")
    stale = (datetime.now() - imported_at).total_seconds() > 24 * 3600

    return {
        "netAssetValue": round(nav, 2),
        "excessLiquidityEstimate": round(excess, 2),
        "bufferPctToMarginCall": buffer_pct,
        "asOf": snapshot["imported_at"],
        "stale": stale,
    }
```

- [ ] **Step 3.4: 跑测试确认通过**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_advanced.py -k margin_buffer -v`
Expected: PASS

#### Step 组 4：接入 `analyze_portfolio()`

- [ ] **Step 4.1: 实现**（这一步是纯粹的接线，前面三组已经把新增逻辑测过，`analyze_portfolio()` 本身跟现有的 `_load_open_positions` 一样是 DB+网络依赖的编排函数，不单独写单测，和现状一致）

修改 `backend/services/risk.py` 的 `analyze_portfolio()` 函数（第 72-171 行）：

1. 开头（第 73-75 行）：

原来：
```python
def analyze_portfolio() -> dict:
    positions = _load_open_positions()
    if not positions:
        return {"empty": True}

    symbols = sorted({p["symbol"] for p in positions})
```

改成：
```python
def analyze_portfolio() -> dict:
    positions = _load_open_positions()
    stock_holdings = _load_stock_holdings()
    if not positions and not stock_holdings:
        return {"empty": True}

    symbols = sorted({p["symbol"] for p in positions} | {h["symbol"] for h in stock_holdings})
```

2. 在期权 `for pos in positions:` 循环（第 100-134 行）结束之后、`# ── 集中度 ──` 注释（第 136 行）之前插入：

```python
    stock_stats = _stock_exposure(stock_holdings, price_map, beta_map, spy_price)
    total_delta += stock_stats["totalDelta"]
    beta_weighted_delta += stock_stats["betaWeightedDelta"]
    for sector, notional in stock_stats["bySector"].items():
        by_sector[sector] = by_sector.get(sector, 0) + notional
    for sym, notional in stock_stats["bySymbolExposure"].items():
        by_symbol_exposure[sym] = by_symbol_exposure.get(sym, 0) + notional
    position_details.extend(stock_stats["details"])
```

3. `_historical_var` 和 `_stress_test` 的调用处（第 146、149 行）：

原来：
```python
    var_metrics = _historical_var(positions, price_map, ret_map, today)
    stress = _stress_test(positions, price_map, ret_map, today)
```

改成：
```python
    var_metrics = _historical_var(positions, price_map, ret_map, today, stock_holdings=stock_holdings)
    stress = _stress_test(positions, price_map, ret_map, today, stock_holdings=stock_holdings)
    margin_buffer = _margin_buffer(_latest_account_snapshot())
```

4. 函数末尾 `return` 语句（第 151-171 行），在 `"stress": stress,` 之后加一行：

```python
        "stress": stress,
        "marginBuffer": margin_buffer,
        "positions": position_details,
```

- [ ] **Step 4.2: 跑全量测试确认没有回归**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS（全部通过）

- [ ] **Step 4.3: 更新 `routers/risk.py` 缓存指纹**（见 Task 5，与本任务同批提交）

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/risk.py tests/test_advanced.py
git commit -m "feat: 风险台接入正股敞口 + marginBuffer 保证金缓冲估算"
```

---

### Task 5: `routers/risk.py` 缓存指纹纳入正股/快照

**Files:**
- Modify: `backend/routers/risk.py:15-23`
- Test: `backend/tests/test_db_integration.py`

**Interfaces:**
- Consumes: `stock_holdings`、`account_snapshots` 表
- Produces: `_positions_fingerprint() -> str`（原有函数，签名不变，返回值组成变化）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_db_integration.py` 追加：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_db_integration.py -k fingerprint -v`
Expected: FAIL（指纹不含 `stock_holdings`，加一条正股记录后 `fp1 == fp2`）

- [ ] **Step 3: 实现**

修改 `backend/routers/risk.py` 的 `_positions_fingerprint()` 函数（第 15-23 行）：

原来：
```python
def _positions_fingerprint() -> str:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(strike * quantity + premium), 0)
            FROM positions WHERE status='open' OR status IS NULL
            """
        ).fetchone()
    return f"{row[0]}:{row[1]}:{round(row[2], 4)}"
```

改成：
```python
def _positions_fingerprint() -> str:
    with get_conn() as conn:
        pos_row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(strike * quantity + premium), 0)
            FROM positions WHERE status='open' OR status IS NULL
            """
        ).fetchone()
        stock_row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(quantity * avg_price), 0)
            FROM stock_holdings
            """
        ).fetchone()
        snap_row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM account_snapshots").fetchone()
    return (
        f"{pos_row[0]}:{pos_row[1]}:{round(pos_row[2], 4)}:"
        f"{stock_row[0]}:{stock_row[1]}:{round(stock_row[2], 4)}:{snap_row[0]}"
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_db_integration.py -v`
Expected: PASS（全部通过）

- [ ] **Step 5: Commit**

```bash
cd backend && git add routers/risk.py tests/test_db_integration.py
git commit -m "fix: 风险台缓存指纹纳入正股/账户快照，避免正股变化后拿到旧缓存"
```

---

### Task 6: 经验胜率暴露独立样本量

**Files:**
- Modify: `backend/services/scanner.py`
- Test: `backend/tests/test_core.py`

**Interfaces:**
- Produces:
  - `_independent_sample_count(windows: list[tuple], trading_dte: int) -> int`
  - `_calc_empirical_win_rate(...) -> dict`（**签名变化**：原来返回 4 元组 `(win_rate, total_windows, safe_windows, triggered_events)`，改成 dict，keys: `win_rate, total_windows, safe_windows, independent_windows, triggered_events`）
  - `_process_row` 返回的 `result` 字典新增两个 key：`popEmpiricalSampleSize`、`popEmpiricalIndependentSampleSize`

- [ ] **Step 1: 写失败测试（含更新已有测试）**

`backend/tests/test_core.py` 里现有三个测试（第 58-73 行）用的是旧的 4 元组解包，先改成 dict 访问，并新增独立样本量测试。把这三个函数整体替换成：

```python
def test_win_rate_flat_history_never_breaches():
    # 价格恒定 100，行权价 90：从不跌破 → 胜率 100%
    stats = _calc_empirical_win_rate(_flat_history(100), 30, 100, 90)
    assert stats["win_rate"] == 1.0
    assert stats["total_windows"] > 0 and stats["safe_windows"] == stats["total_windows"]


def test_win_rate_strike_above_price_is_zero():
    # 行权价 110 高于现价 100：required_drop <= 0 → 0%
    stats = _calc_empirical_win_rate(_flat_history(100), 30, 100, 110)
    assert stats["win_rate"] == 0.0


def test_win_rate_empty_history():
    stats = _calc_empirical_win_rate(pd.DataFrame(), 30, 100, 90)
    assert stats["win_rate"] == 1.0 and stats["total_windows"] == 0


def test_win_rate_reports_independent_sample_smaller_than_total():
    stats = _calc_empirical_win_rate(_flat_history(100), 30, 100, 90)
    # 30 日 DTE ≈ 20 个交易日步长，重叠窗口数应明显多于独立窗口数
    assert stats["independent_windows"] < stats["total_windows"]
    assert stats["independent_windows"] > 0


def test_independent_sample_count_matches_stride():
    from services.scanner import _independent_sample_count
    windows = [(None, 0, 0, 0)] * 100
    assert _independent_sample_count(windows, trading_dte=10) == 10
    assert _independent_sample_count([], trading_dte=10) == 0
    assert _independent_sample_count(windows, trading_dte=1) == 100
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_core.py -v`
Expected: FAIL（`_calc_empirical_win_rate` 仍返回 4 元组，`_independent_sample_count` 不存在）

- [ ] **Step 3: 实现**

在 `backend/services/scanner.py` 的 `_precompute_up_windows` 函数（第 208-222 行）之后、`_calc_empirical_win_rate` 之前插入：

```python
def _independent_sample_count(windows: list[tuple], trading_dte: int) -> int:
    """按 trading_dte 步长跳跃取样，返回互不重叠窗口数（用于暴露真实统计独立性）。"""
    if not windows:
        return 0
    step = max(1, trading_dte)
    return len(windows[::step])
```

然后把 `_calc_empirical_win_rate` 函数（第 225-266 行）整体替换成：

```python
def _calc_empirical_win_rate(history_df: pd.DataFrame, dte: int, current_price: float, strike: float,
                              _windows: list[tuple] | None = None) -> dict:
    """sell_put 经验胜率：股价从未跌破行权价的窗口比例。

    返回 dict：win_rate（重叠窗口胜率）、total_windows（重叠窗口总数）、
    safe_windows、independent_windows（按 DTE 步长跳跃取样的独立样本数，
    用于让调用方判断胜率的统计可信度）、triggered_events。
    """
    empty_result = {"win_rate": 1.0, "total_windows": 0, "safe_windows": 0,
                     "independent_windows": 0, "triggered_events": []}
    if history_df.empty or current_price <= 0:
        return empty_result

    required_drop_pct = (current_price - strike) / current_price
    if required_drop_pct <= 0:
        return {**empty_result, "win_rate": 0.0}

    if _windows is None:
        _windows = _precompute_windows(history_df, dte)

    total_windows = len(_windows)
    safe_windows = 0
    triggered_events: list[dict] = []
    trading_dte = max(1, int(dte * 252 / 365))

    for start_date, start_price, window_min, drop_pct in _windows:
        if drop_pct < required_drop_pct:
            safe_windows += 1
        else:
            if not triggered_events or (
                start_date - datetime.strptime(triggered_events[-1]["date"], "%Y-%m-%d")
                .replace(tzinfo=start_date.tzinfo)
            ).days > trading_dte:
                triggered_events.append({
                    "date": start_date.strftime("%Y-%m-%d"),
                    "start_price": round(start_price, 2),
                    "min_price": round(window_min, 2),
                    "drawdown_pct": round(drop_pct * 100, 2),
                })
            else:
                last = triggered_events[-1]
                if drop_pct * 100 > last["drawdown_pct"]:
                    last["min_price"] = round(window_min, 2)
                    last["drawdown_pct"] = round(drop_pct * 100, 2)

    if total_windows == 0:
        return empty_result

    return {
        "win_rate": safe_windows / total_windows,
        "total_windows": total_windows,
        "safe_windows": safe_windows,
        "independent_windows": _independent_sample_count(_windows, trading_dte),
        "triggered_events": triggered_events,
    }
```

接着修改调用方 `_process_row`（第 567-572 行）。原来：

```python
    # ── 四种策略的经验胜率 ──
    if strategy == "sell_put":
        win_rate, _, _, _ = _calc_empirical_win_rate(history_1y, dte, current_price, strike, down_windows)
        pop_empirical = round(win_rate * 100, 1)
        if pop_empirical < th.pop_min:
            return None
```

改成：

```python
    # ── 四种策略的经验胜率 ──
    pop_sample_size = None
    pop_independent_sample_size = None
    if strategy == "sell_put":
        win_stats = _calc_empirical_win_rate(history_1y, dte, current_price, strike, down_windows)
        pop_empirical = round(win_stats["win_rate"] * 100, 1)
        pop_sample_size = win_stats["total_windows"]
        pop_independent_sample_size = win_stats["independent_windows"]
        if pop_empirical < th.pop_min:
            return None
```

（`elif strategy == "buy_put":` 及之后的分支不变。）

最后在 `result` 字典里（第 636-638 行 `"popTheoretical"`/`"popEmpirical"`/`"p50"` 附近），`"popEmpirical": pop_empirical,` 这一行之后加两行：

```python
        "popEmpirical": pop_empirical,
        "popEmpiricalSampleSize": pop_sample_size,
        "popEmpiricalIndependentSampleSize": pop_independent_sample_size,
        "p50": p50,
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS（全部通过，包括 `test_advanced.py` 里没被这次改动触及的用例）

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/scanner.py tests/test_core.py
git commit -m "fix: 经验胜率暴露独立样本量，修复重叠窗口虚假置信度问题"
```

---

### Task 7: 前端展示胜率样本量

**Files:**
- Modify: `frontend/src/tabs/scanner/OptionCard.jsx:172-205`（`PoPBar` 组件）及其调用处（约第 641 行）

**Interfaces:**
- Consumes: `option.popEmpiricalSampleSize`、`option.popEmpiricalIndependentSampleSize`（Task 6 新增的后端字段）

- [ ] **Step 1: 修改 `PoPBar` 组件**

`frontend/src/tabs/scanner/OptionCard.jsx` 第 173 行，`PoPBar` 组件签名：

原来：
```jsx
function PoPBar({ theoretical, empirical }) {
```

改成：
```jsx
function PoPBar({ theoretical, empirical, sampleSize, independentSampleSize }) {
```

在第 191-193 行（"历史回测胜率" 那一块）的 `</div>` 之后（第 197 行 `</div>` 之前，也就是历史胜率进度条 div 结束之后）插入样本量提示：

```jsx
          {empirical != null && sampleSize != null && (
            <p style={{
              fontSize: '0.68rem', marginTop: '2px',
              color: independentSampleSize != null && independentSampleSize < 5
                ? '#f59e0b' : 'var(--text-secondary)',
            }}>
              基于 {sampleSize} 个历史窗口
              {independentSampleSize != null && `（约 ${independentSampleSize} 个独立样本）`}
              {independentSampleSize != null && independentSampleSize < 5 && ' ⚠️ 样本量小，仅供参考'}
            </p>
          )}
```

- [ ] **Step 2: 更新调用处**

第 641 行附近：

原来：
```jsx
<PoPBar theoretical={option.popTheoretical} empirical={option.popEmpirical} />
```

改成：
```jsx
<PoPBar
  theoretical={option.popTheoretical}
  empirical={option.popEmpirical}
  sampleSize={option.popEmpiricalSampleSize}
  independentSampleSize={option.popEmpiricalIndependentSampleSize}
/>
```

- [ ] **Step 3: Lint 检查**

Run: `cd frontend && npm run lint`
Expected: 无新增报错

- [ ] **Step 4: 手动验证**

启动前后端（`cd backend && ./venv/Scripts/python.exe main.py`，`cd frontend && npm run dev`），在扫描页跑一次 `sell_put` 扫描，打开任意一张期权卡片，确认"历史回测胜率"下方出现"基于 N 个历史窗口（约 M 个独立样本）"字样，且 M 较小时文字变成警示色。

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/tabs/scanner/OptionCard.jsx
git commit -m "feat: 期权卡片展示经验胜率的真实样本量，小样本标警示色"
```

---

## Self-Review 记录

- **Spec 覆盖**：Part A（account_snapshots 表、tiger_import 快照计算、risk.py 正股敞口+marginBuffer、缓存指纹）→ Task 1-5 覆盖；Part B1（独立样本量、前端展示）→ Task 6-7 覆盖。Spec 里"stock_holdings 加两列"和"options 字典加 margin_amount/position_pct"两项，如上文"与 design spec 的偏差说明"所述，判断为本计划范围内的死代码，主动砍掉，未遗漏其余条目。
- **占位符扫描**：全文无 TBD/TODO，每个 Step 都有完整代码。
- **类型一致性**：`_historical_var`/`_stress_test` 的 `stock_holdings` 参数命名、`_stock_exposure` 返回值 keys（`totalDelta`/`betaWeightedDelta`/`bySector`/`bySymbolExposure`/`details`）、`_margin_buffer` 返回值 keys 在 Task 4 内部前后一致；`_calc_empirical_win_rate` 新返回值 keys 在 Task 6 的实现和调用处（`_process_row`）保持一致。
