# 正股/保证金接入风险台 + 扫描胜率统计口径修复

日期：2026-07-26

## 背景

`services/risk.py` 的组合风险台（Beta 加权 Delta、HHI 集中度、历史模拟 VaR、情景压力测试）目前只读 `positions` 表（期权持仓），完全不算 `stock_holdings` 表里的正股/保证金持仓。用户导入老虎证券 CSV 后，正股这块敞口在风险台里是盲区——CSV 里其实自带 `Margin Amount`、`Position Percentage` 等字段，可以反推账户净值、总保证金要求、隐含杠杆，但导入逻辑目前没读这些列。

另外，`services/scanner.py` 里 `_calc_empirical_win_rate` 用重叠滚动窗口计算经验胜率，样本之间高度相关，但样本量从未暴露给调用方；`th.pop_min`（如 strict 档 70%）这个硬门槛看起来像统计显著的胜率，实际独立样本可能很少。

两块改动相互独立，可以并行开发，合并成一份 spec 是因为都是本轮对话里发现的、优先级明确的改进项。

## 目标

1. 正股 + 保证金敞口能进入 `/api/portfolio/risk` 的所有分析维度（Delta、集中度、VaR、压力测试）。
2. 每次老虎 CSV 导入后，能看到一个"距离保证金追缴还有多少缓冲"的量化指标，且随最新报价刷新。
3. 扫描结果的经验胜率旁边能看到真实（独立）样本量，避免小样本被当成机构级门槛信任。

## 非目标（本次不做）

- 组合感知评分（扫描时根据当前仓位集中度/杠杆对候选降权）——依赖本次的 A 部分先落地，作为后续单独一轮 spec。
- 延长历史回看窗口（`cboe.fetch_history` 的 260 日 lookback）——数据源改动，与本次统计口径修复分开处理。
- 价差成本精细化打分（`_liquidity_score` 改进）——优先级最低，本次不做。

---

## Part A：正股/保证金接入风险台

### 数据模型

**新表 `account_snapshots`**（每次 CSV 导入生成一条快照）：

```sql
CREATE TABLE account_snapshots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at             TEXT NOT NULL DEFAULT (datetime('now')),
    net_asset_value         REAL NOT NULL,
    total_market_value      REAL NOT NULL,
    total_margin_requirement REAL NOT NULL,
    implied_margin_loan     REAL NOT NULL,
    leverage                REAL,
    source_filename         TEXT
)
```

- `net_asset_value`：取 CSV 里每行 `Position Percentage`（= 该行 Market Value / NAV）反推出的 NAV，用**中位数**而不是任意一行，抵消四舍五入噪音。
- `total_market_value`：所有行 Market Value 求和。
- `total_margin_requirement`：所有行 Margin Amount 求和。
- `implied_margin_loan = total_market_value - net_asset_value`。
- `leverage = total_market_value / net_asset_value`。

**`stock_holdings` 加两列**（迁移方式同 `positions` 表现有的补列写法）：
- `margin_amount REAL` — 该标的维持保证金要求（CSV 原始值，不现算）。
- `position_pct REAL` — 该标的占 NAV 的百分比（CSV 原始值）。

### `tiger_import.py` 改动

- `parse()` 的 `stocks` 字典追加 `margin_amount`、`position_pct`（读 CSV 的 `Margin Amount` / `Position Percentage` 列，沿用现有 `_to_float` 解析，注意 `%` 符号要先 strip）。
- `options` 字典同样追加这两个字段（一并读取，供以后风险台/持仓页展示用，不强制消费）。
- 新增函数 `compute_account_snapshot(rows) -> dict | None`：输入原始 CSV 行（`csv.DictReader` 产出的 dict 列表），输出上面 `account_snapshots` 的字段（不含 `id`/`imported_at`）。如果 CSV 没有 `Margin Amount` 或 `Position Percentage` 列（老格式/被券商改版），或者能解析出的行数为 0，返回 `None`——不抛异常，让调用方决定是否跳过快照写入。
- `parse()` 返回值增加 `"account_snapshot": compute_account_snapshot(...) | None`。

### `routers/positions.py` 改动

`import_tiger`：
- `parsed["account_snapshot"]` 非 None 时，插入一条 `account_snapshots` 记录；为 None 时跳过，不影响期权/正股导入照常进行。
- 响应体加 `"account_snapshot_saved": bool`。

### `services/risk.py` 改动

- 新增 `_load_stock_holdings() -> list[dict]`，查 `stock_holdings` 全表。
- `analyze_portfolio()` 里，`positions = _load_open_positions()` 之后，紧跟着加载正股列表；正股按 `delta=1.0`（多头）、`$Delta = quantity * current_price` 折算，跟期权的 `$Delta` 合并进：
  - `total_delta`（正股没有 theta/vega，只贡献 delta）
  - `beta_weighted_delta`（复用现有的 `_beta` 查询逻辑，symbol 级缓存已有）
  - `by_sector` / `by_symbol_exposure`（HHI 集中度）
  - `_historical_var` 的 `dollar_deltas` 输入（正股按 `quantity * price` 直接算 delta 敞口，不用走 Black-Scholes）
  - `_stress_test` 的每个情景下，正股 P&L = `quantity * price * priceShock`（线性，不需要期权重估）
- 新增 `_latest_account_snapshot() -> dict | None`，查 `account_snapshots` 最新一条。
- `analyze_portfolio()` 返回值新增 `marginBuffer` 块：
  ```python
  {
      "netAssetValue": ...,          # 快照里的 NAV
      "excessLiquidityEstimate": ...,  # NAV - (最新持仓市值 × 快照隐含的保证金比例)
      "bufferPctToMarginCall": ...,    # 组合整体还能跌多少% 触及追缴（线性估算，注释标明是近似）
      "asOf": ...,                     # 快照时间
      "stale": bool,                   # 快照 > 24 小时时标 true，提示用户重新导入
  }
  ```
  没有快照时该块整体为 `None`，前端据此隐藏这部分 UI，不报错。

### `routers/risk.py` 改动

- `_positions_fingerprint()` 改名/扩展为同时纳入 `stock_holdings`（`COUNT`+`MAX(id)`+金额 SUM）和 `account_snapshots`（`MAX(id)`）三部分拼接成一个字符串，任何一处变化都能让缓存 key 变化、旧缓存自然失效。逻辑跟现有写法一致，只是多查两张表。

### 错误处理

- CSV 缺 `Margin Amount`/`Position Percentage` 列：`compute_account_snapshot` 返回 `None`，导入流程其余部分不受影响（已在上面写明）。
- 两条降级路径互相独立：正股的 Delta/VaR/压力测试计算只依赖 `stock_holdings` 表，不依赖 `account_snapshots`；`account_snapshots` 只用来算 `marginBuffer` 这一块。所以即使用户从没导入过带保证金字段的 CSV（`account_snapshots` 表为空），风险台的 Delta/集中度/VaR/压力测试依然正常工作，只是 `marginBuffer` 单独为 `None`。

### 测试

- `backend/tests/test_advanced.py` 或新建 `test_tiger_import.py`：仿照这次对话里 QQQ/AMD 那几行 CSV 结构构造测试字符串（账户号用占位符，不用真实账户号），跑 `tiger_import.parse()`，断言：
  - `account_snapshot["net_asset_value"]` 接近手算的 ~100,296（容差合理，比如 ±50）。
  - `account_snapshot["total_margin_requirement"]` 等于逐行 Margin Amount 求和。
  - 缺列时返回 `None` 而不是抛异常。
- `services/risk.py` 里加一个纯函数单测：给定一组正股 holdings + 期权 positions，`analyze_portfolio` 的 `concentration.bySector` 里同时出现正股和期权贡献的敞口（复用 `test_advanced.py` 现有的无网络 mock 风格，`_beta`/价格查询用 mock 或直接测试新抽出的纯计算函数而非整个 `analyze_portfolio`）。

---

## Part B1：经验胜率统计口径修复

### `services/scanner.py` 改动

1. `_calc_empirical_win_rate` 返回值不变签名太麻烦，改为返回一个 dict 而不是 4 元组：
   ```python
   {
       "win_rate": float,
       "total_windows": int,       # 重叠窗口总数（现状）
       "safe_windows": int,
       "independent_windows": int, # 新增：跳步取样后的独立窗口数
       "triggered_events": list,
   }
   ```
   调用方（`_process_row`）相应改成属性访问。`_empirical_win_call` / `_empirical_win_put_buy` 目前只返回一个 float，暂不改动签名（它们本来就是基于预计算好的 `up_windows`/`down_windows`，样本量问题同样存在，但这两个函数用途是 buy 方向的参考胜率、不作为硬门槛使用，优先级低于 `sell_put` 的 `pop_min` 硬门槛，先不动）。

2. 独立样本计算：在 `_precompute_windows` 基础上新增 `_independent_sample_count(windows, trading_dte) -> int`——按 `trading_dte` 步长跳跃计数（每隔 `trading_dte` 个交易日取一个窗口，而不是逐日滑动），返回这些跳跃窗口里满足"未跌破行权价"条件的独立样本数与总独立样本数之比不单独算，只返回独立窗口计数（因为独立胜率本身跟重叠胜率理论期望值一致，只是置信区间宽窄不同，不需要重新算一遍胜率数字，只需要暴露样本量让前端标注）。

3. `_process_row` 里 `result` 字典新增字段：
   - `popEmpiricalSampleSize`: `total_windows`（重叠，现状意义上的"样本数"）
   - `popEmpiricalIndependentSampleSize`: 跳步计数得到的独立样本数

4. `sell_put` 硬门槛判断逻辑不变（仍用重叠窗口算出的 `win_rate` 跟 `th.pop_min` 比较）——**不改变现有过滤行为**，只是把样本量透明化，不新增一个基于独立样本的门槛（那是更大的行为变更，超出本次"暴露真实性"的目标，需要用户另外决策要不要收紧门槛）。

### 前端改动（`frontend/src/tabs/scanner`）

- 胜率数值旁边加一个小字/tooltip：`基于 N 个历史窗口（约 M 个独立样本）`，用现有 `components/ui/Tooltip` 组件，不新增组件。
- 独立样本数 < 一个阈值（比如 5）时该 tooltip 用醒目样式（沿用现有 warning 色变量），提示"样本量小，胜率仅供参考"。阈值先写死 5，不做成配置项（YAGNI）。

### 测试

- `test_advanced.py` 补测试：构造一段已知涨跌模式的 `history_df`（比如现有测试里已经有类似手法），断言 `total_windows` > `independent_windows`（重叠样本确实更多），且两者在简单单调序列下的比例符合步长预期（`total_windows ≈ independent_windows × trading_dte`，允许合理误差）。

---

## 影响范围小结

| 文件 | 改动类型 |
|---|---|
| `backend/database.py` | 新表 `account_snapshots`；`stock_holdings` 补列 |
| `backend/services/tiger_import.py` | 解析新字段 + `compute_account_snapshot` |
| `backend/routers/positions.py` | `import_tiger` 写入快照 |
| `backend/services/risk.py` | 正股并入敞口计算 + `marginBuffer` 输出 |
| `backend/routers/risk.py` | 缓存指纹纳入正股/快照 |
| `backend/services/scanner.py` | 独立样本量计算 + 结果字段扩展 |
| `frontend/src/tabs/scanner/*` | 胜率旁展示样本量 |
| `backend/tests/test_advanced.py`（或新文件）| 新增单测 |

不涉及：`spreads.py`、`payoff.py`、`greeks.py`、其余 routers。
