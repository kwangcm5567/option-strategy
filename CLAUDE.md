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

**Alpha Options Strategy** — a full-stack app for quantitative options analysis. It scans ~50 US large-cap stocks and ETFs across four strategies (sell put / buy call / sell call / buy put), applies institutional-grade filters (σ-distance, Delta, ROC, IV premium, empirical win-rate, RSI/MACD timing), and presents ranked opportunities in a React dashboard. The backend fetches live data from Yahoo Finance via `yfinance` (optionally Financial Modeling Prep when `FMP_API_KEY` is set) and does all math server-side. Deployed on Render (`render.yaml`): backend web service + static frontend, both free tier.

## Running the App

**Backend** (FastAPI, port 8000):
```bash
cd backend
source venv/Scripts/activate          # venv is a Windows venv (Scripts/, not bin/)
pip install -r requirements.txt       # first time
python main.py                        # or: uvicorn main:app --reload --port 8000
```
> WSL note: 直接调用 `./venv/Scripts/python.exe` 也能跑。临时脚本别放 `/tmp`（会被当成 Windows 路径），放进项目目录。

**Frontend** (React + Vite, port 5173):
```bash
cd frontend
npm install                           # first time
npm run dev
```
Frontend API base comes from `VITE_API_URL` (see `frontend/.env.example`); empty → `http://localhost:8000`.

**Lint / build frontend:**
```bash
cd frontend && npm run lint
cd frontend && npm run build          # 推送重大改动前先本地构建验证
```

There are no backend tests and no frontend test suite currently.

## Architecture

### Backend — modular FastAPI (`backend/`)

`main.py` is just the app shell + CORS + `/` and `/api/health`. Logic is split into:
- `routers/` — `scanner` (`/api/scan`, `/api/analyze/{symbol}`, `/api/simulate-roll/{symbol}`), `chain`, `positions`, `market`, `earnings`, `news`, `portfolio`, `analytics`.
- `services/` — `scanner` (core scan + filters + scoring), `greeks` (Black-Scholes via `math.erf`, no scipy), `cache` (in-memory dict, 1hr TTL), `news`.
- `database.py` + `positions.db` — SQLite for tracked positions.

**Core scan — `services/scanner.py`:**
- `TICKERS` — ~50 large-caps + ETFs.
- `scan_options(strategies, dte_min, dte_max, min_iv_rank, relaxed)` — runs `_process_ticker` across all tickers in a `ThreadPoolExecutor(max_workers=8)`, dedups to one row per (symbol, strategy), returns top 50 by `score`.
- `_process_row(...)` — per-option filtering + metrics. Hard gates (strict mode) for sell_put: distance 2–20%, annualized 8–80%, σ-distance ≥ 1.0, ROC ≤ 40, |Delta| 0.10–0.40, empirical win-rate ≥ 70%. A `relaxed` flag widens all of these (distance 1–30%, ann 3–120%, σ ≥ 0.7, ROC ≤ 60, |Delta| 0.05–0.50, win-rate ≥ 55%) and tags each result with `relaxed: true`.
- `_calc_empirical_win_rate(...)` — rolling-window backtest (calendar DTE → trading days via `dte * 252 / 365`); precomputed once per ticker+DTE and reused across strikes.
- `_score(opt)` — strategy-specific weighted score (sellers: ROC / IV-premium / Delta / σ-distance sweet spots; buyers: RSI+MACD timing / IV cheapness / Delta).

**Empty-result auto-relax:** `/api/scan` first scans strict; if that yields nothing (and the caller didn't already request relaxed), it auto re-scans with `relaxed=True` and returns `relaxed: true` so the UI can flag it. Callers can also force relaxed via `?relaxed=true`.

### Frontend (`frontend/src/`)

React 19 SPA, no routing library — tab state in `App.jsx` with `useState`. App mounts a fire-and-forget `/api/health` ping to warm the sleeping Render backend.

**Active code lives in `frontend/src/tabs/`** — seven tabs: `scanner`, `strategy`, `positions`, `income`, `enhance`, `earnings`, `market`. Shared bits: `hooks/useApi.js` (`API_BASE` + `useApi` with 90s default timeout + visibility-aware retry), `components/ui/` (LoadingSpinner, Tooltip), `charts/`, `constants/tooltips.js`.

> ⚠️ `frontend/src/components/` top-level files were dead duplicates and have been deleted; only `components/ui/` is live. Don't recreate component code there — new tab UI goes under `tabs/`.

**Styling:** CSS variables in `index.css` (dark glass-morphism). Inline styles are used heavily alongside `index.css` / `App.css` classes.

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

- **Deps in `backend/requirements.txt`** (`fastapi`, `uvicorn`, `yfinance`, `pandas`, `vaderSentiment`). Greeks use `math.erf` — no scipy/numpy needed beyond what pandas pulls in.
- **Slow first scan** — a cold scan across ~50 tickers takes ~20s+ even with the thread pool; results cache 1hr (keyed by strategy/DTE/IV-rank/mode). The frontend `/api/health` warm-up ping mitigates Render free-tier cold start (the service sleeps when idle).
- **In-memory cache only** — restarting (or Render spin-down) clears it; no persistence layer. A disk cache wouldn't survive Render free-tier ephemeral fs, so it's intentionally not added.
- **CORS is wide open** (`allow_origins=["*"]`).
- `_calc_empirical_win_rate` converts calendar DTE to trading days via `dte * 252 / 365`.
- **GitHub `origin/main` is the source of truth** — multiple agents push concurrently; always `git fetch` before assuming local is current.
