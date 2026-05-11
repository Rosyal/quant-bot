"""策略注册: 名称 -> generate_signals(candles)"""
from __future__ import annotations

from typing import Callable

from strategy.ma_cross import generate_signals as ma_cross_signals
from strategy.vibe import generate_signals as vibe_signals
from strategy.rsi_macd import generate_signals as rsi_macd_signals
from strategy.bb_mean_revert import generate_signals as bb_mean_revert_signals
from strategy.rsi_strategy import generate_signals as rsi_only_signals
from strategy.macd_strategy import generate_signals as macd_only_signals
from strategy.bollinger_strategy import generate_signals as bollinger_signals
from strategy.triple_ma import generate_signals as triple_ma_signals
from strategy.ema_cross import generate_signals as ema_cross_signals
from strategy.donchian import generate_signals as donchian_signals
from strategy.roc_momentum import generate_signals as roc_mom_signals
from strategy.ensemble import generate_signals as ensemble_signals
from strategy.ensemble_strict import generate_signals as ensemble_strict_signals
from strategy.stoch_cross import generate_signals as stoch_cross_signals

SignalFn = Callable[[list[dict]], list[dict]]

STRATEGY_REGISTRY: dict[str, SignalFn] = {
    "ma_cross": ma_cross_signals,
    "ema_cross": ema_cross_signals,
    "triple_ma": triple_ma_signals,
    "donchian": donchian_signals,
    "roc_mom": roc_mom_signals,
    "vibe": vibe_signals,
    "rsi_macd": rsi_macd_signals,
    "bb_mean_revert": bb_mean_revert_signals,
    "rsi": rsi_only_signals,
    "macd": macd_only_signals,
    "bollinger": bollinger_signals,
    "ensemble": ensemble_signals,
    "ensemble_strict": ensemble_strict_signals,
    "stoch_cross": stoch_cross_signals,
}

# compare / compare-matrix 默认顺序 (可按名称筛选子集)
COMPARE_STRATEGY_ORDER: tuple[str, ...] = (
    "ma_cross",
    "ema_cross",
    "triple_ma",
    "donchian",
    "roc_mom",
    "bb_mean_revert",
    "rsi_macd",
    "rsi",
    "macd",
    "bollinger",
    "vibe",
    "stoch_cross",
    "ensemble",
    "ensemble_strict",
)


def get_signal_fn(name: str) -> SignalFn:
    key = (name or "").strip().lower()
    if key not in STRATEGY_REGISTRY:
        raise ValueError(
            f"未知策略: {name!r}, 可选: {', '.join(sorted(STRATEGY_REGISTRY))}"
        )
    return STRATEGY_REGISTRY[key]
