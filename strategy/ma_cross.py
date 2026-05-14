"""
MA 交叉策略
"""
from strategy.base import StrategyBase, Indicators


class MACrossStrategy(StrategyBase):
    name = "ma_cross"
    description = "双均线交叉策略"
    default_params = {"fast": 10, "slow": 30}
    param_space = {"fast": [5, 10, 15, 20], "slow": [20, 30, 40, 60]}

    def on_candle(self, idx: int, candles: list[dict], extra_timeframes=None) -> str:
        fast = self.get_param("fast", 10)
        slow = self.get_param("slow", 30)
        closes = [c["close"] for c in candles]
        fast_ma = Indicators.sma(closes, fast)
        slow_ma = Indicators.sma(closes, slow)

        if idx < slow or fast_ma[idx] is None or slow_ma[idx] is None:
            return "hold"
        if idx < slow + 1:
            return "hold"

        prev_fast = fast_ma[idx - 1]
        prev_slow = slow_ma[idx - 1]
        if prev_fast is None or prev_slow is None:
            return "hold"

        if fast_ma[idx] > slow_ma[idx] and prev_fast <= prev_slow:
            return "buy"
        if fast_ma[idx] < slow_ma[idx] and prev_fast >= prev_slow:
            return "sell"
        return "hold"
