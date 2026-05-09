"""
中台合规规则引擎 (可组合)。非交易所/监管规则镜像。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import config as cfg


@dataclass
class RuleContext:
    notional_usdt: float
    symbol: str
    gross_exposure_usd: float
    equity_usdt: float
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleOutcome:
    name: str
    passed: bool
    message: str


RuleFn = Callable[[RuleContext], RuleOutcome]


def rule_max_order(ctx: RuleContext) -> RuleOutcome:
    lim = float(getattr(cfg, "COMPLIANCE_MAX_ORDER_USDT", 1e12))
    ok = ctx.notional_usdt <= lim
    return RuleOutcome(
        "max_order_usdt",
        ok,
        "ok" if ok else f"单笔 {ctx.notional_usdt:.2f} > 上限 {lim:.2f}",
    )


def rule_concentration(ctx: RuleContext, max_frac: float = 0.85) -> RuleOutcome:
    """单标的名义不超过总毛敞口的比例 (无总敞口则跳过)。"""
    g = ctx.gross_exposure_usd
    if g <= 0:
        return RuleOutcome("concentration", True, "无存量敞口")
    # 假设 ctx.extra['symbol_notional'] 为当前标的存量名义
    sym_n = float(ctx.extra.get("symbol_notional_usd") or 0.0)
    frac = abs(sym_n) / g if g > 0 else 0.0
    ok = frac <= max_frac + 1e-9
    return RuleOutcome(
        "concentration",
        ok,
        f"标的占比 {frac*100:.1f}% (限 {max_frac*100:.0f}%)" if not ok else "ok",
    )


def rule_trading_hours(ctx: RuleContext) -> RuleOutcome:
    _ = ctx
    hours = getattr(cfg, "COMPLIANCE_TRADING_HOURS_UTC", None)
    if hours is None:
        return RuleOutcome("trading_hours", True, "未限制时段")
    from compliance.policies import utc_hour_now

    a, b = hours
    h = utc_hour_now()
    if a <= b:
        ok = a <= h < b
    else:
        ok = h >= a or h < b
    return RuleOutcome(
        "trading_hours",
        ok,
        "ok" if ok else f"UTC hour {h} 不在允许窗口",
    )


def default_rules() -> list[RuleFn]:
    return [rule_max_order, rule_trading_hours]


class MiddleOfficeRuleEngine:
    def __init__(self, rules: list[RuleFn] | None = None):
        self.rules = rules or default_rules()

    def evaluate(self, ctx: RuleContext) -> list[RuleOutcome]:
        return [r(ctx) for r in self.rules]

    def all_passed(self, ctx: RuleContext) -> bool:
        return all(o.passed for o in self.evaluate(ctx))
