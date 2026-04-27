# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 协作风格

**请用中文回复。**

改代码前先说明计划，等确认后再动手。遇到不确定的地方先问，不要自己猜。回复保持简洁，不要总结刚写过的内容，不要道歉。

不要做的事：
- 加没必要的注释（代码能自解释就不加）
- 加多余的 try/catch（系统边界除外）
- 写"为了将来扩展"的抽象
- 顺手重构无关代码

## 代码风格

**JavaScript / TypeScript：**
- 只用函数式组件，不用 class 组件
- `async/await`，不用回调嵌套
- 优先 `const`，慎用 `let`，禁用 `var`
- 必须加类型注解，不用 `any`

**Python：**
- 遵循 PEP 8，加 type hints，字符串用 f-string

**通用：** 命名有意义，函数单一职责，先写最简版本再优化。

## 工具偏好

- 前端包管理：`pnpm`（不用 npm/yarn）
- Python 包管理：`uv`（不用 pip/poetry）
- Git commit 格式：Conventional Commits（`feat:` / `fix:` / `docs:` 前缀）
- 遇到不熟悉的库或框架，先用 **Context7 MCP** 查官方文档再写代码

## Project Overview

**Alpha Options Strategy** — a full-stack app for quantitative options analysis. It scans the top 20 US large-cap stocks, filters for cash-secured puts and call-buying opportunities, and presents them in a React dashboard. The backend fetches live market data from Yahoo Finance via `yfinance` and performs all calculations server-side.

## Running the App

**Backend** (FastAPI, port 8000):
```bash
cd backend
# First time: activate the virtual environment
source venv/Scripts/activate   # Windows/WSL
# pip install fastapi uvicorn yfinance pandas vaderSentiment  (if venv not set up)
python main.py
# or: uvicorn main:app --reload --port 8000
```

**Frontend** (React + Vite, port 5173):
```bash
cd frontend
npm install   # first time only
npm run dev
```

**Lint frontend:**
```bash
cd frontend && npm run lint
```

There are no backend tests and no frontend test suite currently.

## Architecture

### Backend (`backend/main.py`)

Single-file FastAPI app. All logic lives here — no separate modules.

**Key globals:**
- `TICKERS` — hardcoded list of 20 large-cap US symbols scanned on every request.
- `cache` — in-memory dict that stores results for 1 hour to avoid hammering Yahoo Finance. The first request after startup (or `?force_refresh=true`) can take 10–30 seconds.

**Core function — `calc_empirical_win_rate(history_df, dte, current_price, strike)`:**  
Slides a rolling window of `dte` trading days across 1–2 years of price history and counts windows where the stock never breached the strike. Returns `(win_rate, total_windows, safe_windows, triggered_events)`. Overlapping breach windows are deduplicated into distinct "crash events."

**API endpoints:**
| Endpoint | Purpose |
|---|---|
| `GET /api/top-options` | Scans all tickers for OTM puts with 6–15% annualized return and DTE of 7–14 or 30–45 days. Returns top 10 (one per symbol). Cached 1hr. |
| `GET /api/analyze-option/{symbol}` | Deep-dive for a single option: 2yr rolling-window historical verification + VADER sentiment on recent news headlines. |
| `GET /api/buy-calls` | Scans for ATM/slightly-OTM calls where HV > IV ("vol edge"). Categorizes as Short-Term (14–45 DTE) or Long-Term (90–180 DTE). |
| `GET /api/earnings` | Returns next earnings date for each ticker, sorted ascending. |

**Ranking logic for puts:**  
`score = annualizedReturn + (winRateEstimate / 5) - (riskScore * 10)`  
`riskScore = strike / support_level` where support level = 20th percentile close over last 6 months (lower is better).  
Only options with `winRateEstimate > 70%` are included.

### Frontend (`frontend/src/`)

React 19 SPA, no routing library — tab state managed in `App.jsx` with `useState`.

**Component responsibilities:**
- `App.jsx` — shell with three tabs (Puts / Calls / Earnings), manages puts fetch + loading/error state, owns `selectedOption` state that triggers the modal.
- `OptionCard.jsx` — card rendering a single put opportunity; click triggers `AnalysisModal`.
- `AnalysisModal.jsx` — fetches `/api/analyze-option/{symbol}` on mount; shows a Recharts price chart with a strike reference line, historical win-rate stats with drill-down crash events, and VADER-based news sentiment.
- `BuyCallsTab.jsx` — self-contained tab that fetches `/api/buy-calls` and renders results.
- `EarningsTab.jsx` — self-contained tab that fetches `/api/earnings`.

**Styling:** CSS variables defined in `index.css` (dark theme with glass-morphism panels). Inline styles are used heavily throughout components alongside CSS classes from `index.css`/`App.css`.

**API calls** all point to `http://localhost:8000` hardcoded — no environment variable abstraction.

## Permissions

These rules are enforced by the project's Claude Code settings and cannot be overridden.

**Always requires confirmation (`ask`) before running:**
- `git push` (any push)
- `rm` (any file deletion)
- Database migrations (`* migrate *`)
- `npm install -g` or `pip install`
- `WebFetch`

**Auto-approved (`allow`) without prompting:**
- `git status`, `git log`, `git diff`
- `npm run *`
- `pytest *`

**Hard-blocked (`deny`) — never attempt these:**
- `rm -rf`, `sudo rm`, or any destructive mass-delete
- `git push --force / -f`, `git reset --hard`, `git branch -D`
- `sudo`, `mkfs`, `dd`
- Piping remote scripts directly to a shell (`curl | bash`, `wget | bash`, etc.)
- Destructive SQL (`DROP TABLE`, `DROP DATABASE`, `TRUNCATE TABLE`)
- Reading credential/secret files (`.env`, `.env.*`, `~/.ssh/**`, `*.pem`, `*.key`, `~/.aws/**`, etc.)
- Editing shell config or system files (`~/.zshrc`, `~/.bashrc`, `/etc/**`)
- 在对话或代码中输出任何 API Key、Token、密码或环境变量的实际值（如 `$DATABASE_URL`）

## Key Constraints & Gotchas

- **No requirements.txt** — backend dependencies must be installed manually into the venv (`fastapi`, `uvicorn`, `yfinance`, `pandas`, `vaderSentiment`).
- **Slow first load** — `/api/top-options` can take 10–30s on cold cache because it serially calls `yf.Ticker()` for all 20 stocks and iterates every option chain.
- **In-memory cache only** — restarting the backend clears the cache; no persistence layer.
- **CORS is wide open** (`allow_origins=["*"]`) by design for local dev.
- The `calc_empirical_win_rate` function uses calendar DTE converted to trading days via `dte * 252 / 365`.
