"""期权链数据源选择：Alpaca（设置 ALPACA key 时）→ Tradier（设置 TRADIER_TOKEN 时）→ CBOE。"""
from . import alpaca, cboe, tradier


class DataSourceUnavailable(RuntimeError):
    pass


UNAVAILABLE_MSG = "期权数据源暂时不可用（所有标的都取不到期权链），请稍后再试"


def prefetch_quotes(symbols: list[str]) -> None:
    alpaca.prefetch_quotes(symbols)
    tradier.prefetch_quotes(symbols)


def fetch(symbol: str, dte_min: int, dte_max: int, max_expirations: int) -> tuple[dict | None, str | None]:
    for name, source in (("alpaca", alpaca), ("tradier", tradier)):
        data = source.fetch(symbol, dte_min, dte_max, max_expirations)
        if data:
            return data, name
    data = cboe.fetch(symbol)
    return (data, "cboe") if data else (None, None)
