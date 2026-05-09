"""
投票组合搜索: 从策略池中枚举「子集 + min_votes」, 用 ensemble_core 生成信号后回测。

用于历史对比与假设生成。组合数随池子指数增长; 用 max_eval 限制计算量。
无法找到「长期保证盈利」的方案 — 样本越多越容易过拟合, 须样本外验证。
"""
from __future__ import annotations

import math
import random
from itertools import combinations
from typing import Any

from backtest.engine import run_backtest
from optimization.composite_score import composite_score_from_backtest, load_rank_weights
from strategy import STRATEGY_REGISTRY
from strategy.ensemble_core import generate_ensemble_signals

# 不参与组合底层票源 (本身是投票结果, 再嵌套语义混乱)
_EXCLUDE_FROM_POOL = frozenset({"ensemble", "ensemble_strict"})

DEFAULT_COMBO_POOL: tuple[str, ...] = (
    "ma_cross",
    "ema_cross",
    "triple_ma",
    "donchian",
    "roc_mom",
    "bb_mean_revert",
    "rsi_macd",
    "rsi",
    "macd",
    "bollinger",
    "vibe",
)


def _parse_pool(pool_csv: str | None) -> list[str]:
    if pool_csv and str(pool_csv).strip():
        names = [p.strip().lower() for p in pool_csv.split(",") if p.strip()]
    else:
        names = list(DEFAULT_COMBO_POOL)
    out: list[str] = []
    for n in names:
        if n in _EXCLUDE_FROM_POOL:
            continue
        if n not in STRATEGY_REGISTRY:
            raise ValueError(f"未知策略: {n!r}, 可选: {sorted(STRATEGY_REGISTRY)}")
        out.append(n)
    if len(out) < 2:
        raise ValueError("策略池至少需要 2 个可组合策略 (已排除 ensemble*)")
    return out


def _iter_specs(
    pool: list[str],
    min_size: int,
    max_size: int,
    min_votes_lo: int,
    min_votes_hi: int | None,
) -> list[tuple[tuple[str, ...], int]]:
    specs: list[tuple[tuple[str, ...], int]] = []
    hi = min_votes_hi if min_votes_hi is not None else max_size
    for n in range(min_size, max_size + 1):
        for combo in combinations(sorted(pool), n):
            for mv in range(max(min_votes_lo, 2), min(n, hi) + 1):
                if mv <= n:
                    specs.append((combo, mv))
    return specs


def run_combo_search(
    candles: list[dict],
    *,
    pool_csv: str | None,
    min_size: int,
    max_size: int,
    min_votes: int,
    max_votes: int | None,
    max_eval: int,
    seed: int,
    sort_by: str,
    config_overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    pool = _parse_pool(pool_csv)
    if min_size < 2:
        raise ValueError("min_size 必须 >= 2")
    if max_size < min_size:
        raise ValueError("max_size 必须 >= min_size")
    max_size = min(max_size, len(pool))

    specs = _iter_specs(pool, min_size, max_size, min_votes, max_votes)
    full_space = len(specs)
    if not specs:
        return {"rows": [], "pool": pool, "specs_in_space": 0, "specs_evaluated": 0}

    if len(specs) > max_eval:
        rng = random.Random(seed)
        specs = rng.sample(specs, max_eval)

    rows: list[dict[str, Any]] = []
    w = load_rank_weights()
    w_kwargs = {
        "w_profit": w["w_profit"],
        "w_sharpe": w["w_sharpe"],
        "w_mdd": w["w_mdd"],
        "w_winround": w["w_winround"],
    }

    for combo, mv in specs:
        label = f"v{mv}:[{','.join(combo)}]"
        try:
            sigs = generate_ensemble_signals(
                candles, combo, mv, label=f"combo:{label}"
            )
        except ValueError:
            continue
        r = run_backtest(
            candles,
            quiet=True,
            strategy=label,
            precomputed_signals=sigs,
            config_overrides=config_overrides,
        )
        if not r:
            continue
        m = r.get("metrics") or {}
        sh = m.get("sharpe", float("nan"))
        mdd = m.get("max_drawdown_pct", float("nan"))
        comp = composite_score_from_backtest(r, **w_kwargs)
        rows.append(
            {
                "label": label,
                "components": list(combo),
                "min_votes": mv,
                "profit_pct": float(r.get("profit_pct", 0)),
                "sharpe": float(sh) if sh == sh else float("nan"),
                "max_drawdown_pct": float(mdd) if mdd == mdd else float("nan"),
                "sell_count": int(r.get("sell_count", 0)),
                "composite": comp,
            }
        )

    sort_by = (sort_by or "composite").strip().lower()
    if sort_by == "profit":
        rows.sort(key=lambda x: x["profit_pct"], reverse=True)
    elif sort_by == "sharpe":
        rows.sort(
            key=lambda x: x["sharpe"] if not math.isnan(x["sharpe"]) else float("-inf"),
            reverse=True,
        )
    else:
        rows.sort(key=lambda x: x["composite"], reverse=True)

    return {
        "rows": rows,
        "pool": pool,
        "specs_in_space": full_space,
        "specs_evaluated": len(specs),
    }


def print_combo_search_report(result: dict[str, Any]) -> None:
    rows = result.get("rows") or []
    pool = result.get("pool") or []
    print("\n" + "=" * 92)
    print("  投票组合搜索 (历史回测排名, 非「最优实盘」、更不保证长期盈利)")
    print(
        f"  有效结果 {len(rows)} 条 | 池子 {len(pool)} 个策略 | "
        f"组合空间≈{result.get('specs_in_space', 0)} 取 {result.get('specs_evaluated', 0)} 组评估"
    )
    print("=" * 92)
    hdr = (
        f"  {'排名':>4} {'组合':<48} {'收益%':>10} {'Sharpe':>8} "
        f"{'回撤%':>8} {'卖出':>6} {'综合分':>8}"
    )
    print(hdr)
    print("  " + "-" * 88)
    for i, row in enumerate(rows[:40], start=1):
        sh = row["sharpe"]
        sh_s = f"{sh:>8.2f}" if not math.isnan(sh) else f"{'n/a':>8}"
        mdd = row["max_drawdown_pct"]
        mdd_s = f"{mdd:>8.2f}" if not math.isnan(mdd) else f"{'n/a':>8}"
        lab = row["label"][:46] + ".." if len(row["label"]) > 48 else row["label"]
        print(
            f"  {i:>4} {lab:<48} {row['profit_pct']:>+10.2f} "
            f"{sh_s} {mdd_s} {row['sell_count']:>6d} {row['composite']:>8.4f}"
        )
    if len(rows) > 40:
        print(f"  ... 另有 {len(rows) - 40} 条未显示")
    print("=" * 92)
    print(
        "  说明: 组合越多、筛选越细, 过拟合风险越大; 请 walk-forward / 样本外 / 小资金验证。\n"
    )


__all__ = [
    "DEFAULT_COMBO_POOL",
    "run_combo_search",
    "print_combo_search_report",
    "_parse_pool",
]
