"""
多策略投票核心: 子策略 signal 按 bar 对齐, 卖出优先于买入。
"""
from __future__ import annotations

from typing import Iterable

from utils.logger import get_logger
from strategy.ma_cross import generate_signals as sig_ma_cross
from strategy.bb_mean_revert import generate_signals as sig_bb_mean_revert
from strategy.rsi_macd import generate_signals as sig_rsi_macd
from strategy.vibe import generate_signals as sig_vibe
from strategy.rsi_strategy import generate_signals as sig_rsi
from strategy.macd_strategy import generate_signals as sig_macd
from strategy.bollinger_strategy import generate_signals as sig_bollinger
from strategy.triple_ma import generate_signals as sig_triple_ma
from strategy.ema_cross import generate_signals as sig_ema_cross
from strategy.donchian import generate_signals as sig_donchian
from strategy.roc_momentum import generate_signals as sig_roc_mom

logger = get_logger("strategy.ensemble_core")

SIGNAL_REGISTRY: dict[str, object] = {
    "ma_cross": sig_ma_cross,
    "ema_cross": sig_ema_cross,
    "triple_ma": sig_triple_ma,
    "donchian": sig_donchian,
    "roc_mom": sig_roc_mom,
    "bb_mean_revert": sig_bb_mean_revert,
    "rsi_macd": sig_rsi_macd,
    "vibe": sig_vibe,
    "rsi": sig_rsi,
    "macd": sig_macd,
    "bollinger": sig_bollinger,
}


def generate_ensemble_signals(
    candles: list[dict],
    component_names: Iterable[str],
    min_votes: int,
    *,
    label: str = "ensemble",
) -> list[dict]:
    if not candles:
        return []

    names = [n.strip().lower() for n in component_names if n and str(n).strip()]
    if len(names) < min_votes:
        logger.warning(
            f"[{label}] 子策略数 {len(names)} < 最少票数 {min_votes}, 组合可能极少交易"
        )

    fns = []
    for n in names:
        if n not in SIGNAL_REGISTRY:
            raise ValueError(
                f"[{label}] 未知子策略: {n!r}, 可选: {sorted(SIGNAL_REGISTRY)}"
            )
        fns.append(SIGNAL_REGISTRY[n])
    sub_signals = [fn(candles) for fn in fns]
    n_bars = len(candles)
    out: list[dict] = []

    for i in range(n_bars):
        buys = sum(1 for s in sub_signals if s[i].get("signal") == "buy")
        sells = sum(1 for s in sub_signals if s[i].get("signal") == "sell")
        price = candles[i]["close"]
        sig = "hold"
        if sells >= min_votes:
            sig = "sell"
        elif buys >= min_votes:
            sig = "buy"
        out.append({"timestamp": candles[i]["timestamp"], "signal": sig, "price": price})

    return out


__all__ = ["SIGNAL_REGISTRY", "generate_ensemble_signals"]
