"""A small cash-secured put screen. Rules are hypotheses, not a tested edge."""
import math

from .greeks import calc_black_scholes

SIMPLE_TICKERS = ("SPY", "QQQ", "IWM")


def evaluate_put(
    row, symbol: str, spot: float, expiration: str, dte: int,
    fee_per_contract: float, slippage_per_share: float,
) -> dict | None:
    if symbol not in SIMPLE_TICKERS or not 30 <= dte <= 45:
        return None
    try:
        strike = float(row.get("strike", 0))
        bid = float(row.get("bid", 0))
        ask = float(row.get("ask", 0))
        iv = float(row.get("impliedVolatility", 0))
        oi = float(row.get("openInterest", 0))
    except (TypeError, ValueError):
        return None
    values = (spot, strike, bid, ask, iv, oi, fee_per_contract, slippage_per_share)
    if not all(math.isfinite(value) for value in values):
        return None
    if not (0 < strike < spot and 0.05 <= bid <= ask < strike and iv >= 0.005 and oi >= 100):
        return None
    if fee_per_contract < 0 or slippage_per_share < 0:
        return None
    spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
    if spread_pct > 10:
        return None
    greeks = calc_black_scholes(spot, strike, dte, iv, "put")
    if not greeks or not 0.15 <= abs(greeks["delta"]) <= 0.30:
        return None

    # Reserve both entry and exit costs even if the option expires worthless.
    costs = 2 * (fee_per_contract + slippage_per_share * 100)
    net_credit = bid * 100 - costs
    close_target = math.floor(bid * 0.5 * 100) / 100
    target_profit = (bid - close_target) * 100 - costs
    if net_credit <= 0 or target_profit <= 0:
        return None
    collateral = strike * 100
    return {
        "symbol": symbol, "strategy": "sell_put", "profile": "simple",
        "currentPrice": round(spot, 2), "strike": strike,
        "expirationDate": expiration, "dte": dte,
        "premium": bid, "bid": bid, "ask": ask, "priceBasis": "bid",
        "delta": greeks["delta"], "openInterest": int(oi),
        "bidAskSpreadPct": round(spread_pct, 2),
        "capitalRequired": round(collateral, 2),
        "estimatedRoundTripCosts": round(costs, 2),
        "netCredit": round(net_credit, 2),
        "netReturnPct": round(net_credit / collateral * 100, 3),
        "netBreakEven": round(strike - net_credit / 100, 2),
        "netMaxLoss": round(collateral - net_credit, 2),
        "closeTarget": close_target,
        "targetNetProfit": round(target_profit, 2),
    }
