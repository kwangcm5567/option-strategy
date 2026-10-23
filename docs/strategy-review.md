# Strategy review and simplified scanner

The project is a useful options research dashboard, but its previous scores and
stock-price statistics did not establish a profitable trading strategy. The new
default is a small, cost-aware cash-secured put screen. Advanced tools remain
available through **高级扫描**. No trades are submitted by this change.

## What changed

- Empty scans stay empty. The API no longer automatically relaxes filters or
  disables quality gates to manufacture candidates.
- The simple universe is SPY, QQQ, and IWM, with 30–45 calendar days to expiry,
  absolute Black–Scholes delta of 0.15–0.30, open interest of at least 100, and a
  bid/ask spread no larger than 10% of midpoint. Invalid, one-sided, crossed,
  nonfinite, and implausible quotes are rejected. These thresholds are research
  defaults, not optimized or validated profit parameters.
- Selling uses bid; buying in the advanced scanner uses ask. Old last-trade
  prices no longer drive the regular scanner's return calculations.
- Simple-mode costs are configurable: fees per contract per side and slippage
  per share per side. Defaults of $0.65 and $0.01 are illustrative. Both entry and
  exit costs are reserved, including when modeling worthless expiry. Taxes,
  assignment charges, collateral interest, and broker-specific minimum fees are
  not separately modeled.
- Each simple card shows cash collateral, net credit, return on collateral for
  this expiry, break-even, and loss if the underlying becomes worthless. A
  half-premium buyback reference shows estimated profit after the cost reserve;
  candidates with nonpositive profit at that reference are excluded. This is
  not an automatic exit order or a tested optimal exit rule.
- A user-supplied cash cap filters individual contracts before selecting one
  contract per ETF. It is not a portfolio allocator and does not subtract
  existing positions. Blank or zero means no cash filter.
- Selection prioritizes delta nearest 0.20, then tighter spread, then higher net
  credit/collateral. The order is a transparent heuristic, not expected profit.
- Historical windows now use each contract's actual DTE, begin after entry
  close, and include the final trading session. Insufficient history produces
  missing statistics rather than 100% success. DTE uses New York calendar dates.
- Historical touch rates are labeled as price-path statistics, not trading win
  rates. The detailed downside analysis is shown only for sell puts. Model
  direction is corrected for buy puts and sell calls.
- The advanced 2% sizing calculation can return zero and refuses unknown or
  unlimited maximum losses. It no longer forces an unaffordable first contract.

## How to interpret the strategy

A cash-secured put is appropriate only when the trader is willing and able to
buy the underlying shares at the strike. Reserving cash does not protect their
value after a price decline. The Options Industry Council describes the strategy
and its substantial downside in its
[cash-secured put guide](https://www.optionseducation.org/strategies/all-strategies/cash-secured-put).
American-style short options can be assigned before expiration; see the
[OIC assignment FAQ](https://www.optionseducation.org/referencelibrary/faq/options-assignment).

SPY, QQQ, and IWM share equity-market exposure. Treat their combined exposure as
part of the same portfolio risk budget. If one contract does not fit the cash
budget, the simple screen should return no candidates; it should not compensate
by increasing leverage. A defined-risk spread would require a separate strategy
and validation, not a silent fallback.

Quote validity does not establish freshness. CBOE/Yahoo data may be delayed or
retain closing quotes; the UI explicitly requires checking broker quotes before
trading. Simple scans cache for five minutes. Data-fetch failures can also result
in an empty screen; no result is not proof that the entire market was scanned
successfully.

## Profitability is not yet established

The repository does not contain historical option bid/ask chains sufficient to
run an execution-aware strategy backtest. Current IV is compared to historical
realized volatility in the advanced scanner; its “IV Rank” is a proxy, not a
historical IV percentile. Other advanced scoring and management suggestions
remain heuristics.

Before treating the simple screen as a trading system, collect timestamped
option quotes and test a fixed entry/exit policy against buy-and-hold and cash.
Use an untouched evaluation period, costs and realistic fills, mark-to-market
drawdowns, assignment treatment, cash utilization, and combined ETF exposure.
Report net return, maximum drawdown, average win/loss, and sample count together.
Do not select rules on the same data used to report their performance.

## Verification

- Backend: `cd backend && python -m pytest -q` after installing
  `requirements-dev.txt`. Tests use mocked chains and a standalone FastAPI router;
  they do not import the live application or modify the portfolio database.
- Frontend: `cd frontend && pnpm test && pnpm build`.
- Browser smoke test: run Vite at `127.0.0.1:5173`, then execute
  `python tests/scanner_smoke.py` from `frontend/` with Playwright installed.
  The test mocks every API request and covers populated/empty results, submitted
  cost/cash inputs, refresh, failure recovery, mode switching, and mobile layout.

Verified in this workspace: 93 backend tests, three position-sizing tests,
production build, and mocked browser smoke checks. New JavaScript files pass
lint; the full lint run still reports ten pre-existing errors in legacy files.
The Linux browser host lacks a usable CJK font, so Chinese labels were checked
through DOM assertions; screenshot typography needs a host with CJK fonts.

Passing these tests validates implementation behavior, not investment returns.
