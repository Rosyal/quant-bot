"""
多策略投票组合

对若干子策略的 signal 按 bar 对齐; 至少 ENSEMBLE_MIN_VOTES 个同时看多/看空才输出。
卖出优先于买入 (同一根 K 线冲突时风控取向)。
"""
from __future__ import annotations

from utils.logger import get_logger
from config import ENSEMBLE_MIN_VOTES, ENSEMBLE_COMPONENTS
from strategy.ma_cross import generate_signals as sig_ma_cross
from strategy.bb_mean_revert import generate_signals as sig_bb_mean_revert
from strategy.rsi_macd import generate_signals as sig_rsi_macd
from strategy.vibe import generate_signals as sig_vibe

logger = get_logger("strategy.ensemble")

_SIGNAL_REGISTRY: dict[str, object] = {
    "ma_cross": sig_ma_cross,
    "bb_mean_revert": sig_bb_mean_revert,
    "rsi_macd": sig_rsi_macd,
    "vibe": sig_vibe,
}


def generate_signals(candles: list[dict]) -> list[dict]:
    if not candles:
        return []

    names = [n.strip().lower() for n in ENSEMBLE_COMPONENTS if n.strip()]
    if len(names) < ENSEMBLE_MIN_VOTES:
        logger.warning(
            f"子策略数 {len(names)} < 最少票数 {ENSEMBLE_MIN_VOTES}, 组合可能永不交易"
        )

    fns = []
    for n in names:
        if n not in _SIGNAL_REGISTRY:
            raise ValueError(f"ensemble 未知子策略: {n!r}, 可选: {sorted(_SIGNAL_REGISTRY)}")
        fns.append(_SIGNAL_REGISTRY[n])
    sub_signals = [fn(candles) for fn in fns]
    n = len(candles)
    out: list[dict] = []

    for i in range(n):
        buys = sum(1 for s in sub_signals if s[i].get("signal") == "buy")
        sells = sum(1 for s in sub_signals if s[i].get("signal") == "sell")
        price = candles[i]["close"]
        sig = "hold"
        if sells >= ENSEMBLE_MIN_VOTES:
            sig = "sell"
        elif buys >= ENSEMBLE_MIN_VOTES:
            sig = "buy"
        out.append({"timestamp": candles[i]["timestamp"], "signal": sig, "price": price})

    return out
