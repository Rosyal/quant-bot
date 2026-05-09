"""
Kelly / 分数 Kelly (二元结果近似)

需稳定 win_rate 与平均盈亏比; 样本小则严重失真。非仓位建议, 仅研究参考。
"""
from __future__ import annotations

import math


def fractional_kelly_two_outcome(
    win_rate: float,
    avg_win: float,
    avg_loss_abs: float,
    *,
    fraction: float = 0.5,
    cap: float = 0.25,
) -> float:
    """
    Kelly ≈ W - (1-W)/R, R = avg_win/avg_loss; 返回 fraction*Kelly 并 cap。
    """
    if not (0 < win_rate < 1) or avg_loss_abs <= 1e-12 or avg_win < 0:
        return float("nan")
    r_ratio = avg_win / avg_loss_abs
    if r_ratio <= 0:
        return float("nan")
    kelly = win_rate - (1.0 - win_rate) / r_ratio
    k = max(0.0, kelly) * fraction
    return min(k, cap) if not math.isnan(k) else float("nan")


def kelly_from_sell_trades(
    sell_profits: list[float],
    *,
    fraction: float = 0.5,
    cap: float = 0.25,
) -> dict[str, float]:
    wins = [p for p in sell_profits if p > 0]
    losses = [p for p in sell_profits if p < 0]
    if not wins or not losses:
        return {"kelly_fraction": float("nan"), "n_trades": float(len(sell_profits))}
    w = len(wins) / len(sell_profits)
    aw = sum(wins) / len(wins)
    al = abs(sum(losses) / len(losses))
    k = fractional_kelly_two_outcome(w, aw, al, fraction=fraction, cap=cap)
    return {
        "kelly_fraction": k,
        "n_trades": float(len(sell_profits)),
        "win_rate": w * 100.0,
    }
