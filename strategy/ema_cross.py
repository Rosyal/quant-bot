"""双 EMA 金叉/死叉 (与 ma_cross 逻辑相同, 用指数均线)"""
from __future__ import annotations

from utils.logger import get_logger
from config import EMA_CROSS_FAST, EMA_CROSS_SLOW
from strategy.indicators import ema

logger = get_logger("strategy.ema_cross")


def generate_signals(candles: list[dict]) -> list[dict]:
    closes = [c["close"] for c in candles]
    fast_e = ema(closes, EMA_CROSS_FAST)
    slow_e = ema(closes, EMA_CROSS_SLOW)

    out: list[dict] = []
    prev_f = prev_s = None

    for i, candle in enumerate(candles):
        c = candle["close"]
        f, s = fast_e[i], slow_e[i]
        row = {"timestamp": candle["timestamp"], "signal": "hold", "price": c}
        if f is None or s is None:
            out.append(row)
            prev_f, prev_s = f, s
            continue

        sig = "hold"
        if prev_f is not None and prev_s is not None:
            if prev_f <= prev_s and f > s:
                sig = "buy"
                logger.info(f"EMA 金叉 @ {c:.4f}")
            elif prev_f >= prev_s and f < s:
                sig = "sell"
                logger.info(f"EMA 死叉 @ {c:.4f}")

        out.append({**row, "signal": sig})
        prev_f, prev_s = f, s

    return out
