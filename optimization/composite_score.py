"""
综合评分 (仅用于历史/耦合测试结果排序, 不保证未来收益)

默认加权: 收益、夏普、回撤(越低越好)、盈利轮占比。
权重可在 config.RANK_COMPOSITE_W_* 调整。
"""
from __future__ import annotations

import math
from typing import Any


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def composite_score_row(
    agg: dict[str, Any],
    *,
    w_profit: float,
    w_sharpe: float,
    w_mdd: float,
    w_winround: float,
) -> float:
    """
    :param agg: coupled_test 的 aggregate 单策略条目, 或单轮兼容字段
    """
    if agg.get("n", 0) <= 0:
        return float("-inf")

    pm = float(agg.get("profit_pct_mean", 0))
    sm = float(agg.get("sharpe_mean", float("nan")))
    mdd = float(agg.get("mdd_mean", float("nan")))
    wr = float(agg.get("profit_win_rate", 0))

    # 归一化到约 [0,1]
    p_norm = (_clamp(pm, -50.0, 50.0) + 50.0) / 100.0
    if math.isnan(sm):
        s_norm = 0.25
    else:
        s_norm = (_clamp(sm, -2.0, 4.0) + 2.0) / 6.0
    if math.isnan(mdd):
        mdd_norm = 0.0
    else:
        mdd_norm = 1.0 - _clamp(mdd, 0.0, 50.0) / 50.0
    wr_norm = _clamp(wr, 0.0, 1.0)

    return (
        w_profit * p_norm
        + w_sharpe * s_norm
        + w_mdd * mdd_norm
        + w_winround * wr_norm
    )


def composite_score_from_backtest(result: dict[str, Any], **weights: float) -> float:
    """单次回测结果 → 与 aggregate 同形评分。"""
    m = result.get("metrics") or {}
    sh = m.get("sharpe", float("nan"))
    mdd = m.get("max_drawdown_pct", float("nan"))
    pm = float(result.get("profit_pct", 0))
    wr = 1.0 if pm > 0 else 0.0
    agg = {
        "n": 1,
        "profit_pct_mean": pm,
        "sharpe_mean": float(sh) if sh == sh else float("nan"),
        "mdd_mean": float(mdd) if mdd == mdd else float("nan"),
        "profit_win_rate": wr,
    }
    return composite_score_row(agg, **weights)


def load_rank_weights() -> dict[str, float]:
    import config as cfg

    return {
        "w_profit": float(getattr(cfg, "RANK_COMPOSITE_W_PROFIT", 0.35)),
        "w_sharpe": float(getattr(cfg, "RANK_COMPOSITE_W_SHARPE", 0.30)),
        "w_mdd": float(getattr(cfg, "RANK_COMPOSITE_W_MDD", 0.25)),
        "w_winround": float(getattr(cfg, "RANK_COMPOSITE_W_WINROUND", 0.10)),
    }
