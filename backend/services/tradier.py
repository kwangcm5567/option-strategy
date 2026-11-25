"""
Tradier 期权链（sandbox 免费、15 分钟延迟；设置环境变量 TRADIER_TOKEN 启用）。

不封机房 IP，作为期权链主数据源。sandbox 市场数据限 60 次/分钟（按 token），
所有请求共用一个全局限速器；到期日列表缓存 6 小时，期权链缓存 2 分钟。
"""
import logging
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests

logger = logging.getLogger("scanner")

_DEFAULT_BASE = "https://sandbox.tradier.com/v1"
_COLUMNS = ["strike", "lastPrice", "bid", "ask", "impliedVolatility", "volume", "openInterest"]
_MIN_INTERVAL = 1.05
_EXP_TTL = 6 * 3600
_CHAIN_TTL = 120
_QUOTE_TTL = 60

_rate_lock = threading.Lock()
_next_slot = 0.0
_cache_lock = threading.Lock()
_exp_cache: dict[str, tuple[float, list[str]]] = {}
_chain_cache: dict[tuple[str, str], tuple[float, dict[str, pd.DataFrame]]] = {}
_quote_cache: dict[str, tuple[float, dict]] = {}


def enabled() -> bool:
    return bool(os.environ.get("TRADIER_TOKEN"))


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _wait_slot() -> None:
    global _next_slot
    with _rate_lock:
        now = time.monotonic()
        wait = max(0.0, _next_slot - now)
        _next_slot = max(now, _next_slot) + _MIN_INTERVAL
    if wait:
        time.sleep(wait)


def _get(path: str, params: dict) -> dict | None:
    token = os.environ.get("TRADIER_TOKEN")
    if not token:
        return None
    url = f"{os.environ.get('TRADIER_BASE_URL', _DEFAULT_BASE)}{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    for attempt in range(3):
        _wait_slot()
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
        except requests.RequestException as e:
            logger.warning("[tradier] %s %s 请求异常: %s", path, params.get("symbol") or params.get("symbols"), e)
            return None
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                return None
        if resp.status_code == 429 and attempt < 2:
            time.sleep(5 * (attempt + 1))
            continue
        logger.warning("[tradier] %s %s → HTTP %s", path, params.get("symbol") or "", resp.status_code)
        return None
    return None


def _cached(store: dict, key, ttl: float):
    with _cache_lock:
        hit = store.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    return None


def _store(store: dict, key, value) -> None:
    with _cache_lock:
        store[key] = (time.time(), value)


def _expirations(symbol: str) -> list[str]:
    hit = _cached(_exp_cache, symbol, _EXP_TTL)
    if hit is not None:
        return hit
    payload = _get("/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"})
    dates = sorted(_as_list(((payload or {}).get("expirations") or {}).get("date")))
    if dates:
        _store(_exp_cache, symbol, dates)
    return dates


def _chain(symbol: str, expiration: str) -> dict[str, pd.DataFrame] | None:
    hit = _cached(_chain_cache, (symbol, expiration), _CHAIN_TTL)
    if hit is not None:
        return hit
    payload = _get("/markets/options/chains",
                   {"symbol": symbol, "expiration": expiration, "greeks": "true"})
    options = _as_list(((payload or {}).get("options") or {}).get("option"))
    if not options:
        return None
    rows: dict[str, list[dict]] = {"calls": [], "puts": []}
    for o in options:
        greeks = o.get("greeks") or {}
        side = "calls" if o.get("option_type") == "call" else "puts"
        rows[side].append({
            "strike": _f(o.get("strike")),
            "lastPrice": _f(o.get("last")),
            "bid": _f(o.get("bid")),
            "ask": _f(o.get("ask")),
            "impliedVolatility": _f(greeks.get("mid_iv")) or _f(greeks.get("smv_vol")),
            "volume": _f(o.get("volume")),
            "openInterest": _f(o.get("open_interest")),
        })
    chain = {side: pd.DataFrame(v, columns=_COLUMNS).sort_values("strike", ignore_index=True)
             for side, v in rows.items()}
    _store(_chain_cache, (symbol, expiration), chain)
    return chain


def prefetch_quotes(symbols: list[str]) -> None:
    """扫描前一次请求批量取所有标的现价，省掉逐只请求。"""
    if not enabled() or not symbols:
        return
    payload = _get("/markets/quotes", {"symbols": ",".join(symbols)})
    for q in _as_list(((payload or {}).get("quotes") or {}).get("quote")):
        if q.get("symbol"):
            _store(_quote_cache, q["symbol"], q)


def _quote(symbol: str) -> dict:
    hit = _cached(_quote_cache, symbol, _QUOTE_TTL)
    if hit is not None:
        return hit
    prefetch_quotes([symbol])
    return _cached(_quote_cache, symbol, _QUOTE_TTL) or {}


def _pick(dates: list[str], n: int) -> list[str]:
    if len(dates) <= n:
        return dates
    return [dates[i * (len(dates) - 1) // (n - 1)] for i in range(n)]


def fetch(symbol: str, dte_min: int, dte_max: int, max_expirations: int) -> dict | None:
    """与 cboe.fetch 同结构；只取 DTE 范围内均匀抽样的 max_expirations 个到期日。未启用或失败返回 None。"""
    if not enabled():
        return None
    symbol = symbol.upper()
    today = datetime.now(ZoneInfo("America/New_York")).date()
    in_range = [d for d in _expirations(symbol)
                if dte_min <= (datetime.strptime(d, "%Y-%m-%d").date() - today).days <= dte_max]
    chains = {}
    for exp in _pick(in_range, max_expirations):
        chain = _chain(symbol, exp)
        if chain is not None:
            chains[exp] = chain
    if not chains:
        return None
    quote = _quote(symbol)
    price = _f(quote.get("last")) or _f(quote.get("prevclose"))
    change = quote.get("change_percentage")
    return {
        "current_price": price or None,
        "prev_close": _f(quote.get("prevclose")) or None,
        "change_pct": round(_f(change), 2) if change is not None else None,
        "iv30": None,
        "chains": chains,
        "quote_as_of": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
