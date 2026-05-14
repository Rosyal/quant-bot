"""
RSI 策略
"""
from strategy.base import StrategyBase, Indicators


class RSIStrategy(StrategyBase):
    name = "rsi"
    description = "RSI 超买超卖策略"
    default_params = {"period": 14, "oversold": 30, "overbought": 70}
    param_space = {"period": [7, 14, 21], "oversold": [20, 25, 30], "overbought": [70, 75, 80]}

    def on_candle(self, idx: int, candles: list[dict], extra_timeframes=None) -> str:
        period = self.get_param("period", 14)
        oversold = self.get_param("oversold", 30)
        overbought = self.get_param("overbought", 70)
        closes = [c["close"] for c in candles]
        rsi = Indicators.rsi(closes, period)

        if idx < period or rsi[idx] is None:
            return "hold"
        if rsi[idx] < oversold:
            return "buy"
        if rsi[idx] > overbought:
            return "sell"
        return "hold"
