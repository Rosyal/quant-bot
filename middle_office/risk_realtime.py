"""
实时风控规则 (并入中台 RuleContext / desk 全链路).

非交易所/监管镜像; 上线前须与业务确认阈值与字段来源 (OMS/风控台推送 equity、回撤等)。
"""
from __future__ import annotations

from typing import Callable

import config as cfg
from middle_office.rules import RuleContext, RuleOutcome, RuleFn


def rule_leverage_after_order(ctx: RuleContext) -> RuleOutcome:
    """
    下单后毛敞口 / 权益 上限 (买方向近似加上本笔名义)。
    """
    max_lev = float(getattr(cfg, "RISK_MAX_LEVERAGE_GROSS_TO_EQUITY", 0.0) or 0.0)
    if max_lev <= 0:
        return RuleOutcome("leverage_cap", True, "未启用")
    eq = float(ctx.equity_usdt or 0.0)
    if eq <= 0:
        return RuleOutcome("leverage_cap", False, "权益无效, 拒绝")
    gross = float(ctx.gross_exposure_usd or 0.0)
    add = float(ctx.notional_usdt or 0.0)
    projected = gross + max(0.0, add)
    lev = projected / eq
    ok = lev <= max_lev + 1e-9
    return RuleOutcome(
        "leverage_cap",
        ok,
        f"杠杆口径≈毛敞口+本笔/权益={lev:.2f} (限 {max_lev:.2f})" if not ok else "ok",
    )


def rule_drawdown_block(ctx: RuleContext) -> RuleOutcome:
    """若 extra 提供 current_drawdown_pct (0~1), 超过阈值则拦截新开风险。"""
    thr = getattr(cfg, "RISK_BLOCK_NEW_BUY_IF_DRAWDOWN_PCT", None)
    if thr is None:
        return RuleOutcome("drawdown_block", True, "未配置阈值")
    try:
        thr_f = float(thr)
    except (TypeError, ValueError):
        return RuleOutcome("drawdown_block", True, "阈值无效")
    raw = ctx.extra.get("current_drawdown_pct")
    if raw is None:
        return RuleOutcome("drawdown_block", True, "无回撤数据, 跳过")
    dd = float(raw)
    ok = dd <= thr_f + 1e-9
    return RuleOutcome(
        "drawdown_block",
        ok,
        f"当前回撤 {dd*100:.1f}% > 限 {thr_f*100:.1f}%" if not ok else "ok",
    )


def rule_daily_loss_block(ctx: RuleContext) -> RuleOutcome:
    """若 extra 提供 daily_loss_pct (负数表示亏损), 低于阈值则拦截。"""
    thr = getattr(cfg, "RISK_DAILY_LOSS_LIMIT_PCT", None)
    if thr is None:
        return RuleOutcome("daily_loss", True, "未配置单日亏损线")
    try:
        thr_f = float(thr)
    except (TypeError, ValueError):
        return RuleOutcome("daily_loss", True, "阈值无效")
    raw = ctx.extra.get("daily_loss_pct")
    if raw is None:
        return RuleOutcome("daily_loss", True, "无日损益数据, 跳过")
    loss = float(raw)
    ok = loss >= -abs(thr_f) - 1e-9
    return RuleOutcome(
        "daily_loss",
        ok,
        f"当日亏损 {-loss*100:.2f}% 超过限额 {abs(thr_f)*100:.2f}%" if not ok else "ok",
    )


def realtime_risk_rules() -> list[RuleFn]:
    if not bool(getattr(cfg, "RISK_REALTIME_RULES_ENABLED", False)):
        return []
    out: list[Callable[[RuleContext], RuleOutcome]] = [
        rule_leverage_after_order,
        rule_drawdown_block,
        rule_daily_loss_block,
    ]
    return out  # type: ignore[return-value]


def evaluate_realtime_risk(ctx: RuleContext) -> list[RuleOutcome]:
    return [r(ctx) for r in realtime_risk_rules()]
