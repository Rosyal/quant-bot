"""
全链路执行编排 (纸面/演练)

顺序: RBAC → OMS 幂等/落库 → 中台规则+实时风控 → 大额审批 → ExecutionRouter → EMS → 汇总审计

与头部 OMS 的差距: 实盘需接交易所私有回报与托管机房; 本仓库已提供 **模拟多档撮合+逐笔成交**、**净头寸落库与清算快照**、**延迟画像 (colo/retail/cross_region)**、**OMS 订单表幂等**、**实时风控扩展规则**，并把各段**串成单入口**便于替换。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import config as cfg
from compliance.audit_service import log_audit_event
from compliance.workflow import approval_row_usable_for_order
from middle_office.risk_realtime import evaluate_realtime_risk
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
    client_order_id: str | None = None


def run_order_pipeline(
    ctx: PipelineContext,
    db: Database | None,
    *,
    run_ems: bool = True,
    log_summary_audit: bool = True,
) -> PipelineResult:
    """
    执行完整链路。db 为 None 时跳过审批校验、OMS 落库与审计落库 (仅控制台演练)。
    """
    stages: list[dict[str, Any]] = []
    oms_enabled = bool(getattr(cfg, "OMS_IDEMPOTENCY_ENABLED", True))
    coid = str((ctx.meta or {}).get("client_order_id") or "").strip() or new_client_order_id(
        "desk"
    )
    order_row_created = False

    try:
        assert_can(ctx.role, A_ROUTE)
        stages.append({"stage": "rbac", "ok": True})
    except PermissionDenied as e:
        return PipelineResult(
            False,
            stages + [{"stage": "rbac", "ok": False, "msg": str(e)}],
            message=str(e),
            client_order_id=coid,
        )

    if db is not None and oms_enabled:
        ex = db.oms_get_order_by_client_id(coid)
        if ex:
            st = (ex.get("status") or "").lower()
            if st in ("filled", "partial_filled"):
                stages.append(
                    {
                        "stage": "oms_idempotent",
                        "ok": True,
                        "client_order_id": coid,
                        "msg": "已成交, 幂等返回",
                    }
                )
                return PipelineResult(
                    True,
                    stages,
                    message="idempotent: order already filled",
                    client_order_id=coid,
                )
            if st in ("new", "routing", "ems_submitted"):
                return PipelineResult(
                    False,
                    stages
                    + [
                        {
                            "stage": "oms_duplicate",
                            "ok": False,
                            "client_order_id": coid,
                            "msg": "同 client_order_id 处理中, 禁止重复提交",
                        }
                    ],
                    message="duplicate client_order_id inflight",
                    client_order_id=coid,
                )
            if st == "rejected":
                return PipelineResult(
                    False,
                    stages
                    + [
                        {
                            "stage": "oms_reuse",
                            "ok": False,
                            "client_order_id": coid,
                            "msg": "该 client_order_id 曾失败, 请更换新号",
                        }
                    ],
                    message="stale client_order_id rejected",
                    client_order_id=coid,
                )
        try:
            db.oms_create_order(
                client_order_id=coid,
                account_id=str((ctx.meta or {}).get("account_id", "MAIN")),
                symbol=ctx.symbol,
                side=ctx.side,
                notional_usdt=ctx.notional_usdt,
                status="new",
                payload_json=json.dumps({"actor": ctx.actor}, ensure_ascii=False),
            )
            order_row_created = True
        except Exception as e:  # noqa: BLE001
            return PipelineResult(
                False,
                stages
                + [{"stage": "oms_create", "ok": False, "msg": str(e)}],
                message=str(e),
                client_order_id=coid,
            )
        stages.append({"stage": "oms_create", "ok": True, "client_order_id": coid})

    extra: dict[str, Any] = {"symbol_notional_usd": ctx.symbol_notional_usd}
    for k, v in (ctx.meta or {}).items():
        if k not in ("account_id", "client_order_id") and k not in extra:
            extra[k] = v

    eng = MiddleOfficeRuleEngine()
    rctx = RuleContext(
        notional_usdt=ctx.notional_usdt,
        symbol=ctx.symbol,
        gross_exposure_usd=ctx.gross_exposure_usd,
        equity_usdt=ctx.equity_usdt,
        extra=extra,
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
            if db is not None and oms_enabled and order_row_created:
                db.oms_update_order(coid, status="rejected", last_error=o.message)
            return PipelineResult(
                False, stages, message=o.message, client_order_id=coid
            )

    for o in evaluate_realtime_risk(rctx):
        stages.append(
            {
                "stage": "risk_realtime",
                "rule": o.name,
                "ok": o.passed,
                "msg": o.message,
            }
        )
        if not o.passed:
            if db is not None and oms_enabled and order_row_created:
                db.oms_update_order(coid, status="rejected", last_error=o.message)
            return PipelineResult(
                False, stages, message=o.message, client_order_id=coid
            )

    thr = float(getattr(cfg, "APPROVAL_REQUIRED_ABOVE_USDT", 1e18))
    if ctx.notional_usdt > thr and not ctx.force:
        if db is None:
            return PipelineResult(
                False,
                stages
                + [{"stage": "approval", "ok": False, "msg": "无 DB 无法校验审批"}],
                message="大额需审批且需数据库",
                client_order_id=coid,
            )
        if ctx.approval_id is None:
            if db is not None and oms_enabled and order_row_created:
                db.oms_update_order(coid, status="rejected", last_error="缺少审批")
            return PipelineResult(
                False,
                stages + [{"stage": "approval", "ok": False, "msg": "缺少 approval_id"}],
                message=f"名义>{thr} 需先 approval-submit 与 resolve, 或 --force",
                client_order_id=coid,
            )
        row = db.get_approval_request(ctx.approval_id)
        ok_ap, ap_msg = approval_row_usable_for_order(row)
        if not ok_ap:
            if db is not None and oms_enabled and order_row_created:
                db.oms_update_order(coid, status="rejected", last_error=ap_msg)
            return PipelineResult(
                False,
                stages
                + [{"stage": "approval", "ok": False, "msg": ap_msg}],
                message=ap_msg,
                client_order_id=coid,
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
        if db is not None and oms_enabled and order_row_created:
            db.oms_update_order(coid, status="rejected", last_error=rr.reason)
        return PipelineResult(
            False, stages, router=rr, message=rr.reason, client_order_id=coid
        )

    if db is not None and oms_enabled and order_row_created:
        db.oms_update_order(coid, status="routing")

    er = None
    if run_ems:
        if db is not None and oms_enabled and order_row_created:
            db.oms_update_order(coid, status="ems_submitted")
        order = OrderRequest(
            client_order_id=coid,
            symbol=ctx.symbol,
            side=OrderSide.BUY if ctx.side == "buy" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            notional_usdt=ctx.notional_usdt,
            account_id=str((ctx.meta or {}).get("account_id", "MAIN")),
        )
        ems = make_default_ems(ctx.mid, db)
        er = ems.submit(order)
        oms_st = "filled" if er.status == "filled" else (
            "partial_filled" if er.status == "partial" else "rejected"
        )
        if db is not None and oms_enabled and order_row_created:
            if oms_st == "rejected":
                db.oms_update_order(
                    coid,
                    status="rejected",
                    last_error=str((er.detail or {}).get("reason", "ems")),
                )
            else:
                db.oms_update_order(coid, status=oms_st)
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
            return PipelineResult(
                False, stages, router=rr, ems=er, message=msg, client_order_id=coid
            )
    elif db is not None and oms_enabled and order_row_created:
        db.oms_update_order(coid, status="cancelled", last_error="no_ems")

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
                "client_order_id": coid,
            },
            outcome="ok",
            latency_ms=None,
        )

    return PipelineResult(
        True, stages, router=rr, ems=er, message="ok", client_order_id=coid
    )


def pipeline_stages_to_text(stages: list[dict[str, Any]]) -> str:
    lines = []
    for s in stages:
        name = s.get("stage", "?")
        extra = {k: v for k, v in s.items() if k != "stage"}
        lines.append(f"  [{name}] {json.dumps(extra, ensure_ascii=False)}")
    return "\n".join(lines)
