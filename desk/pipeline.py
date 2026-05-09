"""
全链路执行编排 (纸面/演练)

顺序: RBAC → 中台规则 → 大额审批 → ExecutionRouter(合规+冲击+审计) → OMS/EMS(通道+latency_ns) → 汇总审计

与头部 OMS 的差距: 实盘需接交易所私有回报与托管机房; 本仓库已提供 **模拟多档撮合+逐笔成交**、**净头寸落库与清算快照**、**延迟画像 (colo/retail/cross_region)**，并把各段**串成单入口**便于替换。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import config as cfg
from compliance.audit_service import log_audit_event
from db.database import Database
from middle_office.rules import MiddleOfficeRuleEngine, RuleContext
from oms.ems import make_default_ems, new_client_order_id
from oms.types import OrderRequest, OrderSide, OrderType
from routing.execution_router import ExecutionRouter, RouteResult
from security.permissions import A_ROUTE, PermissionDenied, assert_can


@dataclass
class PipelineContext:
    symbol: str
    side: str  # buy | sell
    notional_usdt: float
    mid: float
    actor: str = "desk"
    role: str = "trader"
    force: bool = False
    approval_id: int | None = None
    gross_exposure_usd: float = 0.0
    equity_usdt: float = 0.0
    symbol_notional_usd: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    ok: bool
    stages: list[dict[str, Any]]
    router: RouteResult | None = None
    ems: Any = None
    message: str = ""


def run_order_pipeline(
    ctx: PipelineContext,
    db: Database | None,
    *,
    run_ems: bool = True,
    log_summary_audit: bool = True,
) -> PipelineResult:
    """
    执行完整链路。db 为 None 时跳过审批校验与审计落库 (仅控制台演练)。
    """
    stages: list[dict[str, Any]] = []

    try:
        assert_can(ctx.role, A_ROUTE)
        stages.append({"stage": "rbac", "ok": True})
    except PermissionDenied as e:
        return PipelineResult(
            False,
            stages + [{"stage": "rbac", "ok": False, "msg": str(e)}],
            message=str(e),
        )

    eng = MiddleOfficeRuleEngine()
    rctx = RuleContext(
        notional_usdt=ctx.notional_usdt,
        symbol=ctx.symbol,
        gross_exposure_usd=ctx.gross_exposure_usd,
        equity_usdt=ctx.equity_usdt,
        extra={"symbol_notional_usd": ctx.symbol_notional_usd},
    )
    for o in eng.evaluate(rctx):
        stages.append(
            {
                "stage": "middle_office",
                "rule": o.name,
                "ok": o.passed,
                "msg": o.message,
            }
        )
        if not o.passed:
            return PipelineResult(False, stages, message=o.message)

    thr = float(getattr(cfg, "APPROVAL_REQUIRED_ABOVE_USDT", 1e18))
    if ctx.notional_usdt > thr and not ctx.force:
        if db is None:
            return PipelineResult(
                False,
                stages
                + [{"stage": "approval", "ok": False, "msg": "无 DB 无法校验审批"}],
                message="大额需审批且需数据库",
            )
        if ctx.approval_id is None:
            return PipelineResult(
                False,
                stages + [{"stage": "approval", "ok": False, "msg": "缺少 approval_id"}],
                message=f"名义>{thr} 需先 approval-submit 与 resolve, 或 --force",
            )
        row = db.get_approval_request(ctx.approval_id)
        if not row or (row.get("status") or "").lower() != "approved":
            return PipelineResult(
                False,
                stages + [{"stage": "approval", "ok": False, "msg": "未批准"}],
                message="审批未通过或不存在",
            )
        stages.append({"stage": "approval", "ok": True, "id": ctx.approval_id})
    else:
        stages.append({"stage": "approval", "ok": True, "skipped": True})

    router = ExecutionRouter(db=db, role=ctx.role)
    rr = router.dry_run_market_order(
        symbol=ctx.symbol,
        side=ctx.side,
        notional_usdt=ctx.notional_usdt,
        mid=ctx.mid,
        actor=ctx.actor,
    )
    stages.append(
        {
            "stage": "execution_router",
            "ok": rr.ok,
            "reason": rr.reason,
            "effective_price": rr.effective_price,
            "latency_ms": rr.latency_ms,
        }
    )
    if not rr.ok:
        return PipelineResult(False, stages, router=rr, message=rr.reason)

    er = None
    if run_ems:
        order = OrderRequest(
            client_order_id=new_client_order_id("pipe"),
            symbol=ctx.symbol,
            side=OrderSide.BUY if ctx.side == "buy" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            notional_usdt=ctx.notional_usdt,
            account_id=str(ctx.meta.get("account_id", "MAIN")),
        )
        ems = make_default_ems(ctx.mid, db)
        er = ems.submit(order)
        stages.append(
            {
                "stage": "ems",
                "ok": er.status in ("filled", "partial"),
                "channel": er.channel,
                "avg_px": er.avg_px,
                "latency_ns": er.latency_ns,
                "legs": len(er.exec_legs),
                "modelled_exchange_latency_ns": (er.detail or {}).get(
                    "modelled_exchange_latency_ns"
                ),
            }
        )
        if er.status not in ("filled", "partial"):
            msg = (er.detail or {}).get("reason", "ems rejected")
            return PipelineResult(False, stages, router=rr, ems=er, message=msg)

    if log_summary_audit and db is not None:
        log_audit_event(
            db,
            actor=ctx.actor,
            action="full_chain_execution",
            resource=ctx.symbol,
            payload={
                "stages": stages,
                "side": ctx.side,
                "notional_usdt": ctx.notional_usdt,
            },
            outcome="ok",
            latency_ms=None,
        )

    return PipelineResult(True, stages, router=rr, ems=er, message="ok")


def pipeline_stages_to_text(stages: list[dict[str, Any]]) -> str:
    lines = []
    for s in stages:
        name = s.get("stage", "?")
        extra = {k: v for k, v in s.items() if k != "stage"}
        lines.append(f"  [{name}] {json.dumps(extra, ensure_ascii=False)}")
    return "\n".join(lines)
