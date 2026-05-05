"""
网格搜索 + 训练/测试切分 (降低过拟合幻觉)

在训练段选最优 Sharpe (无效则用总收益%), 再在测试段用同一组参数评估。
"""
from __future__ import annotations

import math
from itertools import product
from typing import Any

from config import MIN_CANDLES_FOR_BACKTEST
from backtest.engine import run_backtest


def _score(result: dict) -> float:
    if not result:
        return float("-1e9")
    m = result.get("metrics") or {}
    s = m.get("sharpe")
    if s is not None and isinstance(s, (int, float)) and not math.isnan(s):
        return float(s)
    return float(result.get("profit_pct", -1e9))


def run_vibe_grid_search(
    candles: list[dict],
    *,
    train_ratio: float = 0.7,
    quiet: bool = True,
) -> dict[str, Any]:
    """
    对 vibe 策略做小网格; 返回 train 最优参数、train/test 指标摘要。
    """
    n = len(candles)
    split = int(n * train_ratio)
    split = max(split, MIN_CANDLES_FOR_BACKTEST + 10)
    split = min(split, n - MIN_CANDLES_FOR_BACKTEST - 10)

    train = candles[:split]
    test = candles[split:]
    if (
        len(train) < MIN_CANDLES_FOR_BACKTEST
        or len(test) < MIN_CANDLES_FOR_BACKTEST
    ):
        return {"error": "K线过短, 无法切分训练/测试 (两段均需 >= MIN_CANDLES)"}

    grid = {
        "VIBE_RSI_BUY": [36, 38, 40],
        "VIBE_TP_PCT": [0.009, 0.011, 0.013],
        "VIBE_STOP_ATR_MULT": [3.5, 4.0],
    }
    keys = list(grid.keys())
    best: tuple[dict[str, Any], float, dict] | None = None

    for values in product(*[grid[k] for k in keys]):
        overrides = dict(zip(keys, values))
        r_tr = run_backtest(train, quiet=quiet, strategy="vibe", config_overrides=overrides)
        sc = _score(r_tr)
        if best is None or sc > best[1]:
            best = (overrides, sc, r_tr)

    assert best is not None
    best_ov, best_sc, r_train = best
    r_test = run_backtest(test, quiet=quiet, strategy="vibe", config_overrides=best_ov)

    def _m(r: dict) -> dict:
        return {
            "profit_pct": r.get("profit_pct"),
            "win_rate": r.get("win_rate"),
            "sharpe": (r.get("metrics") or {}).get("sharpe"),
            "max_dd_pct": (r.get("metrics") or {}).get("max_drawdown_pct"),
            "cagr_pct": (r.get("metrics") or {}).get("cagr_pct"),
        }

    return {
        "train_bars": len(train),
        "test_bars": len(test),
        "best_params": best_ov,
        "train_score": best_sc,
        "train_summary": _m(r_train),
        "test_summary": _m(r_test),
    }
