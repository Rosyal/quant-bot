"""
布林带均值回归 (简版)

下轨 + RSI 超卖入场; 回到中轨或 ATR 止损离场。
与账户级风控、策略内止损并行。
"""
from __future__ import annotations

from utils.logger import get_logger
from config import (
    BBMR_BB_PERIOD,
    BBMR_BB_STD,
    BBMR_RSI_PERIOD,
    BBMR_RSI_BUY,
    BBMR_RSI_SELL,
    BBMR_LOWER_SLACK,
    BBMR_ATR_PERIOD,
    BBMR_STOP_ATR_MULT,
    BBMR_MIN_EXIT_GAIN,
    BBMR_TP_PCT,
)
from strategy.indicators import bollinger_bands, rsi, atr

logger = get_logger("strategy.bb_mean_revert")


def generate_signals(candles: list[dict]) -> list[dict]:
    closes = [c["close"] for c in candles]
    mid, upper, lower = bollinger_bands(closes, BBMR_BB_PERIOD, BBMR_BB_STD)
    rsi_vals = rsi(closes, BBMR_RSI_PERIOD)
    atr_vals = atr(candles, BBMR_ATR_PERIOD)

    out: list[dict] = []
    in_long = False
    entry_price = 0.0

    for i, candle in enumerate(candles):
        c = candle["close"]
        mbb, lo = mid[i], lower[i]
        r = rsi_vals[i]
        at = atr_vals[i]

        row = {"timestamp": candle["timestamp"], "signal": "hold", "price": c}

        if mbb is None or lo is None or r is None or at is None or at <= 0:
            out.append(row)
            continue

        sig = "hold"
        if in_long:
            stop = entry_price - BBMR_STOP_ATR_MULT * at
            gain_ok = c >= entry_price * (1.0 + BBMR_MIN_EXIT_GAIN)
            hit_tp = c >= entry_price * (1.0 + BBMR_TP_PCT)
            if c <= stop:
                sig = "sell"
                in_long = False
                logger.info(f"BBMR 止损 @ {c:.2f}")
            elif hit_tp or (c >= mbb and gain_ok) or (r >= BBMR_RSI_SELL and gain_ok):
                sig = "sell"
                in_long = False
                logger.info(f"BBMR 离场 @ {c:.2f} RSI={r:.1f}")
        else:
            touch = c <= lo * BBMR_LOWER_SLACK
            if r <= BBMR_RSI_BUY and touch:
                sig = "buy"
                in_long = True
                entry_price = c
                logger.info(f"BBMR 入场 @ {c:.2f} RSI={r:.1f}")

        out.append({**row, "signal": sig})

    return out
