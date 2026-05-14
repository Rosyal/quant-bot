"""
策略基类 + 技术指标
"""
from utils.logger import get_logger

logger = get_logger("strategy.base")


class Indicators:
    """技术指标计算"""

    @staticmethod
    def sma(data: list[float], period: int) -> list[float | None]:
        """简单移动平均"""
        result = [None] * (period - 1)
        for i in range(period - 1, len(data)):
            result.append(sum(data[i - period + 1:i + 1]) / period)
        return result

    @staticmethod
    def ema(data: list[float], period: int) -> list[float | None]:
        """指数移动平均"""
        if len(data) < period:
            return [None] * len(data)
        k = 2 / (period + 1)
        result = [None] * (period - 1)
        ema_val = sum(data[:period]) / period
        result.append(ema_val)
        for i in range(period, len(data)):
            ema_val = data[i] * k + ema_val * (1 - k)
            result.append(ema_val)
        return result

    @staticmethod
    def rsi(data: list[float], period: int = 14) -> list[float | None]:
        """RSI"""
        if len(data) < period + 1:
            return [None] * len(data)
        result = [None] * period
        gains, losses = [], []
        for i in range(1, period + 1):
            diff = data[i] - data[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - 100 / (1 + rs))
        for i in range(period + 1, len(data)):
            diff = data[i] - data[i - 1]
            avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
            avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
            if avg_loss == 0:
                result.append(100.0)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - 100 / (1 + rs))
        return result

    @staticmethod
    def macd(data: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
        """MACD (macd_line, signal_line, histogram)"""
        ema_fast = Indicators.ema(data, fast)
        ema_slow = Indicators.ema(data, slow)
        macd_line = []
        for i in range(len(data)):
            f = ema_fast[i] if i < len(ema_fast) and ema_fast[i] is not None else None
            s = ema_slow[i] if i < len(ema_slow) and ema_slow[i] is not None else None
            if f is not None and s is not None:
                macd_line.append(f - s)
            else:
                macd_line.append(None)
        # signal line
        valid_macd = [v for v in macd_line if v is not None]
        signal_line_vals = Indicators.ema(valid_macd, signal)
        signal_line = [None] * (len(data) - len(signal_line_vals))
        signal_line.extend(signal_line_vals)
        # histogram
        histogram = []
        for i in range(len(data)):
            m = macd_line[i]
            s = signal_line[i] if i < len(signal_line) else None
            if m is not None and s is not None:
                histogram.append(m - s)
            else:
                histogram.append(None)
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger(data: list[float], period: int = 20, std_dev: float = 2.0) -> tuple:
        """布林带 (upper, middle, lower)"""
        middle = Indicators.sma(data, period)
        upper, lower = [], []
        for i in range(len(data)):
            if middle[i] is None:
                upper.append(None)
                lower.append(None)
            else:
                window = data[i - period + 1:i + 1]
                std = (sum((x - middle[i]) ** 2 for x in window) / period) ** 0.5
                upper.append(middle[i] + std_dev * std)
                lower.append(middle[i] - std_dev * std)
        return upper, middle, lower


class StrategyBase:
    """策略基类"""

    name = "base"
    description = ""
    default_params = {}
    param_space = {}

    def __init__(self, **params):
        self._params = {**self.default_params, **params}

    def get_param(self, key: str, default=None):
        return self._params.get(key, default)

    def generate_signals(self, candles: list[dict]) -> list[dict]:
        signals = []
        closes = [c["close"] for c in candles]
        for i in range(len(candles)):
            sig = self.on_candle(i, candles)
            signals.append({
                "timestamp": candles[i]["timestamp"],
                "signal": sig,
                "price": candles[i]["close"],
            })
        return signals

    def on_candle(self, idx: int, candles: list[dict], extra_timeframes=None) -> str:
        raise NotImplementedError
