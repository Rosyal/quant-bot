from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass
class OrderRequest:
    """OMS 侧标准订单请求 (简化)"""

    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty_coin: float | None = None
    notional_usdt: float | None = None
    limit_price: float | None = None
    account_id: str = "MAIN"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionReport:
    """EMS 回执 (含简化撮合回报字段; 生产需接交易所私有协议 / FIX / 二进制通道)"""

    status: str  # filled | partial | rejected | routed_dry
    channel: str
    avg_px: float | None
    latency_ns: int
    detail: dict[str, Any] = field(default_factory=dict)
    # --- 模拟/真实回报常见字段 (可选) ---
    filled_qty: float | None = None  # 标的基准资产数量
    filled_notional_usdt: float | None = None
    fee_usdt: float | None = None
    leaves_qty: float | None = None  # 未成交量 (基准资产)
    exec_legs: list[dict[str, Any]] = field(default_factory=list)  # 逐笔成交
