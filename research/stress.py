"""
权益曲线压力情景: 在「最深回撤日」之后施加一次性比例冲击 (缺口风险演示)。
"""
from __future__ import annotations


def deepest_drawdown_bar_index(equity: list[float]) -> int:
    """回撤最深时刻的 bar 索引。"""
    if not equity:
        return 0
    peak = equity[0]
    mdd = 0.0
    end_i = 0
    for i, x in enumerate(equity):
        peak = max(peak, x)
        if peak > 0:
            dd = (peak - x) / peak
            if dd > mdd:
                mdd = dd
                end_i = i
    return end_i


def apply_equity_shock_from_bar(
    equity: list[float],
    shock_pct: float,
    from_bar: int | None = None,
) -> tuple[list[float], int]:
    """
    从 from_bar 起每根权益乘以 (1+shock_pct)。from_bar 默认最深回撤点。
    """
    if not equity:
        return [], 0
    bar = deepest_drawdown_bar_index(equity) if from_bar is None else max(0, min(from_bar, len(equity) - 1))
    mult = 1.0 + shock_pct
    out = list(equity[:bar])
    out.extend(equity[i] * mult for i in range(bar, len(equity)))
    return out, bar
