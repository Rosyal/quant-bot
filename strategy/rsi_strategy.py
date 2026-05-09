"""纯 RSI 策略: 超卖买入 / 超买卖出 + 可选均线过滤"""
from __future__ import annotations

from utils.logger import get_logger
from config import (
    RSI_ONLY_PERIOD,
    RSI_ONLY_OVERSOLD,
    RSI_ONLY_OVERBOUGHT,
    RSI_ONLY_USE_MA,
    RSI_ONLY_MA_PERIOD,
)
from strategy.indicators import rsi, sma

logger = get_logger("strategy.rsi")


def generate_signals(candles: list[dict]) -> list[dict]:
    closes = [c["close"] for c in candles]
    rsi_vals = rsi(closes, RSI_ONLY_PERIOD)
    ma_vals = sma(closes, RSI_ONLY_MA_PERIOD) if RSI_ONLY_USE_MA else [None] * len(closes)

    out: list[dict] = []
    in_long = False

    for i, candle in enumerate(candles):
        c = candle["close"]
        r = rsi_vals[i]
        ma = ma_vals[i] if RSI_ONLY_USE_MA else None

        row = {"timestamp": candle["timestamp"], "signal": "hold", "price": c}
        if r is None:
            out.append(row)
            continue

        trend_ok = True
        if RSI_ONLY_USE_MA and ma is not None:
            trend_ok = c >= ma

        sig = "hold"
        if in_long:
            if r >= RSI_ONLY_OVERBOUGHT:
                sig = "sell"
                in_long = False
                logger.info(f"RSI 超买离场 @ {c:.4f} RSI={r:.1f}")
        else:
            if r <= RSI_ONLY_OVERSOLD and trend_ok:
                sig = "buy"
                in_long = True
                logger.info(f"RSI 超卖入场 @ {c:.4f} RSI={r:.1f}")

        out.append({**row, "signal": sig})

    return out
