"""审计写入: SQLite + 可选 JSONL 双写"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import config as cfg
from db.database import Database


def append_audit_jsonl(payload: dict[str, Any]) -> None:
    path = getattr(cfg, "AUDIT_JSONL_PATH", "") or ""
    if not path.strip():
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def log_audit_event(
    db: Database | None,
    *,
    actor: str,
    action: str,
    resource: str,
    payload: dict[str, Any],
    outcome: str,
    latency_ms: float | None,
) -> None:
    row = {
        "ts": int(time.time()),
        "actor": actor,
        "action": action,
        "resource": resource,
        "payload_json": json.dumps(payload, ensure_ascii=False),
        "outcome": outcome,
        "latency_ms": latency_ms,
    }
    if db is not None:
        db.insert_audit_event(row)
    append_audit_jsonl(row)
