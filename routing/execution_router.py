"""
低延迟实盘路由 — 进程内演示版

说明:
- 真·低延迟需 C++/Rust 共址、内核旁路、专用线程与无 GC 语言; 本模块在 Python 中提供
  **统一路由入口、计时、权限、策略校验、审计** 的扩展点。
- 后端: noop | paper_stub | ccxt_live (默认关闭, 须自行接线并承担合规责任)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal

import config as cfg
from compliance.audit_service import log_audit_event
from compliance.policies import TradingPolicy
from db.database import Database
from execution.order_book_impact import effective_price_sqrt_impact
from security.permissions import A_ROUTE, PermissionDenied, assert_can

BackendName = Literal["noop", "paper_stub", "ccxt_live"]


@dataclass
class RouteResult:
    ok: bool
    reason: str
    effective_price: float | None
    backend: str
    latency_ms: float
    detail: dict[str, Any]


class ExecutionRouter:
    def __init__(
        self,
        *,
        db: Database | None = None,
        role: str | None = None,
        backend: str | None = None,
        policy: TradingPolicy | None = None,
    ):
        self.db = db
        self.role = role or getattr(cfg, "SECURITY_DEFAULT_ROLE", "trader")
        b = (backend or getattr(cfg, "ROUTER_BACKEND", "noop")).strip().lower()
        if b not in ("noop", "paper_stub", "ccxt_live"):
            b = "noop"
        self.backend: BackendName = b  # type: ignore[assignment]
        self.policy = policy or TradingPolicy(
            max_order_usdt=float(getattr(cfg, "COMPLIANCE_MAX_ORDER_USDT", 1e9)),
            allowed_hours_utc=getattr(cfg, "COMPLIANCE_TRADING_HOURS_UTC", None),
        )

    def dry_run_market_order(
        self,
        *,
        symbol: str,
        side: str,
        notional_usdt: float,
        mid: float,
        actor: str = "cli",
    ) -> RouteResult:
        """不下单: 权限 → 合规 → 冲击价 → 审计。"""
        t0 = time.perf_counter()
        detail: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "notional_usdt": notional_usdt,
            "mid": mid,
        }

        def _fin(
            ok: bool,
            reason: str,
            px: float | None,
            outcome: str,
        ) -> RouteResult:
            ms = (time.perf_counter() - t0) * 1000.0
            warn = float(getattr(cfg, "ROUTER_LATENCY_WARN_MS", 500.0))
            if ms > warn:
                detail["latency_warn"] = True
            log_audit_event(
                self.db,
                actor=actor,
                action="dry_run_market",
                resource=symbol,
                payload=detail,
                outcome=outcome,
                latency_ms=ms,
            )
            return RouteResult(ok, reason, px, self.backend, ms, detail)

        try:
            assert_can(self.role, A_ROUTE)
        except PermissionDenied as e:
            return _fin(False, str(e), None, "denied_permission")

        pr = self.policy.check_market_order(notional_usdt)
        if not pr.allowed:
            return _fin(False, pr.reason, None, "denied_policy")

        if self.backend == "noop":
            return _fin(False, "后端为 noop (不落盘成交)", None, "noop_backend")

        if self.backend == "ccxt_live":
            if not getattr(cfg, "CCXT_LIVE_ENABLED", False):
                return _fin(
                    False,
                    "CCXT_LIVE_ENABLED=False, 禁止真下单 (安全默认)",
                    None,
                    "ccxt_disabled",
                )
            return _fin(
                False,
                "ccxt_live 须二次开发接线; 此处拒绝真实报单",
                None,
                "ccxt_not_implemented",
            )

        # paper_stub: 仅仿真成交价
        gamma = float(getattr(cfg, "ORDERBOOK_IMPACT_GAMMA", 0.55))
        depth = float(getattr(cfg, "ORDERBOOK_SYNTH_DEPTH_USD", 5e6))
        try:
            px = effective_price_sqrt_impact(
                side, mid, notional_usdt, depth, gamma=gamma
            )
        except ValueError as e:
            return _fin(False, str(e), None, "invalid_input")
        detail["effective_price"] = px
        detail["impact_model"] = "sqrt_law"
        return _fin(True, "ok", px, "simulated_fill")
