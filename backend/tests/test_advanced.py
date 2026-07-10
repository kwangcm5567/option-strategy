"""进阶模块纯函数单测：盈亏计算 / 价差构建与评分 / 风险台数学。无网络依赖。"""
from datetime import datetime, timedelta

import pandas as pd

from services.payoff import compute, scenario_grid, _bs_price
from services.scanner import FILTER_PROFILES
from services.spreads import _clean, _vertical, _iron_condor, _straddle_strangle, _score_spread
from services.risk import _beta, _correlation_matrix, _historical_var, _stress_test, _reval_price


# ═══ payoff ═══════════════════════════════════════════════════════════════════

def test_bs_price_expiry_is_intrinsic():
    assert _bs_price(110, 100, 0, 0.3, "call") == 10.0
    assert _bs_price(90, 100, 0, 0.3, "put") == 10.0
    assert _bs_price(100, 110, 0, 0.3, "call") == 0.0


def test_payoff_long_call():
    legs = [{"action": "buy", "type": "call", "strike": 100, "premium": 3.0, "iv": 0.3}]
    r = compute(legs, spot=100, dte=30)
    assert r["netEntry"] == 300.0
    assert r["isCredit"] is False
    assert r["maxLoss"] == -300.0                      # 最差情况亏掉全部权利金
    assert len(r["breakEvens"]) == 1
    assert abs(r["breakEvens"][0] - 103.0) < 1.0       # 盈亏平衡 ≈ 行权价 + 权利金
    # 到期曲线在最高价点：内在价值 - 成本
    top = r["curve"][-1]
    assert abs(top["expiryPnl"] - ((top["price"] - 100) * 100 - 300)) < 1.0


def test_payoff_bull_put_credit():
    legs = [
        {"action": "sell", "type": "put", "strike": 95, "premium": 2.0, "iv": 0.3},
        {"action": "buy", "type": "put", "strike": 90, "premium": 1.0, "iv": 0.3},
    ]
    r = compute(legs, spot=100, dte=30)
    assert r["isCredit"] is True
    assert r["netEntry"] == -100.0                     # 收到 $1.00 信用
    assert r["maxProfit"] == 100.0                     # 保住全部信用
    assert r["maxLoss"] == -400.0                      # 宽度 5 - 信用 1
    assert len(r["breakEvens"]) == 1
    assert abs(r["breakEvens"][0] - 94.0) < 0.5        # 短腿 95 - 信用 1


def test_scenario_grid_shape_and_direction():
    legs = [{"action": "buy", "type": "call", "strike": 100, "premium": 3.0, "iv": 0.3}]
    g = scenario_grid(legs, spot=100, dte=30)
    assert len(g["priceShocks"]) == 7
    assert len(g["grid"]) == 5
    assert all(len(row["pnls"]) == 7 for row in g["grid"])
    # 长 call：价格冲击越大盈亏越高（任一 IV 行内单调不减）
    mid_row = g["grid"][2]["pnls"]
    assert mid_row == sorted(mid_row)


# ═══ spreads ══════════════════════════════════════════════════════════════════

def _chain_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_clean_filters_and_adds_mid():
    df = _chain_df([
        {"strike": 100, "bid": 1.0, "ask": 1.2, "impliedVolatility": 0.3},
        {"strike": 95, "bid": 0.0, "ask": 1.0, "impliedVolatility": 0.3},   # bid=0 剔除
        {"strike": 90, "bid": 0.5, "ask": 0.7, "impliedVolatility": 0.001},  # IV 过低剔除
    ])
    d = _clean(df)
    assert len(d) == 1
    assert d.iloc[0]["mid"] == 1.1


def _leg_row(strike: float, mid: float, iv: float = 0.30) -> pd.Series:
    return pd.Series({"strike": strike, "mid": mid, "impliedVolatility": iv})


def test_vertical_bull_put_credit_math():
    v = _vertical(_leg_row(95, 2.0), _leg_row(90, 1.0), spot=100, dte=30,
                  kind="bull_put", exp="2099-01-01")
    assert v is not None
    assert v["netCredit"] == 1.0
    assert v["maxProfit"] == 100.0
    assert v["maxLoss"] == 400.0
    assert v["breakEven"] == 94.0
    assert v["creditWidthPct"] == 20.0
    assert v["legs"][0]["action"] == "sell" and v["legs"][0]["strike"] == 95
    assert v["legs"][1]["action"] == "buy" and v["legs"][1]["strike"] == 90


def test_vertical_rejects_tiny_credit():
    v = _vertical(_leg_row(95, 1.0), _leg_row(90, 0.99), spot=100, dte=30,
                  kind="bull_put", exp="2099-01-01")
    assert v is None


def test_vertical_bull_call_debit_math():
    # 买 100C @3.0，卖 105C @1.5 → 借记 1.5，宽度 5
    v = _vertical(_leg_row(105, 1.5), _leg_row(100, 3.0), spot=100, dte=30,
                  kind="bull_call", exp="2099-01-01")
    assert v is not None
    assert v["netDebit"] == 1.5
    assert v["maxProfit"] == 350.0
    assert v["maxLoss"] == 150.0
    assert v["breakEven"] == 101.5


def test_iron_condor_combines_wings():
    bp = _vertical(_leg_row(95, 2.0), _leg_row(90, 1.0), 100, 30, "bull_put", "2099-01-01")
    bc = _vertical(_leg_row(105, 1.8), _leg_row(110, 0.9), 100, 30, "bear_call", "2099-01-01")
    ic = _iron_condor(bp, bc, spot=100, exp="2099-01-01", dte=30)
    assert ic["netCredit"] == round(bp["netCredit"] + bc["netCredit"], 2)
    assert ic["maxProfit"] == round(ic["netCredit"] * 100, 2)
    assert ic["maxLoss"] == max(bp["maxLoss"], bc["maxLoss"])
    assert ic["lowerBreakEven"] == bp["breakEven"]
    assert ic["upperBreakEven"] == bc["breakEven"]
    assert len(ic["legs"]) == 4


def test_straddle_breakevens():
    calls = _chain_df([{"strike": 100, "mid": 3.0, "impliedVolatility": 0.30}])
    puts = _chain_df([{"strike": 100, "mid": 2.5, "impliedVolatility": 0.30}])
    s = _straddle_strangle(calls, puts, spot=100, exp="2099-01-01", dte=30, wide=False)
    assert s is not None
    assert s["netDebit"] == 5.5
    assert s["lowerBreakEven"] == 94.5
    assert s["upperBreakEven"] == 105.5
    assert s["maxLoss"] == 550.0


def test_score_spread_bounds():
    v = _vertical(_leg_row(95, 2.0), _leg_row(90, 1.0), 100, 30, "bull_put", "2099-01-01")
    assert 0.0 <= _score_spread(v) <= 1.0
    # 波动优势为正的跨式 > 无优势的
    hi = _score_spread({"type": "straddle", "moveEdge": 30})
    lo = _score_spread({"type": "straddle", "moveEdge": -30})
    assert hi > lo


# ═══ risk ═════════════════════════════════════════════════════════════════════

def _ret_series(vals: list[float]) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=len(vals), freq="D")
    return pd.Series(vals, index=idx)


def test_beta_of_leveraged_series():
    market = _ret_series([0.01, -0.02, 0.015, -0.005, 0.02] * 8)
    stock = market * 2
    assert _beta(stock, market) == 2.0


def test_beta_insufficient_data():
    short = _ret_series([0.01] * 10)
    assert _beta(short, short) is None


def test_correlation_matrix():
    a = _ret_series([0.01, -0.02, 0.015, -0.005, 0.02] * 8)
    c = _correlation_matrix({"A": a, "B": a * 3, "C": None})
    assert c["symbols"] == ["A", "B"]
    assert c["matrix"][0][1] == 1.0
    assert _correlation_matrix({"A": a}) == {"symbols": [], "matrix": []}


def _open_position(symbol: str = "AAPL", strategy: str = "sell_put",
                   strike: float = 95.0, quantity: int = 1) -> dict:
    exp = (datetime.now().date() + timedelta(days=30)).isoformat()
    return {"id": 1, "symbol": symbol, "strategy": strategy, "strike": strike,
            "quantity": quantity, "expiration_date": exp}


def test_historical_var_positive_for_delta_exposure():
    pos = [_open_position()]
    ret_map = {"AAPL": _ret_series([0.01, -0.03, 0.02, -0.015, 0.025] * 60)}
    var = _historical_var(pos, {"AAPL": 100.0}, ret_map, datetime.now().date())
    assert var["oneDayVar95"] is not None and var["oneDayVar95"] > 0
    assert var["expectedShortfall"] >= var["oneDayVar95"]


def test_historical_var_no_data():
    pos = [_open_position()]
    var = _historical_var(pos, {"AAPL": 100.0}, {"AAPL": None}, datetime.now().date())
    assert var["oneDayVar95"] is None


def test_stress_test_sell_put_loses_in_crash():
    pos = [_open_position(strategy="sell_put", strike=95)]
    ret_map = {"AAPL": _ret_series([0.01, -0.02, 0.015, -0.005, 0.02] * 8)}
    out = _stress_test(pos, {"AAPL": 100.0}, ret_map, datetime.now().date())
    by_name = {o["scenario"]: o["pnl"] for o in out}
    assert by_name["2008金融危机"] < 0     # 卖 put 在暴跌中亏损
    assert by_name["强势上涨+10%"] > 0     # 上涨 + IV 回落 → 盈利


# ═══ scanner 过滤档位 ══════════════════════════════════════════════════════════

def test_filter_profiles_monotonic():
    s, r, b = FILTER_PROFILES["strict"], FILTER_PROFILES["relaxed"], FILTER_PROFILES["best_effort"]
    # 越宽松的档位门槛越低（下限）/ 越高（上限）
    assert s.dist_min > r.dist_min >= b.dist_min
    assert s.dist_max < r.dist_max <= b.dist_max
    assert s.std_min > r.std_min >= b.std_min
    assert s.pop_min > r.pop_min >= b.pop_min
    assert s.ann_min_sp > r.ann_min_sp >= b.ann_min_sp
    assert s.delta_max < r.delta_max <= b.delta_max


def test_reval_price_intrinsic_when_no_vol():
    assert _reval_price(110, 100, 30, 0, "call") == 10.0
    assert _reval_price(90, 100, 30, 0, "put") == 10.0
    assert _reval_price(100, 100, 30, 0.3, "call") > 0
