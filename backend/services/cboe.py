"""
CBOE 免费延迟期权报价（15 分钟延迟，无需 API Key）。

相比 yfinance：不封锁数据中心 IP、始终返回真实 bid/ask/IV，一次请求拿到
全部到期日 + 标的现价 + 隔夜涨跌幅。作为期权链主数据源，yfinance 作兜底。
"""
import logging
import random
import threading
import time

import pandas as pd
import requests

logger = logging.getLogger("scanner")

_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

# CBOE 的 CDN 按 IP 限制突发请求（8 并发会全部 429，~3 并发安全），
# 用信号量限并发 + 429 退避重试；再加 120s 进程内缓存，避免 strict→relaxed→
# best_effort 多轮重扫时重复打。
_SEM = threading.Semaphore(3)
_CACHE_TTL = 120
_cache: dict[str, tuple[float, dict | None]] = {}
_cache_lock = threading.Lock()

# 与 yfinance option_chain DataFrame 对齐的列
_COLUMNS = ["strike", "lastPrice", "bid", "ask", "impliedVolatility", "volume", "openInterest"]


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_osi(osym: str, root: str) -> tuple[str, str, float] | None:
    """AAPL260608P00250000 → ('2026-06-08', 'P', 250.0)。"""
    rest = osym[len(root):] if osym.startswith(root) else osym.lstrip(root)
    if len(rest) < 15 or not rest[:6].isdigit():
        return None
    ymd, opt_type, strike_raw = rest[:6], rest[6], rest[7:15]
    if opt_type not in ("C", "P") or not strike_raw.isdigit():
        return None
    expiry = f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}"
    return expiry, opt_type, int(strike_raw) / 1000.0


def _get_json(symbol: str) -> dict | None:
    """限并发 + 429 退避，返回原始 JSON；失败返回 None。"""
    for attempt in range(3):
        with _SEM:
            try:
                resp = requests.get(_URL.format(symbol.upper()), headers=_HEADERS, timeout=15)
            except Exception as e:
                logger.warning("[cboe] %s 请求异常: %s", symbol, e)
                return None
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429 and attempt < 2:
            time.sleep(1.5 * (attempt + 1) + random.uniform(0, 0.5))
            continue
        return None
    return None


def fetch(symbol: str) -> dict | None:
    """成功返回 {current_price, prev_close, change_pct, iv30, chains}；失败返回 None。

    chains: {expiry: {"puts": DataFrame, "calls": DataFrame}}。
    """
    now = time.time()
    with _cache_lock:
        hit = _cache.get(symbol)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

    result = _build(symbol)
    with _cache_lock:
        _cache[symbol] = (now, result)
    return result


def _build(symbol: str) -> dict | None:
    try:
        payload = _get_json(symbol)
        if not payload:
            return None
        data = payload.get("data") or {}
        options = data.get("options") or []
        if not options:
            return None

        root = symbol.upper()
        by_exp: dict[str, dict[str, list]] = {}
        for o in options:
            parsed = _parse_osi(o.get("option", ""), root)
            if not parsed:
                continue
            expiry, opt_type, strike = parsed
            rec = {
                "strike": strike,
                "lastPrice": _f(o.get("last_trade_price")),
                "bid": _f(o.get("bid")),
                "ask": _f(o.get("ask")),
                "impliedVolatility": _f(o.get("iv")),
                "volume": _f(o.get("volume")),
                "openInterest": _f(o.get("open_interest")),
            }
            slot = by_exp.setdefault(expiry, {"calls": [], "puts": []})
            slot["calls" if opt_type == "C" else "puts"].append(rec)

        if not by_exp:
            return None

        chains = {
            exp: {
                "puts": pd.DataFrame(v["puts"], columns=_COLUMNS),
                "calls": pd.DataFrame(v["calls"], columns=_COLUMNS),
            }
            for exp, v in by_exp.items()
        }

        current_price = _f(data.get("current_price"))
        return {
            "current_price": current_price if current_price > 0 else None,
            "prev_close": _f(data.get("prev_day_close")) or None,
            "change_pct": round(_f(data.get("price_change_percent")), 2),
            "iv30": round(_f(data.get("iv30")), 1) or None,
            "chains": chains,
        }
    except Exception as e:
        logger.warning("[cboe] %s 失败: %s", symbol, e)
        return None
