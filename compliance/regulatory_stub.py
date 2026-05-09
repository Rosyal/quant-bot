"""
监管报送占位导出: 审计事件 CSV (内部留存 / 法务抽样).

不构成向监管机构的正式报送; 格式与字段须由合规团队审定。
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from db.database import Database


def _hash_actor(actor: str) -> str:
    return hashlib.sha256(actor.encode("utf-8")).hexdigest()[:16]


def export_audit_events_csv(
    db: "Database",
    path: str,
    *,
    limit: int = 10_000,
    hash_actors: bool = False,
) -> dict[str, Any]:
    rows = db.list_audit_events(limit=min(50_000, max(1, limit)))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fields = ["id", "ts", "actor", "action", "resource", "outcome", "latency_ms", "payload_json"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = dict(r)
            if hash_actors and row.get("actor"):
                row["actor"] = _hash_actor(str(row["actor"]))
            w.writerow(row)
    return {"path": path, "rows": len(rows), "hash_actors": hash_actors}
