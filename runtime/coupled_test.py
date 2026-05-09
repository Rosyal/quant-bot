"""
多次耦合回测: 每一「轮」内多策略共享同一批 K 线 (公平可比), 多轮后汇总分布。

- mock-seeds: 每轮独立随机行情 (不同种子), 每轮内全策略耦合。
- walk-forward: 同一条 K 线按时间切成多段, 每段内全策略耦合 (样本外/分窗压力)。
"""
from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any

from backtest.engine import run_backtest
from config import MIN_CANDLES_FOR_BACKTEST, SYMBOL, TIMEFRAME
from data_fetcher import fetch_ohlcv, generate_mock_data
from utils.logger import get_logger

logger = get_logger("coupled_test")


def split_walk_forward(
    candles: list[dict],
    runs_requested: int,
) -> tuple[list[list[dict]], int]:
    """
    将 candles 切成至多 runs_requested 段连续子序列, 每段长度 >= MIN_CANDLES_FOR_BACKTEST。
    若 K 线不足会自动减少段数。
    """
    n = len(candles)
    min_b = MIN_CANDLES_FOR_BACKTEST
    if n < min_b:
        return [], 0
    max_runs = max(1, n // min_b)
    eff = min(max(1, runs_requested), max_runs)
    chunk = n // eff
    segs: list[list[dict]] = []
    for i in range(eff):
        s = i * chunk
        e = n if i == eff - 1 else (i + 1) * chunk
        segs.append(candles[s:e])
    return segs, eff


def _collect_one_backtest(
    strategy: str,
    candles: list[dict],
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    r = run_backtest(
        candles, quiet=True, strategy=strategy, config_overrides=config_overrides
    )
    if not r:
        return None
    m = r.get("metrics") or {}
    sh = m.get("sharpe", float("nan"))
    mdd = m.get("max_drawdown_pct", float("nan"))
    return {
        "profit_pct": float(r.get("profit_pct", 0)),
        "sharpe": float(sh) if sh == sh else float("nan"),
        "max_drawdown_pct": float(mdd) if mdd == mdd else float("nan"),
        "sell_count": int(r.get("sell_count", 0)),
        "total_value": float(r.get("total_value", 0)),
    }


def run_coupled_test(
    *,
    runs: int,
    days: int,
    mode: str,
    symbol: str,
    strategies: list[str],
    seed_offset: int,
    use_mock: bool,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    :param mode: ``mock-seeds`` | ``walk-forward``
    :return: 含 rounds 元数据、每策略各轮指标列表、汇总 aggregate
    """
    mode = (mode or "mock-seeds").strip().lower().replace("_", "-")
    if mode not in ("mock-seeds", "walk-forward"):
        raise ValueError(f"未知 mode: {mode!r}, 使用 mock-seeds 或 walk-forward")

    coupled_rounds: list[list[dict]] = []
    eff_runs = 0
    detail_mode = ""

    if mode == "mock-seeds":
        if not use_mock:
            raise ValueError("mock-seeds 模式需要 --mock (每轮独立模拟行情)")
        eff_runs = max(1, runs)
        for i in range(eff_runs):
            coupled_rounds.append(
                generate_mock_data(days, seed=seed_offset + i, silent=True)
            )
        detail_mode = f"mock-seeds×{eff_runs} (种子 {seed_offset}..{seed_offset + eff_runs - 1})"
    else:
        if use_mock:
            candles = generate_mock_data(days, seed=seed_offset, silent=True)
            detail_mode = f"walk-forward(mock, seed={seed_offset})"
        else:
            candles = fetch_ohlcv(symbol, TIMEFRAME, days)
            detail_mode = f"walk-forward(真实 {symbol})"
        coupled_rounds, eff_runs = split_walk_forward(candles, runs)
        if not coupled_rounds:
            return {
                "ok": False,
                "error": f"K 线不足分段: 需要至少 {MIN_CANDLES_FOR_BACKTEST} 根",
                "mode": mode,
                "symbol": symbol,
                "strategies": strategies,
            }

    # 每策略: 每轮一条记录 (与 coupled_rounds 对齐)
    per_strategy: dict[str, list[dict[str, Any] | None]] = {
        s: [] for s in strategies
    }
    for ci, candles in enumerate(coupled_rounds):
        for st in strategies:
            per_strategy[st].append(
                _collect_one_backtest(st, candles, config_overrides)
            )
        if (ci + 1) % 50 == 0:
            logger.info(f"耦合进度: {ci + 1}/{len(coupled_rounds)} 轮")

    aggregate = _aggregate(per_strategy)
    return {
        "ok": True,
        "mode": mode,
        "detail_mode": detail_mode,
        "symbol": symbol,
        "timeframe": TIMEFRAME,
        "days": days,
        "runs_requested": runs,
        "runs_effective": len(coupled_rounds),
        "strategies": strategies,
        "per_strategy": per_strategy,
        "aggregate": aggregate,
    }


def _aggregate(
    per_strategy: dict[str, list[dict[str, Any] | None]],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for st, rows in per_strategy.items():
        valid = [x for x in rows if x is not None]
        if not valid:
            out[st] = {"n": 0}
            continue
        pps = [x["profit_pct"] for x in valid]
        sharpes = [x["sharpe"] for x in valid if not math.isnan(x["sharpe"])]
        mdds = [x["max_drawdown_pct"] for x in valid if not math.isnan(x["max_drawdown_pct"])]
        wins = sum(1 for x in pps if x > 0)
        out[st] = {
            "n": len(valid),
            "profit_pct_mean": mean(pps),
            "profit_pct_std": pstdev(pps) if len(pps) > 1 else 0.0,
            "profit_win_rate": wins / len(pps),
            "sharpe_mean": mean(sharpes) if sharpes else float("nan"),
            "sharpe_std": pstdev(sharpes) if len(sharpes) > 1 else 0.0,
            "mdd_mean": mean(mdds) if mdds else float("nan"),
            "sells_mean": mean(x["sell_count"] for x in valid),
        }
    return out


def print_coupled_report(
    result: dict[str, Any],
    *,
    sort_by: str,
    win_round_ratio_target: float | None = None,
) -> None:
    if not result.get("ok"):
        print(result.get("error", "未知错误"))
        return

    sort_by = (sort_by or "sharpe").strip().lower()
    if sort_by not in ("sharpe", "profit"):
        sort_by = "sharpe"

    agg = result["aggregate"]
    rows = []
    for st, a in agg.items():
        if a.get("n", 0) <= 0:
            continue
        key = (
            a.get("sharpe_mean", float("-inf"))
            if sort_by == "sharpe"
            else a.get("profit_pct_mean", float("-inf"))
        )
        if isinstance(key, float) and math.isnan(key):
            key = float("-inf")
        rows.append((key, st, a))
    rows.sort(key=lambda x: x[0], reverse=True)

    print("\n" + "=" * 86)
    print(
        f"  多次耦合回测  |  {result['detail_mode']}  |  "
        f"有效轮数={result['runs_effective']}  |  周期={result['timeframe']}"
    )
    print(f"  策略数={len(result['strategies'])}  |  排序: {sort_by} 均值 (高→低)")
    print("=" * 86)
    hdr = (
        f"  {'策略':<14} {'N':>4} {'收益均值%':>12} {'收益σ%':>10} "
        f"{'盈利轮%':>10} {'夏普均值':>10} {'夏普σ':>8} {'回撤均值%':>10} {'均卖出':>8}"
    )
    print(hdr)
    print("  " + "-" * 82)
    for _, st, a in rows:
        sm = a["sharpe_mean"]
        sm_s = f"{sm:>10.2f}" if not math.isnan(sm) else f"{'n/a':>10}"
        mdd_m = a["mdd_mean"]
        mdd_s = f"{mdd_m:>10.2f}" if not math.isnan(mdd_m) else f"{'n/a':>10}"
        sh_std = a["sharpe_std"]
        sh_std_s = (
            f"{sh_std:>8.2f}"
            if (not math.isnan(sm) and a.get("n", 0) > 1)
            else f"{'n/a':>8}"
        )
        print(
            f"  {st:<14} {a['n']:>4} {a['profit_pct_mean']:>+12.2f} "
            f"{a['profit_pct_std']:>10.2f} {100 * a['profit_win_rate']:>9.1f}% "
            f"{sm_s} {sh_std_s} {mdd_s} {a['sells_mean']:>8.1f}"
        )
    print("=" * 86)
    print(
        "  说明: 每轮内各策略共用同一批 K 线 (耦合); "
        "mock-seeds 为不同随机路径; walk-forward 为时间分窗。"
    )

    thr = win_round_ratio_target
    if thr is None:
        try:
            import config as cfg

            thr = float(getattr(cfg, "TARGET_COUPLED_WIN_ROUND_RATIO", 0.65))
        except (TypeError, ValueError, AttributeError):
            thr = 0.65
    evaluated = [(st, a) for st, a in agg.items() if a.get("n", 0) > 0]
    passing = [
        st
        for st, a in evaluated
        if float(a.get("profit_win_rate", 0)) >= thr
    ]
    passing.sort(key=lambda s: agg[s].get("profit_win_rate", 0), reverse=True)
    print(
        f"  对照阈值: 耦合「盈利轮占比」≥ {100 * thr:.0f}% "
        f"→ 命中 {len(passing)}/{len(evaluated)} 个策略"
    )
    print(f"    {', '.join(passing) if passing else '(无 — 需换参数/策略/路径数再测)'}")
    print(
        "  重要: 上列为历史统计, 无法保证实盘或未来仍达到该比例。\n"
    )


__all__ = [
    "split_walk_forward",
    "run_coupled_test",
    "print_coupled_report",
]
