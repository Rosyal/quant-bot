"""
回测/耦合用风险预设 (临时覆盖 config)。

「stability」: 低仓位、紧回撤、仍走完整策略逻辑 —— 只降低风险暴露与杠杆感,
不能也不代表「保证盈利」或「一直赚钱」。无风险收益请考虑现金管理类工具。
"""
from __future__ import annotations

from copy import copy
from typing import Any

# 与 backtest.engine._config_overrides 配合: 键须为 config 模块已有属性
STABILITY_PROFILE_OVERRIDES: dict[str, Any] = {
    "TRADE_AMOUNT_PCT": 0.10,
    "RSIMACD_TRADE_AMOUNT_PCT": 0.12,
    "RISK_MAX_POSITION_PCT": 0.20,
    "RISK_MAX_DRAWDOWN_PCT": 0.08,
    "RISK_FORCE_FLAT_ON_DRAWDOWN": True,
    "RISK_ENABLED": True,
}

PROFILE_DEFAULT_STRATEGY: dict[str, str] = {
    # 未指定 --strategy 时, stability 默认用高门槛投票 (信号更稀疏)
    "stability": "ensemble_strict",
}

_PROFILES: dict[str, dict[str, Any]] = {
    "stability": STABILITY_PROFILE_OVERRIDES,
}


def get_profile_overrides(profile_name: str | None) -> dict[str, Any] | None:
    if not profile_name or not str(profile_name).strip():
        return None
    key = str(profile_name).strip().lower()
    if key in ("none", "default", "off"):
        return None
    if key not in _PROFILES:
        raise ValueError(
            f"未知预设: {profile_name!r}, 可选: {', '.join(sorted(_PROFILES))}"
        )
    return copy(_PROFILES[key])


def default_strategy_for_profile(profile_name: str | None) -> str | None:
    if not profile_name or not str(profile_name).strip():
        return None
    key = str(profile_name).strip().lower()
    return PROFILE_DEFAULT_STRATEGY.get(key)


__all__ = [
    "STABILITY_PROFILE_OVERRIDES",
    "PROFILE_DEFAULT_STRATEGY",
    "get_profile_overrides",
    "default_strategy_for_profile",
]
