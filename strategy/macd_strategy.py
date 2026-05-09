"""纯 MACD 策略: 金叉买入 / 死叉卖出"""
from __future__ import annotations

from utils.logger import get_logger
from config import MACD_ONLY_FAST, MACD_ONLY_SLOW, MACD_ONLY_SIGNAL
from strategy.indicators import macd

logger = get_logger("strategy.macd")


def generate_signals(candles: list[dict]) -> list[dict]:
    closes = [c["close"] for c in candles]
    m_line, s_line, _hist = macd(closes, MACD_ONLY_FAST, MACD_ONLY_SLOW, MACD_ONLY_SIGNAL)

    out: list[dict] = []
    in_long = False
    prev_m = prev_s = None

    for i, candle in enumerate(candles):
        c = candle["close"]
        m = m_line[i]
        s = s_line[i]
        row = {"timestamp": candle["timestamp"], "signal": "hold", "price": c}

        if m is None or s is None:
            out.append(row)
            prev_m, prev_s = m, s
            continue

        golden = prev_m is not None and prev_s is not None and prev_m <= prev_s and m > s
        death = prev_m is not None and prev_s is not None and prev_m >= prev_s and m < s

        sig = "hold"
        if in_long:
            if death:
                sig = "sell"
                in_long = False
                logger.info(f"MACD 死叉平仓 @ {c:.4f}")
        else:
            if golden:
                sig = "buy"
                in_long = True
                logger.info(f"MACD 金叉开仓 @ {c:.4f}")

        out.append({**row, "signal": sig})
        prev_m, prev_s = m, s

    return out
