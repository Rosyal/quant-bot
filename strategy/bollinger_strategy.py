"""纯布林带策略: 下轨附近做多 / 上轨或中轨止盈"""
from __future__ import annotations

from utils.logger import get_logger
from config import (
    BB_ONLY_PERIOD,
    BB_ONLY_STD,
    BB_ONLY_LOWER_SLACK,
    BB_ONLY_TP_TOUCH_UPPER,
    BB_ONLY_ATR_PERIOD,
    BB_ONLY_STOP_MULT,
)
from strategy.indicators import bollinger_bands, atr

logger = get_logger("strategy.bollinger")


def generate_signals(candles: list[dict]) -> list[dict]:
    closes = [c["close"] for c in candles]
    mid, upper, lower = bollinger_bands(closes, BB_ONLY_PERIOD, BB_ONLY_STD)
    atr_vals = atr(candles, BB_ONLY_ATR_PERIOD)

    out: list[dict] = []
    in_long = False
    entry = 0.0

    for i, candle in enumerate(candles):
        c = candle["close"]
        mbb, up, lo = mid[i], upper[i], lower[i]
        at = atr_vals[i]
        row = {"timestamp": candle["timestamp"], "signal": "hold", "price": c}

        if mbb is None or up is None or lo is None or at is None or at <= 0:
            out.append(row)
            continue

        sig = "hold"
        if in_long:
            stop = entry - BB_ONLY_STOP_MULT * at
            if c <= stop:
                sig = "sell"
                in_long = False
                logger.info(f"布林 ATR 止损 @ {c:.4f}")
            elif BB_ONLY_TP_TOUCH_UPPER and c >= up * 0.998:
                sig = "sell"
                in_long = False
                logger.info(f"布林 触碰上轨止盈 @ {c:.4f}")
            elif c >= mbb:
                sig = "sell"
                in_long = False
                logger.info(f"布林 回归中轨平仓 @ {c:.4f}")
        else:
            if c <= lo * BB_ONLY_LOWER_SLACK:
                sig = "buy"
                in_long = True
                entry = c
                logger.info(f"布林 下轨入场 @ {c:.4f}")

        out.append({**row, "signal": sig})

    return out
