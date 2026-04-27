"""
/api/market-overview  —  VIX 指数 + 20 只股票的 IV Rank 热力图
"""
import math

import yfinance as yf
from fastapi import APIRouter

from services import cache as cache_svc
from services.greeks import calc_iv_rank
from services.scanner import TICKERS

router = APIRouter()


def _vix_description(vix: float) -> str:
    if vix < 15:
        return "市场非常平静，期权相对便宜，卖方优势较小"
    if vix < 20:
        return "市场正常波动，期权价格适中"
    if vix < 30:
        return "市场有些紧张，期权偏贵，卖方开始有优势"
    if vix < 40:
        return "市场恐慌，期权很贵，卖出期权的最佳时机之一"
    return "市场极度恐慌！期权价格极高，需谨慎控制仓位"


@router.get("/api/market-overview")
def market_overview(force_refresh: bool = False):
    cached = cache_svc.get("market_overview", ttl_seconds=1800)
    if not force_refresh and cached:
        return {"data": cached, "cached": True}

    # ── VIX ──
    vix_data = {}
    try:
        vix_ticker = yf.Ticker("^VIX")
        vix_hist = vix_ticker.history(period="1y")
        if not vix_hist.empty:
            current_vix = float(vix_hist["Close"].iloc[-1])
            vix_52w_low = float(vix_hist["Close"].min())
            vix_52w_high = float(vix_hist["Close"].max())
            vix_rank = round((current_vix - vix_52w_low) / (vix_52w_high - vix_52w_low) * 100, 1)
            vix_data = {
                "current": round(current_vix, 2),
                "weekLow52": round(vix_52w_low, 2),
                "weekHigh52": round(vix_52w_high, 2),
                "rank52w": vix_rank,
                "description": _vix_description(current_vix),
            }
    except Exception as e:
        print(f"[market] VIX 获取失败: {e}")

    # ── 各股票 IV Rank ──
    iv_ranks = []
    for symbol in TICKERS:
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period="1y")
            if history.empty:
                continue
            current_price = float(history["Close"].iloc[-1])

            # 取最近到期的 ATM put 的 IV 作为当前 IV 代表
            exp_dates = ticker.options
            current_iv = None
            for date_str in exp_dates[:3]:
                try:
                    chain = ticker.option_chain(date_str)
                    atm_puts = chain.puts[
                        (chain.puts["strike"] >= current_price * 0.97) &
                        (chain.puts["strike"] <= current_price * 1.03)
                    ]
                    if not atm_puts.empty:
                        current_iv = float(atm_puts["impliedVolatility"].median())
                        break
                except Exception:
                    continue

            if current_iv is None or current_iv <= 0:
                # fallback：用历史波动率
                daily_ret = history["Close"].pct_change().dropna()
                current_iv = float(daily_ret.std() * math.sqrt(252))

            iv_rank = calc_iv_rank(history, current_iv)
            iv_ranks.append({
                "symbol": symbol,
                "currentPrice": round(current_price, 2),
                "currentIV": round(current_iv * 100, 1),
                "ivRank": iv_rank,
            })
        except Exception as e:
            print(f"[market] {symbol} 跳过: {e}")
            continue

    result = {"vix": vix_data, "ivRanks": iv_ranks}
    cache_svc.set("market_overview", result)
    return {"data": result, "cached": False}
