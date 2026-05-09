"""
将 walk_forward 结果整理为「样本外章节」结构（供 dossier / CRM）。
"""
from __future__ import annotations

import math
from typing import Any


def _num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def build_walk_forward_chapter(wf: dict[str, Any]) -> dict[str, Any]:
    """可 JSON 序列化的样本外章节；错误时返回 error 字段。"""
    if not wf:
        return {"error": "empty_walk_forward"}
    if wf.get("error"):
        return {
            "error": wf["error"],
            "disclaimer": "历史分段结果不代表未来；非投资建议。",
        }

    agg = wf.get("aggregate") or {}
    folds_out: list[dict[str, Any]] = []
    for f in wf.get("folds") or []:
        o = f.get("out_of_sample") or {}
        folds_out.append(
            {
                "fold": f.get("fold"),
                "test_bar_range": [f.get("test_start_idx"), f.get("test_end_idx")],
                "oos_profit_pct": _num(o.get("profit_pct")),
                "oos_sharpe": _num(o.get("sharpe")),
                "oos_max_drawdown_pct": _num(o.get("max_dd_pct")),
                "oos_trades": o.get("trades"),
            }
        )

    return {
        "chapter_title": "样本外章节（Walk-forward 汇总）",
        "train_bars": wf.get("train_bars"),
        "test_bars": wf.get("test_bars"),
        "step": wf.get("step"),
        "folds_n": agg.get("folds_n"),
        "aggregate": {
            "oos_sharpe_mean": _num(agg.get("oos_sharpe_mean")),
            "oos_sharpe_stdev": _num(agg.get("oos_sharpe_stdev")),
            "oos_profit_pct_mean": _num(agg.get("oos_profit_pct_mean")),
        },
        "folds_out_of_sample": folds_out,
        "interpretation_hint": (
            "关注样本外夏普均值与分段稳定性；标准差过大表示跨期不稳定，需谨慎对外表述。"
        ),
        "disclaimer": "历史分段结果不代表未来；非投资建议。",
    }
