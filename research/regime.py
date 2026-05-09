"""
波动率 regime (无 HMM): 用滚动标准差相对全样本分位划分高/低波动。

用于分段统计或特征标注, 非预测工具。
"""
from __future__ import annotations

from typing import Any

import numpy as np


def rolling_vol_series(closes: np.ndarray, window: int) -> np.ndarray:
    """与 closes 等长; 前 window+1 根为 nan。"""
    n = len(closes)
    out = np.full(n, np.nan)
    if n <= window + 1:
        return out
    r = closes[1:] / closes[:-1] - 1.0
    for i in range(window, len(r)):
        seg = r[i - window : i]
        out[i + 1] = float(np.std(seg, ddof=1))
    return out


def high_vol_mask(
    closes: list[float] | np.ndarray,
    *,
    window: int = 20,
    quantile: float = 0.7,
) -> tuple[np.ndarray, np.ndarray]:
    """
    :return: (vol 与收盘价对齐), (是否为高波动, 与 vol 同索引)
    """
    c = np.asarray(closes, dtype=float)
    vol = rolling_vol_series(c, window)
    valid = np.isfinite(vol)
    high = np.zeros_like(vol, dtype=bool)
    if not np.any(valid):
        return vol, high
    thresh = float(np.quantile(vol[valid], quantile))
    high = valid & (vol >= thresh)
    return vol, high


def regime_summary(closes: list[float] | np.ndarray, **kwargs: Any) -> dict[str, float]:
    vol, high = high_vol_mask(closes, **kwargs)
    valid = np.isfinite(vol)
    n_valid = int(np.sum(valid))
    n_high = int(np.sum(high & valid))
    pct = 100.0 * n_high / n_valid if n_valid else 0.0
    return {
        "bars_labeled": float(n_valid),
        "high_vol_bars": float(n_high),
        "high_vol_pct": pct,
    }
