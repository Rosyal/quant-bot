"""
高门槛投票组合: 更多子策略、更高 min_votes, 信号更稀疏, 回测中常提高「盈利轮占比」但降低交易次数。

不保证实盘或未来耦合测试中仍 ≥ TARGET_COUPLED_WIN_ROUND_PCT。
"""
from __future__ import annotations

from config import ENSEMBLE_STRICT_MIN_VOTES, ENSEMBLE_STRICT_COMPONENTS
from strategy.ensemble_core import generate_ensemble_signals


def generate_signals(candles: list[dict]) -> list[dict]:
    return generate_ensemble_signals(
        candles,
        ENSEMBLE_STRICT_COMPONENTS,
        ENSEMBLE_STRICT_MIN_VOTES,
        label="ensemble_strict",
    )
