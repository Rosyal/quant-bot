"""
合规审批工作流辅助: SLA 过期、待办列表 (非法律意见).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from db.database import Database


def list_pending_approvals_stale(
    db: "Database",
    *,
    older_than_hours: int,
    limit: int = 200,
) -> list[dict]:
    """超过 N 小时仍为 pending 的审批 (用于运营告警)。"""
    if older_than_hours <= 0:
        return []
    cutoff = int(time.time()) - older_than_hours * 3600
    rows = db.list_approval_requests(status="pending", limit=limit)
    return [dict(r) for r in rows if int(r.get("created_ts") or 0) < cutoff]


def approval_row_usable_for_order(row: dict | None) -> tuple[bool, str]:
    """校验审批记录是否仍可用于关联下单。"""
    if not row:
        return False, "审批不存在"
    st = (row.get("status") or "").lower()
    if st == "approved":
        return True, "ok"
    if st == "expired":
        return False, "审批已过期 (SLA), 请重新提交"
    if st == "pending":
        return False, "审批尚未通过"
    return False, f"审批状态不可用于下单: {st}"


def run_sla_expire_job(db: "Database", *, max_age_hours: int) -> dict[str, Any]:
    """将超期 pending 标记为 expired; 返回影响行数。"""
    n = db.expire_pending_approvals(max_age_hours=max_age_hours)
    return {"expired_count": n, "max_age_hours": max_age_hours}
