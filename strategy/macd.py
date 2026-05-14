"""
MACD 策略
"""
from strategy.base import StrategyBase, Indicators


class MACDStrategy(StrategyBase):
    name = "macd"
    description = "MACD 金叉死叉策略"
    default_params = {"fast": 12, "slow": 26, "signal": 9}
    param_space = {"fast": [8, 12, 16], "slow": [20, 26, 32], "signal": [7, 9, 12]}

    def on_candle(self, idx: int, candles: list[dict], extra_timeframes=None) -> str:
        fast = self.get_param("fast", 12)
        slow = self.get_param("slow", 26)
        signal = self.get_param("signal", 9)
        closes = [c["close"] for c in candles]
        macd_line, signal_line, histogram = Indicators.macd(closes, fast, slow, signal)

        if idx < slow + signal:
            return "hold"
        m = macd_line[idx]
        s = signal_line[idx]
        pm = macd_line[idx - 1]
        ps = signal_line[idx - 1]

        if any(v is None for v in [m, s, pm, ps]):
            return "hold"
        if m > s and pm <= ps:
            return "buy"
        if m < s and pm >= ps:
            return "sell"
        return "hold"
