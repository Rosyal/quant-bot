"""
完整「证据包」：治理三层 + 全样本 brief + 多策略 + walk-forward 样本外章节。
"""
from __future__ import annotations

import json
import math
import time
from typing import Any

from backtest.engine import run_backtest
from backtest.walk_forward import run_walk_forward
from deliverables.executive_brief import build_brief
from deliverables.governance import governance_triad
from deliverables.wf_chapter import build_walk_forward_chapter


def json_sanitize(obj: Any) -> Any:
    """将 nan/inf 转为 None，便于 strict JSON。"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_sanitize(v) for v in obj]
    return obj


def build_product_dossier(
    candles: list[dict],
    *,
    symbol: str,
    timeframe: str,
    primary_strategy: str,
    config_overrides: dict[str, Any] | None,
    extra_strategies: list[str] | None,
    walk_forward_params: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    :param walk_forward_params: 若提供则含 train_bars, test_bars, step(optional)
    """
    extra_strategies = extra_strategies or []
    seen: set[str] = set()
    strat_list: list[str] = []
    for s in [primary_strategy] + extra_strategies:
        k = (s or "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            strat_list.append(k)

    multi_briefs: list[dict[str, Any]] = []
    prim = primary_strategy.strip().lower()
    primary_result: dict[str, Any] | None = None
    for s in strat_list:
        r = run_backtest(
            candles,
            quiet=True,
            strategy=s,
            config_overrides=config_overrides,
        )
        if s == prim:
            primary_result = r
        br = build_brief(r, symbol=symbol, timeframe=timeframe)
        multi_briefs.append({"strategy": s, "brief": br})

    wf_chapter: dict[str, Any] | None = None
    if walk_forward_params is not None:
        wf = run_walk_forward(
            candles,
            strategy=prim,
            train_bars=int(walk_forward_params["train_bars"]),
            test_bars=int(walk_forward_params["test_bars"]),
            step=walk_forward_params.get("step"),
            config_overrides=config_overrides,
        )
        wf_chapter = build_walk_forward_chapter(wf)

    full_brief = build_brief(
        primary_result or {},
        symbol=symbol,
        timeframe=timeframe,
    )

    dossier = {
        "schema": "quant_bot_product_dossier_v1",
        "generated_at_unix": int(time.time()),
        "governance_triad": governance_triad(),
        "evidence_chain": {
            "tool_layer_refs": ["backtest", "walk_forward", "paper_live", "tca", "web_dashboard"],
            "evidence_layer_refs": ["product_brief", "walk_forward_chapter", "paper_state_json"],
            "decision_layer_refs": ["human_approval", "compliance_review", "broker_api"],
        },
        "meta": {
            "symbol": symbol,
            "timeframe": timeframe,
            "primary_strategy": primary_strategy,
            "strategies_evaluated": strat_list,
            "candles": len(candles),
        },
        "full_sample_brief": full_brief,
        "multi_strategy_briefs": multi_briefs,
        "walk_forward_out_of_sample_chapter": wf_chapter,
    }
    return json_sanitize(dossier)


def dossier_to_json(dossier: dict[str, Any]) -> str:
    return json.dumps(dossier, ensure_ascii=False, indent=2)


def format_dossier_text(dossier: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("Quant Bot 产品证据包（非投资建议）")
    lines.append(f"schema: {dossier.get('schema')}  generated_at: {dossier.get('generated_at_unix')}")
    lines.append("=" * 64)

    gt = dossier.get("governance_triad") or {}
    for key in ("tool_layer", "evidence_layer", "decision_layer"):
        block = gt.get(key) or {}
        lines.append("")
        lines.append(f"【{block.get('title', key)}】")
        lines.append(f"  {block.get('summary', '')}")
        for c in block.get("capabilities") or []:
            lines.append(f"  · {c}")

    lines.append("")
    lines.append("【全样本执行摘要 — 主策略】")
    from deliverables.executive_brief import format_brief_text

    lines.append(format_brief_text(dossier.get("full_sample_brief") or {}))

    mbs = dossier.get("multi_strategy_briefs") or []
    if len(mbs) > 1:
        lines.append("")
        lines.append("【多策略批量摘要】")
        for item in mbs:
            lines.append(f"  --- 策略: {item.get('strategy')} ---")
            b = item.get("brief") or {}
            hs = b.get("historical_sample_summary") or {}
            lines.append(
                f"    return%={hs.get('total_return_pct')} sharpe={hs.get('sharpe')} "
                f"trades={hs.get('total_trades')} robust={((b.get('risk_and_limits') or {}).get('robustness_score_0_100'))}"
            )

    wf = dossier.get("walk_forward_out_of_sample_chapter")
    if wf and not wf.get("error"):
        lines.append("")
        lines.append(f"【{wf.get('chapter_title', '样本外')}】")
        agg = wf.get("aggregate") or {}
        lines.append(
            f"  folds={wf.get('folds_n')} oos_sharpe_mean={agg.get('oos_sharpe_mean')} "
            f"oos_profit_mean%={agg.get('oos_profit_pct_mean')}"
        )
        lines.append(f"  {wf.get('interpretation_hint', '')}")
        lines.append(f"  {wf.get('disclaimer', '')}")
    elif wf and wf.get("error"):
        lines.append("")
        lines.append(f"【样本外章节未生成】{wf.get('error')}")

    lines.append("")
    lines.append("=" * 64)
    return "\n".join(lines)
