"""
本地模拟撮合: 多档吃单 → 多笔成交回报 (仿真)

非交易所真实撮合序; 用于补齐「有逐笔成交、有 VWAP」的研究链路。
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any

import config as cfg
from execution.order_book_impact import SimpleLimitOrderBook
from oms.latency_profile import modelled_exchange_latency_ns
from oms.types import ExecutionReport, OrderRequest, OrderSide, OrderType


def _walk_ladder(
    levels: list[tuple[float, float]],
    target_notional_usd: float,
) -> list[tuple[float, float, float]]:
    """沿 (价格, 该档美元深度) 吃单, 返回 [(px, usd, qty), ...]。"""
    if target_notional_usd <= 0:
        return []
    rem = float(target_notional_usd)
    out: list[tuple[float, float, float]] = []
    for px, depth_usd in levels:
        if rem <= 0 or px <= 0 or depth_usd <= 0:
            break
        take_usd = min(rem, depth_usd)
        qty = take_usd / px
        out.append((px, take_usd, qty))
        rem -= take_usd
    return out


def _lob_for_mid(mid: float) -> SimpleLimitOrderBook:
    scale = float(getattr(cfg, "ORDERBOOK_SYNTH_DEPTH_USD", 5_000_000.0))
    depth_scale = max(50_000.0, scale / 12.0)
    return SimpleLimitOrderBook(
        mid=mid,
        depth_scale_usd=depth_scale,
        half_spread_bps=float(getattr(cfg, "MATCHING_HALF_SPREAD_BPS", 2.0)),
        levels_each_side=int(getattr(cfg, "MATCHING_LOB_LEVELS", 8)),
        tick_bps=float(getattr(cfg, "MATCHING_TICK_BPS", 3.0)),
    )


def simulate_exchange_match(
    order: OrderRequest,
    mid: float,
    *,
    latency_profile: str | None = None,
) -> ExecutionReport:
    """
    市价单: 中央限价簿吃单 → 多笔 exec_legs; 手续费按 cfg.FEE_RATE 计入。
    """
    t0 = time.perf_counter_ns()
    if order.order_type != OrderType.MARKET:
        return ExecutionReport(
            "rejected",
            "matching_sim",
            None,
            time.perf_counter_ns() - t0,
            {"reason": "模拟撮合仅支持市价单"},
        )
    n = float(order.notional_usdt or 0.0)
    if n <= 0 or mid <= 0:
        return ExecutionReport(
            "rejected",
            "matching_sim",
            None,
            time.perf_counter_ns() - t0,
            {"reason": "名义或 mid 无效"},
        )

    lob = _lob_for_mid(mid)
    side = "buy" if order.side == OrderSide.BUY else "sell"
    if side == "buy":
        levels = lob.ask_levels()
    else:
        levels = lob.bid_levels_high_to_low()

    legs_raw = _walk_ladder(levels, n)
    if not legs_raw:
        return ExecutionReport(
            "rejected",
            "matching_sim",
            None,
            time.perf_counter_ns() - t0,
            {"reason": "订单簿深度不足"},
        )

    filled_notional = sum(x[1] for x in legs_raw)
    total_qty = sum(x[2] for x in legs_raw)
    avg_px = filled_notional / total_qty if total_qty > 0 else None
    fee_rate = float(getattr(cfg, "FEE_RATE", 0.001))
    fee_usdt = filled_notional * fee_rate

    exec_legs: list[dict[str, Any]] = []
    cum_ns = 0
    for px, usd, qty in legs_raw:
        cum_ns += int(random.uniform(800.0, 12_000.0))  # 档间微间隔 (仿真)
        exec_legs.append(
            {
                "exec_id": f"ex-{uuid.uuid4().hex[:10]}",
                "px": px,
                "qty": qty,
                "notional_usdt": usd,
                "fee_usdt": usd * fee_rate,
                "offset_ns": cum_ns,
            }
        )

    leaves_usd = max(0.0, n - filled_notional)
    leaves_qty = leaves_usd / avg_px if avg_px and leaves_usd > 1e-12 else 0.0
    modelled_lat = modelled_exchange_latency_ns(latency_profile)
    status = "filled" if leaves_usd <= 1e-6 else "partial"

    detail: dict[str, Any] = {
        "matcher": "limit_book_walk",
        "side": side,
        "requested_notional_usdt": n,
        "filled_notional_usdt": filled_notional,
        "modelled_exchange_latency_ns": modelled_lat,
        "leg_count": len(exec_legs),
    }

    proc_ns = time.perf_counter_ns() - t0
    return ExecutionReport(
        status=status,
        channel="matching_sim",
        avg_px=avg_px,
        latency_ns=proc_ns,
        detail=detail,
        filled_qty=total_qty,
        filled_notional_usdt=filled_notional,
        fee_usdt=fee_usdt,
        leaves_qty=leaves_qty if status == "partial" else 0.0,
        exec_legs=exec_legs,
    )
