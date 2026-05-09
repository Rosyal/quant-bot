"""托管与权限 (应用层 RBAC 演示, 非 HSM/多签托管)"""

from security.permissions import (
    PermissionDenied,
    assert_can,
    default_role_from_env,
    role_matrix_doc,
)

__all__ = [
    "PermissionDenied",
    "assert_can",
    "default_role_from_env",
    "role_matrix_doc",
]
