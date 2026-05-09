"""
多资产组合优化 (研究用)

- 风险平价 (迭代解)
- 长端最小方差 (解析 + 投影到非负)

需历史收益样本估计协方差; 样本短则估计噪声大。非投资建议。
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def returns_from_closes(closes: np.ndarray) -> np.ndarray:
    """closes: (T, N) 价格矩阵 → (T-1, N) 简单收益率"""
    if closes.ndim != 2 or closes.shape[0] < 3:
        raise ValueError("closes 须为 (T,N) 且 T>=3")
    r = closes[1:] / closes[:-1] - 1.0
    return np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)


def _cov_shrinkage(r: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf 简化: 对角收缩 toward identity scale"""
    t, n = r.shape
    if t < n + 1:
        return np.cov(r, rowvar=False) + np.eye(n) * 1e-8
    s = np.cov(r, rowvar=False)
    mu = np.trace(s) / n
    target = np.eye(n) * mu
    shrink = min(1.0, (n / t) ** 0.5 * 0.25)
    return (1.0 - shrink) * s + shrink * target + np.eye(n) * 1e-10


def risk_parity_weights(
    cov: np.ndarray,
    *,
    max_iter: int = 80,
    tol: float = 1e-10,
) -> np.ndarray:
    """风险平价权重, 和为 1, 全为正。"""
    n = cov.shape[0]
    w = np.ones(n) / n
    for _ in range(max_iter):
        mrc = cov @ w
        rc = w * mrc
        avg = np.sum(rc) / n
        w_new = w * avg / (rc + 1e-15)
        w_new = np.maximum(w_new, 0.0)
        s = w_new.sum()
        if s <= 0:
            break
        w_new /= s
        if np.max(np.abs(w_new - w)) < tol:
            return w_new
        w = w_new
    return w


def long_only_min_variance(cov: np.ndarray) -> np.ndarray:
    """
    最小方差组合解析解 w ∝ Σ^{-1}1, 再投影到单纯形 (非负归一)。
    """
    n = cov.shape[0]
    try:
        inv = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        inv = np.linalg.pinv(cov)
    raw = inv @ np.ones(n)
    raw = np.maximum(raw, 0.0)
    s = raw.sum()
    if s < 1e-15:
        return np.ones(n) / n
    w = raw / s
    var = float(w @ cov @ w)
    if math.isnan(var) or var < 0:
        return np.ones(n) / n
    return w


def optimize_from_price_panel(
    closes_matrix: np.ndarray,
    *,
    method: str = "riskparity",
) -> tuple[np.ndarray, np.ndarray]:
    """
    :param closes_matrix: (T, N)
    :param method: riskparity | minvar
    :return: (weights N,), cov_used (N,N)
    """
    r = returns_from_closes(closes_matrix)
    cov = _cov_shrinkage(r)
    m = method.strip().lower()
    if m == "riskparity":
        w = risk_parity_weights(cov)
    elif m in ("minvar", "min_variance", "mvp"):
        w = long_only_min_variance(cov)
    else:
        raise ValueError("method 须为 riskparity 或 minvar")
    return w, cov
