"""唐奇安通道突破: 收盘突破前 N 根最高价做多, 跌破前 N 根最低价平仓"""
from __future__ import annotations

from utils.logger import get_logger
from config import DONCHIAN_PERIOD

logger = get_logger("strategy.donchian")


def generate_signals(candles: list[dict]) -> list[dict]:
    n = DONCHIAN_PERIOD

    out: list[dict] = []
    in_long = False

    for i, candle in enumerate(candles):
        c = candle["close"]
        row = {"timestamp": candle["timestamp"], "signal": "hold", "price": c}

        if i < n:
            out.append(row)
            continue

        window = candles[i - n : i]
        upper = max(x["high"] for x in window)
        lower = min(x["low"] for x in window)

        sig = "hold"
        if in_long:
            if c < lower:
                sig = "sell"
                in_long = False
                logger.info(f"唐奇安 跌破下轨平仓 @ {c:.4f}")
        else:
            if c > upper:
                sig = "buy"
                in_long = True
                logger.info(f"唐奇安 突破上轨入场 @ {c:.4f}")

        out.append({**row, "signal": sig})

    return out
