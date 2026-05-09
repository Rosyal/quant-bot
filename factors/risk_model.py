"""
Barra / 多因子风险 — 极简版: 因子协方差 + 载荷矩阵 → 资产协方差 + 组合波动。

真 Barra 需行业归属、因子收益序列、特异风险估计; 此处为教学用线性代数壳。
"""
from __future__ import annotations

import numpy as np


def barra_lite_asset_covariance(
    loadings: np.ndarray,
    factor_cov: np.ndarray,
    idio_variance: np.ndarray,
) -> np.ndarray:
    """
    Σ = B F B' + diag(D)

    :param loadings: (n_assets, n_factors)
    :param factor_cov: (n_factors, n_factors)
    :param idio_variance: (n_assets,) 特异方差
    """
    b = np.asarray(loadings, dtype=float)
    f = np.asarray(factor_cov, dtype=float)
    d = np.asarray(idio_variance, dtype=float).flatten()
    n = b.shape[0]
    if d.shape[0] != n:
        raise ValueError("idio_variance 长度须等于资产数")
    return b @ f @ b.T + np.diag(d)


def portfolio_volatility(w: np.ndarray, cov: np.ndarray) -> float:
    w = np.asarray(w, dtype=float).flatten()
    return float(np.sqrt(max(w @ cov @ w, 0.0)))


def single_market_factor_assumption(
    betas: np.ndarray,
    market_var: float,
    idio_var: np.ndarray,
) -> np.ndarray:
    """单市场因子: B 为列向量 beta, F = [[market_var]]。"""
    b = np.asarray(betas, dtype=float).reshape(-1, 1)
    f = np.array([[market_var]], dtype=float)
    return barra_lite_asset_covariance(b, f, idio_var)
