"""
布林带策略
"""
from strategy.base import StrategyBase, Indicators


class BollingerStrategy(StrategyBase):
    name = "bollinger"
    description = "布林带突破策略"
    default_params = {"period": 20, "std_dev": 2.0}
    param_space = {"period": [10, 20, 30], "std_dev": [1.5, 2.0, 2.5]}

    def on_candle(self, idx: int, candles: list[dict], extra_timeframes=None) -> str:
        period = self.get_param("period", 20)
        std_dev = self.get_param("std_dev", 2.0)
        closes = [c["close"] for c in candles]
        upper, middle, lower = Indicators.bollinger(closes, period, std_dev)

        if idx < period or upper[idx] is None:
            return "hold"
        price = closes[idx]
        if price <= lower[idx]:
            return "buy"
        if price >= upper[idx]:
            return "sell"
        return "hold"
