"""
基于角色的访问控制 (演示级)

角色: admin / trader / readonly / none
动作: route_order, read_market, view_audit, change_config, manage_users

真实托管需 KMS、多签、硬件模块与独立审计服务; 此处仅为进程内校验钩子。
"""
from __future__ import annotations

import os
from typing import FrozenSet

# 动作集合
A_ROUTE = "route_order"
A_READ = "read_market"
A_AUDIT = "view_audit"
A_CONFIG = "change_config"
A_USERS = "manage_users"

_MATRIX: dict[str, FrozenSet[str]] = {
    "admin": frozenset({A_ROUTE, A_READ, A_AUDIT, A_CONFIG, A_USERS}),
    "trader": frozenset({A_ROUTE, A_READ, A_AUDIT}),
    "readonly": frozenset({A_READ, A_AUDIT}),
    "none": frozenset(),
}


class PermissionDenied(PermissionError):
    pass


def normalize_role(role: str | None) -> str:
    r = (role or "none").strip().lower()
    return r if r in _MATRIX else "none"


def assert_can(role: str, action: str) -> None:
    r = normalize_role(role)
    allowed = _MATRIX.get(r, _MATRIX["none"])
    if action not in allowed:
        raise PermissionDenied(f"角色 {r!r} 无权执行 {action!r}")


def default_role_from_env() -> str:
    e = os.environ.get("QUANT_BOT_ROLE", "").strip()
    if e:
        return normalize_role(e)
    import config as cfg

    return normalize_role(getattr(cfg, "SECURITY_DEFAULT_ROLE", "trader"))


def role_matrix_doc() -> str:
    lines = ["角色 → 允许动作:", ""]
    for role, acts in sorted(_MATRIX.items()):
        lines.append(f"  {role}: {', '.join(sorted(acts)) or '(无)'}")
    return "\n".join(lines)
