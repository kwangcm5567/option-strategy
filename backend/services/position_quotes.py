"""Position marks from exact option quotes; models are only used for risk estimates."""
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import yfinance as yf

from . import cboe
from .greeks import calc_black_scholes
from .payoff import _bs_price

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
SCENARIOS = [
    ("大跌 15%", -0.15, 0.50), ("小跌 5%", -0.05, 0.20),
    ("平盘", 0.0, 0.0), ("小涨 5%", 0.05, -0.10), ("大涨 15%", 0.15, -0.20),
]


def _number(value) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _contract(chain: dict | None, pos: dict) -> dict | None:
    if not chain:
        return None
    rows = chain.get("puts" if "put" in pos["strategy"] else "calls")
    if rows is None or rows.empty:
        return None
    matches = rows.loc[rows["strike"].eq(pos["strike"])]
    if matches.empty:
        return None
    row = matches.iloc[0].to_dict()
    bid, ask = _number(row.get("bid")), _number(row.get("ask"))
    if bid is None or ask is None or not 0 <= bid <= ask or ask <= 0:
        return None
    # A long position with no bid has no observable liquidation price.
    if not pos["strategy"].startswith("sell_") and bid == 0:
        return None
    return {"bid": bid, "ask": ask, "iv": _number(row.get("impliedVolatility"))}


def _load_symbol(symbol: str, positions: list[dict], force_refresh: bool) -> dict:
    source = cboe.fetch(symbol, force_refresh=force_refresh)
    ticker = None
    yahoo_chains = {}
    quotes = {}
    for pos in positions:
        expiry = pos["expiration_date"]
        row = _contract((source or {}).get("chains", {}).get(expiry), pos)
        spot = _number((source or {}).get("current_price"))
        if row is not None and spot is not None and spot > 0:
            quotes[pos["id"]] = {**row, "spot": spot, "source": "cboe",
                                  "quoteAsOf": source.get("quote_as_of"),
                                  "quoteStatus": "delayed"}
            continue
        try:
            if ticker is None:
                ticker = yf.Ticker(symbol)
            if expiry not in yahoo_chains:
                yahoo_chains[expiry] = ticker.option_chain(expiry)
            chain = yahoo_chains[expiry]
            row = _contract({"puts": chain.puts, "calls": chain.calls}, pos)
            spot = _number((chain.underlying or {}).get("regularMarketPrice"))
            if row is not None and spot is not None and spot > 0:
                quotes[pos["id"]] = {**row, "spot": spot, "source": "yfinance",
                                      "quoteAsOf": None, "quoteStatus": "time_unknown"}
        except Exception as exc:
            logger.warning("Position quote unavailable for %s %s: %s", symbol, expiry, type(exc).__name__)
            yahoo_chains[expiry] = None
    return quotes


def mark_position(pos: dict, quote: dict | None, now: datetime) -> dict:
    expiry = datetime.strptime(pos["expiration_date"], "%Y-%m-%d").date()
    dte = (expiry - now.astimezone(NY).date()).days
    result = {
        "id": pos["id"], "symbol": pos["symbol"], "strategy": pos["strategy"],
        "quantity": pos["quantity"], "strike": pos["strike"], "dte": dte,
        "currentPrice": None, "currentPremium": None, "unrealizedPnl": None,
        "unrealizedPnlPct": None, "profitProgress": None,
        "delta": None, "theta": None, "positionDelta": None,
        "positionTheta": None, "positionVega": None,
        "quoteAsOf": None, "source": None, "quoteStatus": "unavailable",
    }
    if dte < 0:
        return {**result, "error": "已过到期日，请核对平仓或行权记录", "quoteStatus": "expired"}
    if quote is None:
        return {**result, "error": "未取得该到期日及行权价的有效 Bid/Ask，暂不计算盈亏"}
    sign = -1 if pos["strategy"].startswith("sell_") else 1
    mult = pos["quantity"] * 100
    premium = quote["ask"] if sign == -1 else quote["bid"]
    pnl = (premium - pos["premium"]) * sign * mult
    entry_value = pos["premium"] * mult
    percent = round(pnl / entry_value * 100, 1) if entry_value > 0 else None
    result.update({
        "currentPrice": quote["spot"], "currentPremium": premium,
        "bid": quote["bid"], "ask": quote["ask"],
        "markBasis": "ask" if sign == -1 else "bid",
        "unrealizedPnl": round(pnl, 2), "unrealizedPnlPct": percent,
        "profitProgress": percent if sign == -1 else None,
        "source": quote["source"], "quoteAsOf": quote["quoteAsOf"],
        "quoteStatus": quote["quoteStatus"],
    })
    iv = quote["iv"]
    if iv is None or iv <= 0:
        return result
    expiry_time = datetime.combine(expiry, time(16), tzinfo=NY)
    model_dte = max((expiry_time - now).total_seconds() / 86400, 1 / 1440)
    kind = "put" if "put" in pos["strategy"] else "call"
    greeks = calc_black_scholes(quote["spot"], pos["strike"], model_dte, iv, kind)
    if greeks:
        result.update({
            "iv": iv, "modelDte": model_dte, "delta": greeks["delta"],
            "theta": greeks["theta_day"],
            "positionDelta": round(greeks["delta"] * mult * sign, 3),
            "positionTheta": round(greeks["theta_day"] * mult * sign, 2),
            "positionVega": round(greeks["vega_1pct"] * mult * sign, 2),
        })
    return result


def aggregate_greeks(positions: list[dict], rows: list[dict]) -> dict:
    complete = all(row["positionDelta"] is not None for row in rows)
    values = {}
    for target, key in [("totalDelta", "positionDelta"), ("totalTheta", "positionTheta"),
                        ("totalVega", "positionVega")]:
        values[target] = round(sum(row[key] for row in rows), 3) if complete else None
    capital = 0.0
    unknown_capital = False
    for pos in positions:
        if pos["strategy"] == "sell_put":
            capital += pos["strike"] * pos["quantity"] * 100
        elif pos["strategy"].startswith("buy_"):
            capital += pos["premium"] * pos["quantity"] * 100
        else:
            unknown_capital = True
    return {
        **values, "dailyThetaIncome": values["totalTheta"],
        "totalCapitalAtRisk": None if unknown_capital else round(capital, 2),
        "sellPutCount": sum(p["quantity"] for p in positions if p["strategy"] == "sell_put"),
        "buyCallCount": sum(p["quantity"] for p in positions if p["strategy"] == "buy_call"),
        "complete": complete,
    }


def stress_scenarios(rows: list[dict]) -> list[dict]:
    complete = all(row["positionDelta"] is not None for row in rows)
    scenarios = []
    for label, spot_change, iv_change in SCENARIOS:
        total = 0.0
        if complete:
            for row in rows:
                kind = "put" if "put" in row["strategy"] else "call"
                base = _bs_price(row["currentPrice"], row["strike"], row["modelDte"], row["iv"], kind)
                stressed = _bs_price(row["currentPrice"] * (1 + spot_change), row["strike"],
                                     row["modelDte"], row["iv"] * (1 + iv_change), kind)
                sign = -1 if row["strategy"].startswith("sell_") else 1
                total += (stressed - base) * sign * row["quantity"] * 100
        scenarios.append({"label": label, "spotChg": spot_change, "ivChg": iv_change,
                          "pnlChange": round(total, 2) if complete else None})
    return scenarios


def build_snapshot(positions: list[dict], force_refresh: bool = False,
                   now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    grouped = {}
    for pos in positions:
        if pos["expiration_date"] >= now.astimezone(NY).date().isoformat():
            grouped.setdefault(pos["symbol"], []).append(pos)
    quotes = {}
    if grouped:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_load_symbol, symbol, items, force_refresh)
                       for symbol, items in grouped.items()]
            for future in futures:
                quotes.update(future.result())
    rows = [mark_position(pos, quotes.get(pos["id"]), now) for pos in positions]
    return {"data": rows, "greeks": aggregate_greeks(positions, rows),
            "scenarios": stress_scenarios(rows),
            "fetchedAt": datetime.now(timezone.utc).isoformat()}
