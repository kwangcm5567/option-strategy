"""
Alpaca 期权链（免费 indicative feed；设置 ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY 启用）。

报价 / IV 来自 data API 的期权快照，未平仓量来自 trading API 的合约列表（快照不含 OI）。
免费套餐 200 次/分钟，全局限速；合约列表缓存 6 小时，期权链缓存 2 分钟。
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests

logger = logging.getLogger("scanner")

_DATA_BASE = "https://data.alpaca.markets"
_TRADING_BASES = ["https://paper-api.alpaca.markets", "https://api.alpaca.markets"]
_COLUMNS = ["strike", "lastPrice", "bid", "ask", "impliedVolatility", "volume", "openInterest"]
_MIN_INTERVAL = 0.32
_CONTRACT_TTL = 6 * 3600
_CHAIN_TTL = 120
_QUOTE_TTL = 60
_STRIKE_BAND = 0.35

_rate_lock = threading.Lock()
_next_slot = 0.0
_cache_lock = threading.Lock()
_contract_cache: dict[tuple, tuple[float, dict[str, dict[str, float]]]] = {}
_chain_cache: dict[tuple[str, str], tuple[float, dict[str, pd.DataFrame]]] = {}
_quote_cache: dict[str, tuple[float, dict]] = {}
_trading_base: list[str] = []


def _keys() -> tuple[str, str] | None:
    key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    return (key, secret) if key and secret else None


def enabled() -> bool:
    return _keys() is not None


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _wait_slot() -> None:
    global _next_slot
    with _rate_lock:
        now = time.monotonic()
        wait = max(0.0, _next_slot - now)
        _next_slot = max(now, _next_slot) + _MIN_INTERVAL
    if wait:
        time.sleep(wait)


def _request(url: str, params: dict) -> tuple[int, dict | None]:
    keys = _keys()
    if not keys:
        return 0, None
    headers = {"APCA-API-KEY-ID": keys[0], "APCA-API-SECRET-KEY": keys[1], "Accept": "application/json"}
    for attempt in range(3):
        _wait_slot()
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
        except requests.RequestException as e:
            logger.warning("[alpaca] %s 请求异常: %s", url, e)
            return 0, None
        if resp.status_code == 429 and attempt < 2:
            time.sleep(3 * (attempt + 1))
            continue
        if resp.status_code != 200:
            logger.warning("[alpaca] %s %s → HTTP %s", url, params.get("underlying_symbols") or "", resp.status_code)
            return resp.status_code, None
        try:
            return 200, resp.json()
        except ValueError:
            return 200, None
    return 429, None


def _paged(url: str, params: dict, items_key: str) -> list | dict | None:
    """跟随分页把 items_key 合并；任何一页失败返回 None。"""
    merged: list | dict | None = None
    token = None
    for _ in range(20):
        status, payload = _request(url, {**params, **({"page_token": token} if token else {})})
        if payload is None:
            return None
        items = payload.get(items_key) or ([] if items_key == "option_contracts" else {})
        if merged is None:
            merged = items
        elif isinstance(merged, list):
            merged.extend(items)
        else:
            merged.update(items)
        token = payload.get("next_page_token") or payload.get("page_token")
        if not token:
            break
    return merged


def _cached(store: dict, key, ttl: float):
    with _cache_lock:
        hit = store.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    return None


def _store(store: dict, key, value) -> None:
    with _cache_lock:
        store[key] = (time.time(), value)


def prefetch_quotes(symbols: list[str]) -> None:
    """一次请求批量取标的现价。"""
    if not enabled() or not symbols:
        return
    _, payload = _request(f"{_DATA_BASE}/v2/stocks/snapshots",
                          {"symbols": ",".join(symbols), "feed": "iex"})
    snaps = (payload or {}).get("snapshots", payload) or {}
    for sym, snap in snaps.items():
        if isinstance(snap, dict):
            _store(_quote_cache, sym, snap)


def _quote(symbol: str) -> dict:
    hit = _cached(_quote_cache, symbol, _QUOTE_TTL)
    if hit is not None:
        return hit
    prefetch_quotes([symbol])
    return _cached(_quote_cache, symbol, _QUOTE_TTL) or {}


def _contracts(symbol: str, start: str, end: str, lo: float, hi: float) -> dict[str, dict[str, float]]:
    """{expiration: {contract_symbol: open_interest}}。"""
    key = (symbol, start, end, round(lo), round(hi))
    hit = _cached(_contract_cache, key, _CONTRACT_TTL)
    if hit is not None:
        return hit
    params = {"underlying_symbols": symbol, "expiration_date_gte": start, "expiration_date_lte": end,
              "strike_price_gte": f"{lo:.2f}", "strike_price_lte": f"{hi:.2f}", "limit": 10000}
    contracts = None
    for base in _trading_base or _TRADING_BASES:
        contracts = _paged(f"{base}/v2/options/contracts", params, "option_contracts")
        if contracts is not None:
            if not _trading_base:
                _trading_base.append(base)
            break
    by_exp: dict[str, dict[str, float]] = {}
    for c in contracts or []:
        if c.get("expiration_date") and c.get("symbol"):
            by_exp.setdefault(c["expiration_date"], {})[c["symbol"]] = _f(c.get("open_interest"))
    if by_exp:
        _store(_contract_cache, key, by_exp)
    return by_exp


def _chain(symbol: str, expiration: str, lo: float, hi: float,
           open_interest: dict[str, float]) -> dict[str, pd.DataFrame] | None:
    hit = _cached(_chain_cache, (symbol, expiration), _CHAIN_TTL)
    if hit is not None:
        return hit
    snaps = _paged(f"{_DATA_BASE}/v1beta1/options/snapshots/{symbol}",
                   {"feed": "indicative", "expiration_date": expiration, "limit": 1000,
                    "strike_price_gte": f"{lo:.2f}", "strike_price_lte": f"{hi:.2f}"}, "snapshots")
    if not snaps:
        return None
    rows: dict[str, list[dict]] = {"calls": [], "puts": []}
    for osym, snap in snaps.items():
        tail = osym[len(symbol):]
        if len(tail) < 15 or tail[6] not in ("C", "P") or not tail[7:15].isdigit():
            continue
        quote = snap.get("latestQuote") or {}
        rows["calls" if tail[6] == "C" else "puts"].append({
            "strike": int(tail[7:15]) / 1000.0,
            "lastPrice": _f((snap.get("latestTrade") or {}).get("p")),
            "bid": _f(quote.get("bp")),
            "ask": _f(quote.get("ap")),
            "impliedVolatility": _f(snap.get("impliedVolatility")),
            "volume": _f((snap.get("dailyBar") or {}).get("v")),
            "openInterest": open_interest.get(osym, 0.0),
        })
    chain = {side: pd.DataFrame(v, columns=_COLUMNS).sort_values("strike", ignore_index=True)
             for side, v in rows.items()}
    _store(_chain_cache, (symbol, expiration), chain)
    return chain


def _pick(dates: list[str], n: int) -> list[str]:
    if len(dates) <= n:
        return dates
    return [dates[i * (len(dates) - 1) // (n - 1)] for i in range(n)]


def fetch(symbol: str, dte_min: int, dte_max: int, max_expirations: int) -> dict | None:
    """与 cboe.fetch 同结构；只取 DTE 范围内均匀抽样的到期日、现价 ±35% 的行权价。"""
    if not enabled():
        return None
    symbol = symbol.upper()
    quote = _quote(symbol)
    price = _f((quote.get("latestTrade") or {}).get("p")) or _f((quote.get("dailyBar") or {}).get("c"))
    prev_close = _f((quote.get("prevDailyBar") or {}).get("c"))
    price = price or prev_close
    if not price:
        return None
    lo, hi = price * (1 - _STRIKE_BAND), price * (1 + _STRIKE_BAND)
    today = datetime.now(ZoneInfo("America/New_York")).date()
    start = (today + timedelta(days=dte_min)).isoformat()
    end = (today + timedelta(days=dte_max)).isoformat()
    by_exp = _contracts(symbol, start, end, lo, hi)
    chains = {}
    for exp in _pick(sorted(by_exp), max_expirations):
        chain = _chain(symbol, exp, lo, hi, by_exp[exp])
        if chain is not None:
            chains[exp] = chain
    if not chains:
        return None
    return {
        "current_price": price,
        "prev_close": prev_close or None,
        "change_pct": round((price / prev_close - 1) * 100, 2) if prev_close else None,
        "iv30": None,
        "chains": chains,
        "quote_as_of": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
