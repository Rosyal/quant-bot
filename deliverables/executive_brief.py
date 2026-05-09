"""
执行摘要：把回测结果整理成「对内销售 / 对外技术说明」结构。
明确声明：不构成投资建议，不保证盈利。
"""
from __future__ import annotations

import json
from typing import Any

from deliverables.edge_diagnostics import diagnose_backtest_sample


def _safe_float(x: Any, nd: int = 2) -> str:
    try:
        v = float(x)
        if v != v:  # nan
            return "—"
        return f"{v:.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def build_brief(
    result: dict[str, Any],
    *,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    diag = diagnose_backtest_sample(result)
    m = result.get("metrics") or {}
    adv = result.get("advanced") or {}
    tca = result.get("tca") or {}

    product_capabilities = [
        "统一回测引擎：多策略、风控熔断、绩效与 TCA",
        "数字货币（ccxt）与 A 股（AkShare）行情入口",
        "纸面模拟 + Web/PWA 看板 + 可选全链路仿真（RBAC/路由/EMS）",
        "Walk-forward、耦合测试、组合搜索等验证工具（需正确解读）",
    ]

    sales_factual_only = [
        "可私有化部署，数据与审计可落本地 SQLite",
        "交付物可包含：回测报告、图表、执行摘要、CLIENT 风险披露",
        "适合作为「量化研究与流程演示」产品，而非保本理财",
    ]

    sample_summary = {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": result.get("strategy"),
        "period": f"{result.get('first_date')} ~ {result.get('last_date')}",
        "bars": result.get("candles_used"),
        "total_return_pct": _safe_float(result.get("profit_pct")),
        "final_value": _safe_float(result.get("total_value")),
        "total_trades": result.get("total_trades"),
        "win_rate_pct": _safe_float(result.get("win_rate"), 1),
        "max_drawdown_pct": _safe_float(m.get("max_drawdown_pct"), 1),
        "sharpe": _safe_float(m.get("sharpe"), 2),
        "sortino": _safe_float(m.get("sortino"), 2),
    }

    benchmark_block = {
        "buy_hold_return_pct": _safe_float(result.get("benchmark_profit_pct")),
        "alpha_vs_buy_hold_pct": _safe_float(result.get("alpha_profit_pct")),
    }

    risk_block = {
        "disclaimer": "历史与模拟不代表未来；本摘要不构成投资建议。",
        "diagnostics_tier": diag["tier"],
        "diagnostics_summary": diag["summary"],
        "flags": diag["flags"],
        "robustness_score_0_100": diag["robustness_score"],
        "kelly_hint": result.get("kelly_hint"),
        "tca_fee_bps_on_gross": _safe_float(tca.get("fee_bps_on_gross_traded"), 2),
        "info_ratio_vs_buy_hold": _safe_float(adv.get("information_ratio_vs_bh"), 2),
    }

    next_steps = [
        "python main.py product-brief --mock --walk-forward --json（证据包含样本外章节）",
        "python main.py paper-live --once 做连续纸面压力测试",
        "官网/CRM：配置 QUANT_BOT_BRIEF_API_KEY 后 GET /api/product-brief?key=…",
        "若对外销售：随交付附上 CLIENT.md，并避免「稳赚」「保本」表述",
    ]

    return {
        "document_title": "Quant Bot 执行摘要（非投资建议）",
        "product_capabilities": product_capabilities,
        "sales_factual_talking_points": sales_factual_only,
        "historical_sample_summary": sample_summary,
        "vs_buy_and_hold": benchmark_block,
        "risk_and_limits": risk_block,
        "suggested_next_steps": next_steps,
    }


def format_brief_text(brief: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append(brief["document_title"])
    lines.append("=" * 64)
    lines.append("")
    lines.append("【产品能力 — 可对外陈述的事实】")
    for x in brief["product_capabilities"]:
        lines.append(f"  · {x}")
    lines.append("")
    lines.append("【商务话术素材 — 仅事实，禁止替代合规审查】")
    for x in brief["sales_factual_talking_points"]:
        lines.append(f"  · {x}")
    lines.append("")
    lines.append("【本段历史回测样本 — 不等于未来赚钱能力】")
    hs = brief["historical_sample_summary"]
    for k, v in hs.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("【相对买入持有】")
    for k, v in brief["vs_buy_and_hold"].items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    rl = brief["risk_and_limits"]
    lines.append("【诊断与风险边界】")
    lines.append(f"  tier: {rl['diagnostics_tier']}")
    lines.append(f"  summary: {rl['diagnostics_summary']}")
    lines.append(f"  robustness_score (启发式 0–100): {rl['robustness_score_0_100']}")
    lines.append("  flags:")
    for f in rl["flags"]:
        lines.append(f"    - {f}")
    lines.append(f"  disclaimer: {rl['disclaimer']}")
    lines.append("")
    lines.append("【建议下一步】")
    for x in brief["suggested_next_steps"]:
        lines.append(f"  · {x}")
    lines.append("")
    lines.append("=" * 64)
    return "\n".join(lines)


def brief_to_json(brief: dict[str, Any]) -> str:
    return json.dumps(brief, ensure_ascii=False, indent=2)
