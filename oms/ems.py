"""
多通道 EMS: 按顺序尝试通道 (失败切换)。可与路由/审计/中台规则组合。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Callable

import config as cfg
from execution.order_book_impact import effective_price_sqrt_impact
from oms.types import ExecutionReport, OrderRequest, OrderSide, OrderType

ChannelFn = Callable[[OrderRequest], ExecutionReport]


def channel_paper_stub(order: OrderRequest, mid: float) -> ExecutionReport:
    """仿真成交价 (平方根冲击), 不落库持仓。"""
    if order.order_type != OrderType.MARKET:
        return ExecutionReport(
            "rejected",
            "paper_stub",
            None,
            0,
            {"reason": "仅支持市价单演示"},
        )
    n = float(order.notional_usdt or 0.0)
    if n <= 0 or mid <= 0:
        return ExecutionReport(
            "rejected", "paper_stub", None, 0, {"reason": "名义或价格无效"}
        )
    gamma = float(getattr(cfg, "ORDERBOOK_IMPACT_GAMMA", 0.55))
    depth = float(getattr(cfg, "ORDERBOOK_SYNTH_DEPTH_USD", 5e6))
    side = "buy" if order.side == OrderSide.BUY else "sell"
    px = effective_price_sqrt_impact(side, mid, n, depth, gamma=gamma)
    return ExecutionReport(
        "filled",
        "paper_stub",
        px,
        0,
        {"shock_model": "sqrt_law", "notional_usdt": n},
    )


def channel_sim_latency_stub(order: OrderRequest) -> ExecutionReport:
    """模拟次优通道: 高延迟/拒单, 用于演示 failover。"""
    _ = order
    return ExecutionReport(
        "rejected",
        "sim_slow",
        None,
        0,
        {"reason": "simulated_channel_unavailable"},
    )


class MultiChannelEMS:
    """
    多通道智能路由 (顺序故障切换, 非智能拆单)。

    生产级 EMS 需延迟探测、动态权重、流动性画像; 此处为可插拔列表。
    """

    def __init__(self, channels: list[tuple[str, ChannelFn]]):
        self.channels = channels

    def submit(self, order: OrderRequest) -> ExecutionReport:
        t0 = time.perf_counter_ns()
        last_detail: dict = {}
        for name, fn in self.channels:
            try:
                rep = fn(order)
                rep.channel = name
                rep.latency_ns = time.perf_counter_ns() - t0
                if rep.status == "filled" or rep.status == "routed_dry":
                    return rep
                last_detail = rep.detail
            except Exception as e:  # noqa: BLE001
                last_detail = {"error": str(e)}
                continue
        return ExecutionReport(
            "rejected",
            "ems",
            None,
            time.perf_counter_ns() - t0,
            {"failover_exhausted": True, "last": last_detail},
        )


def make_matching_channel(mid_for_paper: float, db: object | None) -> ChannelFn:
    """模拟交易所撮合 + 可选落库回报与净头寸滚动。"""
    from oms.matching_engine import simulate_exchange_match
    from oms.netting import apply_spot_fill_to_net

    def _fn(order: OrderRequest) -> ExecutionReport:
        profile = getattr(cfg, "EMS_LATENCY_PROFILE", "retail")
        rep = simulate_exchange_match(order, mid_for_paper, latency_profile=profile)
        if db is None:
            return rep
        persist = bool(getattr(cfg, "EMS_PERSIST_EXECUTIONS", True))
        do_net = bool(getattr(cfg, "EMS_APPLY_NETTING", True))
        if rep.status not in ("filled", "partial") or not rep.filled_qty or rep.avg_px is None:
            return rep
        if persist:
            db.insert_oms_execution(
                {
                    "client_order_id": order.client_order_id,
                    "account_id": order.account_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "status": rep.status,
                    "avg_px": rep.avg_px,
                    "filled_qty": rep.filled_qty,
                    "fee_usdt": rep.fee_usdt,
                    "latency_ns": rep.latency_ns,
                    "legs_json": json.dumps(rep.exec_legs, ensure_ascii=False),
                    "detail_json": json.dumps(rep.detail, ensure_ascii=False),
                }
            )
        if do_net:
            apply_spot_fill_to_net(
                db,
                account_id=order.account_id,
                symbol=order.symbol,
                side=order.side.value,
                filled_qty=float(rep.filled_qty),
                avg_px=float(rep.avg_px),
                fee_usdt=rep.fee_usdt,
            )
        return rep

    return _fn


def make_default_ems(mid_for_paper: float, db: object | None = None) -> MultiChannelEMS:
    """
    默认: 可选先走 sim_slow (演示 failover), 再走 matching_sim (多档吃单+逐笔回报),
    最后 paper_stub (单档冲击) 兜底。
    """
    ch: list[tuple[str, ChannelFn]] = []
    if bool(getattr(cfg, "EMS_FAILOVER_SIM_SLOW_FIRST", True)):
        ch.append(("sim_slow", channel_sim_latency_stub))
    ch.append(("matching_sim", make_matching_channel(mid_for_paper, db)))
    ch.append(
        (
            "paper_stub",
            lambda o: channel_paper_stub(o, mid_for_paper),
        )
    )
    return MultiChannelEMS(ch)


def new_client_order_id(prefix: str = "oms") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
