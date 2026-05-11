"""
随机指标金叉/死叉 + 超买超卖过滤（演示策略）。
"""
from __future__ import annotations

from strategy.indicators import stochastic

from utils.logger import get_logger

logger = get_logger("strategy")


def generate_signals(candles: list[dict]) -> list[dict]:
    if len(candles) < 30:
        logger.warning("K 线过少, stoch_cross 可能无有效信号")
    pct_k, pct_d = stochastic(candles, k_period=14, slowing=3, d_period=3)
    signals: list[dict] = []
    prev_k = None
    prev_d = None
    for i, c in enumerate(candles):
        k, d = pct_k[i], pct_d[i]
        price = float(c["close"])
        sig = "hold"
        if (
            prev_k is not None
            and prev_d is not None
            and k is not None
            and d is not None
        ):
            # 超卖区金叉买入
            if prev_k <= prev_d and k > d and k < 25:
                sig = "buy"
            # 超买区死叉卖出
            elif prev_k >= prev_d and k < d and k > 75:
                sig = "sell"
        signals.append(
            {"timestamp": c["timestamp"], "signal": sig, "price": price}
        )
        if k is not None and d is not None:
            prev_k, prev_d = k, d
    return signals
