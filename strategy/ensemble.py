"""
多策略投票组合 (默认配置见 ENSEMBLE_COMPONENTS / ENSEMBLE_MIN_VOTES)
"""
from __future__ import annotations

from config import ENSEMBLE_MIN_VOTES, ENSEMBLE_COMPONENTS
from strategy.ensemble_core import generate_ensemble_signals


def generate_signals(candles: list[dict]) -> list[dict]:
    return generate_ensemble_signals(
        candles,
        ENSEMBLE_COMPONENTS,
        ENSEMBLE_MIN_VOTES,
        label="ensemble",
    )
