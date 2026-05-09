"""
滚动样本外验证 (Walk-forward): 多段训练窗 + 测试窗, 观察参数固定时策略跨区间稳定性。

与单次回测相比, 更接近实务中的「分段样本外」评估; 不保证未来表现。
"""
from __future__ import annotations

import math
import statistics
from typing import Any

from config import MIN_CANDLES_FOR_BACKTEST
from backtest.engine import run_backtest


def _summarize_segment(r: dict) -> dict[str, Any]:
    if not r:
        return {
            "profit_pct": float("nan"),
            "sharpe": float("nan"),
            "max_dd_pct": float("nan"),
            "trades": 0,
        }
    m = r.get("metrics") or {}
    return {
        "profit_pct": r.get("profit_pct"),
        "sharpe": m.get("sharpe"),
        "max_dd_pct": m.get("max_drawdown_pct"),
        "trades": r.get("total_trades", 0),
    }


def run_walk_forward(
    candles: list[dict],
    *,
    strategy: str | None,
    train_bars: int,
    test_bars: int,
    step: int | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    从数据起点开始, 每窗: [train][test], 然后窗口整体右移 step 根 K 线。

    :param step: 默认等于 test_bars (测试段不重叠)
    """
    step = int(test_bars if step is None else step)
    if step < 1:
        return {"error": "step 须 >= 1"}
    train_bars = int(train_bars)
    test_bars = int(test_bars)
    if train_bars < MIN_CANDLES_FOR_BACKTEST or test_bars < MIN_CANDLES_FOR_BACKTEST:
        return {
            "error": f"train_bars/test_bars 均需 >= {MIN_CANDLES_FOR_BACKTEST}",
        }

    n = len(candles)
    folds: list[dict[str, Any]] = []
    i = 0
    fold_idx = 0
    while i + train_bars + test_bars <= n:
        train = candles[i : i + train_bars]
        test = candles[i + train_bars : i + train_bars + test_bars]
        r_in = run_backtest(
            train,
            quiet=True,
            strategy=strategy,
            config_overrides=config_overrides,
        )
        r_out = run_backtest(
            test,
            quiet=True,
            strategy=strategy,
            config_overrides=config_overrides,
        )
        folds.append(
            {
                "fold": fold_idx,
                "train_start_idx": i,
                "train_end_idx": i + train_bars - 1,
                "test_start_idx": i + train_bars,
                "test_end_idx": i + train_bars + test_bars - 1,
                "in_sample": _summarize_segment(r_in),
                "out_of_sample": _summarize_segment(r_out),
            }
        )
        fold_idx += 1
        i += step

    if not folds:
        return {
            "error": "K 线不足以构成至少一段 walk-forward, 请缩短 train/test 或增加数据",
            "folds": [],
        }

    def _finite(xs: list[float]) -> list[float]:
        return [x for x in xs if x is not None and isinstance(x, (int, float)) and not math.isnan(x)]

    oos_sharpe = _finite(
        [f["out_of_sample"]["sharpe"] for f in folds if f["out_of_sample"]]
    )
    oos_profit = _finite(
        [float(f["out_of_sample"]["profit_pct"]) for f in folds]
    )

    agg: dict[str, Any] = {
        "folds_n": len(folds),
        "oos_sharpe_mean": statistics.mean(oos_sharpe) if oos_sharpe else float("nan"),
        "oos_sharpe_stdev": statistics.stdev(oos_sharpe) if len(oos_sharpe) > 1 else float("nan"),
        "oos_profit_pct_mean": statistics.mean(oos_profit) if oos_profit else float("nan"),
    }
    return {"folds": folds, "aggregate": agg, "train_bars": train_bars, "test_bars": test_bars, "step": step}


def format_walk_forward_report(wf: dict[str, Any]) -> str:
    if wf.get("error"):
        return f"Walk-forward 失败: {wf['error']}"
    st = wf["aggregate"]["oos_sharpe_stdev"]
    st_s = f"{st:.4f}" if isinstance(st, (int, float)) and not math.isnan(st) else "n/a"
    lines = [
        "",
        "=" * 60,
        "  Walk-forward 摘要 (固定参数, 多样本外段)",
        "=" * 60,
        f"  段数: {wf['aggregate']['folds_n']}  train={wf['train_bars']}  test={wf['test_bars']}  step={wf['step']}",
        f"  样本外 Sharpe 均值: {wf['aggregate']['oos_sharpe_mean']:.4f}",
        f"  样本外 Sharpe 标准差: {st_s}",
        f"  样本外收益%% 均值: {wf['aggregate']['oos_profit_pct_mean']:.2f}",
        "-" * 60,
    ]
    for f in wf["folds"]:
        o = f["out_of_sample"]
        sp = o.get("sharpe")
        sp_s = f"{sp:.3f}" if sp is not None and isinstance(sp, (int, float)) and not math.isnan(sp) else "n/a"
        lines.append(
            f"  折{f['fold']}: OOS 收益 {o.get('profit_pct', 0):+.2f}%  "
            f"Sharpe {sp_s}  回撤 {o.get('max_dd_pct', 0):.2f}%  成交 {o.get('trades', 0)}"
        )
    lines.append("=" * 60)
    lines.append("  (历史分段结果不代表未来; 非投资建议)")
    lines.append("")
    return "\n".join(lines)
