"""
双均线交叉策略 (MA Cross)
经典趋势跟踪策略:
- 快线上穿慢线 → 买入信号 (金叉)
- 快线下穿慢线 → 卖出信号 (死叉)
"""
from __future__ import annotations

from utils.logger import get_logger
from config import FAST_PERIOD, SLOW_PERIOD

logger = get_logger("strategy")


def calculate_ma(closes: list[float], period: int) -> list[float | None]:
    """计算移动平均线"""
    result: list[float | None] = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
        else:
            ma = sum(closes[i - period + 1 : i + 1]) / period
            result.append(ma)
    return result


def generate_signals(candles: list[dict]) -> list[dict]:
    """
    生成交易信号
    :param candles: K线数据列表, 每个元素包含 close, timestamp
    :return: 信号列表, 每个元素包含 timestamp, signal (buy/sell/hold), price
    """
    closes = [c["close"] for c in candles]
    fast_ma = calculate_ma(closes, FAST_PERIOD)
    slow_ma = calculate_ma(closes, SLOW_PERIOD)

    signals = []
    prev_fast = None
    prev_slow = None

    for i, candle in enumerate(candles):
        f = fast_ma[i]
        s = slow_ma[i]

        if f is None or s is None:
            signals.append({
                "timestamp": candle["timestamp"],
                "signal": "hold",
                "price": candle["close"],
                "fast_ma": None,
                "slow_ma": None,
            })
            continue

        signal = "hold"

        # 金叉: 快线从下方穿越慢线
        if prev_fast is not None and prev_slow is not None:
            if prev_fast <= prev_slow and f > s:
                signal = "buy"
                logger.info(
                    f"金叉信号 @ {candle['close']:.2f} "
                    f"(MA{FAST_PERIOD}={f:.2f} > MA{SLOW_PERIOD}={s:.2f})"
                )
            # 死叉: 快线从上方穿越慢线
            elif prev_fast >= prev_slow and f < s:
                signal = "sell"
                logger.info(
                    f"死叉信号 @ {candle['close']:.2f} "
                    f"(MA{FAST_PERIOD}={f:.2f} < MA{SLOW_PERIOD}={s:.2f})"
                )

        signals.append({
            "timestamp": candle["timestamp"],
            "signal": signal,
            "price": candle["close"],
            "fast_ma": round(f, 2),
            "slow_ma": round(s, 2),
        })

        prev_fast = f
        prev_slow = s

    return signals
