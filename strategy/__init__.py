"""策略注册: 名称 -> generate_signals(candles)"""
from __future__ import annotations

from typing import Callable

from strategy.ma_cross import generate_signals as ma_cross_signals
from strategy.vibe import generate_signals as vibe_signals
from strategy.rsi_macd import generate_signals as rsi_macd_signals
from strategy.bb_mean_revert import generate_signals as bb_mean_revert_signals
from strategy.ensemble import generate_signals as ensemble_signals

SignalFn = Callable[[list[dict]], list[dict]]

STRATEGY_REGISTRY: dict[str, SignalFn] = {
    "ma_cross": ma_cross_signals,
    "vibe": vibe_signals,
    "rsi_macd": rsi_macd_signals,
    "bb_mean_revert": bb_mean_revert_signals,
    "ensemble": ensemble_signals,
}


def get_signal_fn(name: str) -> SignalFn:
    key = (name or "").strip().lower()
    if key not in STRATEGY_REGISTRY:
        raise ValueError(
            f"未知策略: {name!r}, 可选: {', '.join(sorted(STRATEGY_REGISTRY))}"
        )
    return STRATEGY_REGISTRY[key]
