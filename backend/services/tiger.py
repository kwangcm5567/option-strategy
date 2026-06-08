"""
老虎证券 Tiger Open API 期权链/股价数据源（最高优先级，延迟行情即可，免费）。

需要三个环境变量才启用，否则 enabled() 返回 False、自动回退 CBOE：
  TIGER_ID            开放平台 tiger_id
  TIGER_ACCOUNT       交易账号
  TIGER_PRIVATE_KEY   RSA 私钥 PEM 内容（换行可用 \\n 转义）

返回结构与 cboe.fetch 完全一致：
  {current_price, prev_close, change_pct, iv30, chains{expiry: {"puts": df, "calls": df}}}
"""
import logging
import math
import os
import threading
from datetime import datetime

import pandas as pd

logger = logging.getLogger("scanner")

_COLUMNS = ["strike", "lastPrice", "bid", "ask", "impliedVolatility", "volume", "openInterest"]

# Tiger 官方 API 频率限制未公开，保守限并发
_SEM = threading.Semaphore(4)
_client = None
_client_lock = threading.Lock()
_client_failed = False  # 初始化失败后本进程不再重试，直接回退


def enabled() -> bool:
    return bool(
        os.environ.get("TIGER_ID")
        and os.environ.get("TIGER_ACCOUNT")
        and os.environ.get("TIGER_PRIVATE_KEY")
    )


def _get_client():
    global _client, _client_failed
    if _client is not None or _client_failed:
        return _client
    with _client_lock:
        if _client is None and not _client_failed:
            try:
                from tigeropen.tiger_open_config import TigerOpenClientConfig
                from tigeropen.quote.quote_client import QuoteClient

                config = TigerOpenClientConfig()
                config.private_key = os.environ["TIGER_PRIVATE_KEY"].replace("\\n", "\n")
                config.tiger_id = os.environ["TIGER_ID"]
                config.account = os.environ["TIGER_ACCOUNT"]
                _client = QuoteClient(config)
            except Exception as e:
                logger.warning("[tiger] 客户端初始化失败，回退其他数据源: %s", e)
                _client_failed = True
    return _client


def _num(series_or_val, default: float = 0.0):
    return pd.to_numeric(series_or_val, errors="coerce").fillna(default)


def _map_chain(df: pd.DataFrame, put_call: str) -> pd.DataFrame:
    sub = df[df["put_call"].str.upper() == put_call]
    if sub.empty:
        return pd.DataFrame(columns=_COLUMNS)

    def col(name: str):
        return _num(sub[name]) if name in sub.columns else 0.0

    return pd.DataFrame({
        "strike": col("strike"),
        "lastPrice": col("latest_price"),
        "bid": col("bid_price"),
        "ask": col("ask_price"),
        "impliedVolatility": col("implied_vol"),
        "volume": col("volume"),
        "openInterest": col("open_interest"),
    }).reset_index(drop=True)


def _select_expiries(exp_df: pd.DataFrame, today: datetime, dte_min: int, dte_max: int) -> list[tuple]:
    """返回窗口内、最多 4 个到期日的 [(date_str, timestamp_ms)]。"""
    rows = []
    for _, r in exp_df.iterrows():
        date_str = str(r.get("date", "")).strip()
        try:
            dte = (datetime.strptime(date_str, "%Y-%m-%d") - today).days
        except ValueError:
            continue
        if dte_min <= dte <= dte_max:
            rows.append((date_str, int(r["timestamp"]) if "timestamp" in exp_df.columns and not pd.isna(r["timestamp"]) else date_str))
    if len(rows) > 4:
        idx = sorted({0, len(rows) // 3, len(rows) * 2 // 3, len(rows) - 1})
        rows = [rows[i] for i in idx]
    return rows


def fetch(symbol: str, today: datetime, dte_min: int, dte_max: int) -> dict | None:
    if not enabled():
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        from tigeropen.common.consts import Market

        with _SEM:
            briefs = client.get_stock_briefs([symbol], include_hour_trading=True)
        if briefs is None or len(briefs) == 0:
            return None
        b = briefs.iloc[0]
        prev_close = float(b["pre_close"]) if not pd.isna(b.get("pre_close")) else 0.0
        latest = float(b["latest_price"]) if not pd.isna(b.get("latest_price")) else 0.0
        hour_px = b.get("hour_trading_latest_price")
        if hour_px is not None and not pd.isna(hour_px) and float(hour_px) > 0:
            current_price = float(hour_px)
        else:
            current_price = latest
        change_pct = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else None

        with _SEM:
            exp_df = client.get_option_expirations(symbols=[symbol], market=Market.US)
        if exp_df is None or len(exp_df) == 0:
            return None
        selected = _select_expiries(exp_df, today, dte_min, dte_max)
        if not selected:
            return None

        chains: dict[str, dict] = {}
        for date_str, expiry_param in selected:
            with _SEM:
                chain_df = client.get_option_chain(
                    symbol, expiry_param, market=Market.US, return_greek_value=True
                )
            if chain_df is None or len(chain_df) == 0:
                continue
            chains[date_str] = {
                "puts": _map_chain(chain_df, "PUT"),
                "calls": _map_chain(chain_df, "CALL"),
            }
        if not chains:
            return None

        return {
            "current_price": current_price if current_price > 0 else None,
            "prev_close": prev_close or None,
            "change_pct": change_pct,
            "iv30": None,
            "chains": chains,
        }
    except Exception as e:
        logger.warning("[tiger] %s 失败，回退其他数据源: %s", symbol, e)
        return None
