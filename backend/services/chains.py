"""期权链数据源选择：Tradier（设置 TRADIER_TOKEN 时）→ CBOE。"""
from . import cboe, tradier


class DataSourceUnavailable(RuntimeError):
    pass


UNAVAILABLE_MSG = "期权数据源暂时不可用（所有标的都取不到期权链），请稍后再试"


def fetch(symbol: str, dte_min: int, dte_max: int, max_expirations: int) -> tuple[dict | None, str | None]:
    data = tradier.fetch(symbol, dte_min, dte_max, max_expirations)
    if data:
        return data, "tradier"
    data = cboe.fetch(symbol)
    return (data, "cboe") if data else (None, None)
