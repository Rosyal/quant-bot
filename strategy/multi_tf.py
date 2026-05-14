"""
多时间框架策略
"""
from strategy.base import StrategyBase, Indicators


class MultiTFStrategy(StrategyBase):
    name = "multi_tf"
    description = "多时间框架确认策略（短周期信号 + 长周期趋势过滤）"
    default_params = {"fast": 10, "slow": 30, "trend_period": 50}
    param_space = {"fast": [5, 10, 15], "slow": [20, 30, 40], "trend_period": [40, 50, 60]}

    def on_candle(self, idx: int, candles: list[dict], extra_timeframes=None) -> str:
        fast = self.get_param("fast", 10)
        slow = self.get_param("slow", 30)
        trend_period = self.get_param("trend_period", 50)
        closes = [c["close"] for c in candles]
        fast_ma = Indicators.sma(closes, fast)
        slow_ma = Indicators.sma(closes, slow)
        trend_ma = Indicators.sma(closes, trend_period)

        if idx < trend_period or any(v is None for v in [fast_ma[idx], slow_ma[idx], trend_ma[idx]]):
            return "hold"
        if idx < trend_period + 1:
            return "hold"

        prev_fast = fast_ma[idx - 1]
        prev_slow = slow_ma[idx - 1]
        if prev_fast is None or prev_slow is None:
            return "hold"

        # 金叉 + 趋势向上 → 买入
        if fast_ma[idx] > slow_ma[idx] and prev_fast <= prev_slow and closes[idx] > trend_ma[idx]:
            return "buy"
        # 死叉 + 趋势向下 → 卖出
        if fast_ma[idx] < slow_ma[idx] and prev_fast >= prev_slow and closes[idx] < trend_ma[idx]:
            return "sell"
        return "hold"
