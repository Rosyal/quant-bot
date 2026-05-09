"""风格因子截面得分 (动量、低波、短期反转) — 可与 risk_model 联用"""
from __future__ import annotations

import numpy as np

from factors.cross_section import cross_section_zscores, momentum_raw, realized_vol


def style_momentum_z(close_panel: dict[str, np.ndarray], lookback: int = 20) -> dict[str, float]:
    raw = {s: momentum_raw(c, lookback) for s, c in close_panel.items()}
    return cross_section_zscores(raw)


def style_low_vol_z(close_panel: dict[str, np.ndarray], window: int = 20) -> dict[str, float]:
    """低波动因子: 波动率截面 z 后取反 (高 z = 低波优选)"""
    raw = {s: realized_vol(c, window) for s, c in close_panel.items()}
    z = cross_section_zscores(raw)
    return {s: -v for s, v in z.items()}


def style_short_reversal_z(close_panel: dict[str, np.ndarray], lb: int = 5) -> dict[str, float]:
    """短反转: 短窗动量 z 后取反"""
    mom = {s: momentum_raw(c, lb) for s, c in close_panel.items()}
    z = cross_section_zscores(mom)
    return {s: -v for s, v in z.items()}
