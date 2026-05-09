"""三均线排列: 快>中>慢 做多, 快下穿中或排列破坏则平仓"""
from __future__ import annotations

from utils.logger import get_logger
from config import TRIPLE_MA_FAST, TRIPLE_MA_MID, TRIPLE_MA_SLOW
from strategy.indicators import sma

logger = get_logger("strategy.triple_ma")


def generate_signals(candles: list[dict]) -> list[dict]:
    closes = [c["close"] for c in candles]
    fv = sma(closes, TRIPLE_MA_FAST)
    mv = sma(closes, TRIPLE_MA_MID)
    sv = sma(closes, TRIPLE_MA_SLOW)

    out: list[dict] = []
    in_long = False
    prev_align = False

    for i, candle in enumerate(candles):
        c = candle["close"]
        f, m, s = fv[i], mv[i], sv[i]
        row = {"timestamp": candle["timestamp"], "signal": "hold", "price": c}
        if f is None or m is None or s is None:
            out.append(row)
            continue

        align = f > m > s
        sig = "hold"
        if in_long:
            if f < m or not (f > m > s):
                sig = "sell"
                in_long = False
                logger.info(f"三均线 离场 @ {c:.4f}")
        else:
            if align and not prev_align:
                sig = "buy"
                in_long = True
                logger.info(f"三均线 多头排列入场 @ {c:.4f}")

        out.append({**row, "signal": sig})
        prev_align = align

    return out
