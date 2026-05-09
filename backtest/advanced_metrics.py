"""
相对基准的扩展绩效与回撤形态 (市面回测平台常见补充项)
"""
from __future__ import annotations

import math
from typing import Sequence

from backtest.metrics import _simple_returns


def max_drawdown_episode_length_bars(equity: list[float]) -> int:
    """处于「低于历史峰值」状态的最长连续 K 线根数 (近似回撤期长度)。"""
    if not equity:
        return 0
    peak = equity[0]
    run = 0
    best = 0
    for x in equity:
        peak = max(peak, x)
        if peak > 0 and x < peak - 1e-12 * peak:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def pct_bars_below_prior_peak(equity: list[float]) -> float:
    """低于前序峰值的 K 线占比 (%)。"""
    if not equity:
        return 0.0
    peak = equity[0]
    n = 0
    for x in equity:
        peak = max(peak, x)
        if peak > 0 and x < peak - 1e-12 * peak:
            n += 1
    return 100.0 * n / len(equity)


def max_consecutive_losing_trades(sell_profits: Sequence[float]) -> int:
    """按平仓顺序统计最大连续亏损笔数 (profit<=0)。"""
    best = cur = 0
    for p in sell_profits:
        if p <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def information_ratio_vs_benchmark(
    strategy_equity: list[float],
    benchmark_equity: list[float],
    periods_per_year: float,
) -> float:
    """
    相对基准超额收益的信息比率 (年化): mean(active_ret) / std(active_ret) * sqrt(ppy)
    """
    if (
        len(strategy_equity) != len(benchmark_equity)
        or len(strategy_equity) < 4
    ):
        return float("nan")
    rs = _simple_returns(strategy_equity)
    rb = _simple_returns(benchmark_equity)
    n = min(len(rs), len(rb))
    if n < 3:
        return float("nan")
    active = [rs[-n + i] - rb[-n + i] for i in range(n)]
    mu = sum(active) / n
    var = sum((x - mu) ** 2 for x in active) / (n - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd < 1e-15:
        return float("nan")
    return (mu / sd) * math.sqrt(periods_per_year)


def compute_advanced_metrics(
    equity: list[float],
    *,
    benchmark_equity: list[float] | None,
    sell_trade_profits: list[float],
    periods_per_year: float,
) -> dict[str, float]:
    out: dict[str, float] = {
        "max_drawdown_duration_bars": float(max_drawdown_episode_length_bars(equity)),
        "pct_bars_under_peak": pct_bars_below_prior_peak(equity),
        "max_consecutive_losses": float(max_consecutive_losing_trades(sell_trade_profits)),
    }
    if benchmark_equity and len(benchmark_equity) == len(equity):
        out["information_ratio_vs_bh"] = information_ratio_vs_benchmark(
            equity, benchmark_equity, periods_per_year
        )
    else:
        out["information_ratio_vs_bh"] = float("nan")
    return out
