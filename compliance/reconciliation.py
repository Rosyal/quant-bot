"""
日终对账起点: OMS 订单、执行回报、资金划拨、审计事件计数与摘要.

非交易所正式对账单; 差异须由运营与财务人工复核。
"""
from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from db.database import Database


def run_reconciliation(db: "Database") -> dict[str, Any]:
    oms = db.list_oms_orders(limit=5000)
    st = Counter((r.get("status") or "").lower() for r in oms)
    execs = db.list_oms_executions(limit=5000)
    fees = sum(float(x.get("fee_usdt") or 0) for x in execs)
    transfers = db.list_fund_transfers(limit=2000)
    audit = db.list_audit_events(limit=500)
    audit_actions = Counter((r.get("action") or "") for r in audit)
    return {
        "oms_orders_total": len(oms),
        "oms_orders_by_status": dict(st),
        "oms_executions_count": len(execs),
        "oms_executions_fee_usdt_sum": round(fees, 6),
        "fund_transfers_count": len(transfers),
        "transfer_volume_usdt": round(
            sum(float(t.get("amount_usdt") or 0) for t in transfers), 2
        ),
        "recent_audit_sample_actions": dict(audit_actions.most_common(15)),
        "flags": _flags(st, len(execs), len(oms)),
    }


def _flags(st: Counter, n_exec: int, n_oms: int) -> list[str]:
    out: list[str] = []
    filled = st.get("filled", 0) + st.get("partial_filled", 0)
    if filled > 0 and n_exec == 0:
        out.append("存在已成交 OMS 订单但无执行回报记录, 请核查 EMS 持久化开关")
    if n_oms > 0 and filled + st.get("rejected", 0) + st.get("cancelled", 0) < n_oms * 0.5:
        out.append("大量订单非终态, 请检查是否有异常中断")
    return out


def reconciliation_to_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
