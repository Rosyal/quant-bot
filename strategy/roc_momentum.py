"""ROC 动量: N 期涨跌幅超过阈值做多, 跌穿负阈值或动量转弱平仓"""
from __future__ import annotations

from utils.logger import get_logger
from config import ROC_MOM_PERIOD, ROC_MOM_BUY, ROC_MOM_SELL

logger = get_logger("strategy.roc_mom")


def generate_signals(candles: list[dict]) -> list[dict]:
    n = ROC_MOM_PERIOD
    closes = [c["close"] for c in candles]

    out: list[dict] = []
    in_long = False

    for i, candle in enumerate(candles):
        c = candle["close"]
        row = {"timestamp": candle["timestamp"], "signal": "hold", "price": c}
        if i < n:
            out.append(row)
            continue

        base = closes[i - n]
        if base <= 0:
            out.append(row)
            continue
        roc = (c - base) / base

        sig = "hold"
        if in_long:
            if roc <= ROC_MOM_SELL:
                sig = "sell"
                in_long = False
                logger.info(f"ROC 动量离场 @ {c:.4f} roc={roc:.4f}")
        else:
            if roc >= ROC_MOM_BUY:
                sig = "buy"
                in_long = True
                logger.info(f"ROC 动量入场 @ {c:.4f} roc={roc:.4f}")

        out.append({**row, "signal": sig})

    return out
