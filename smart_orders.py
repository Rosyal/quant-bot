"""
智能订单 — 追踪止盈、OCO(One-Cancels-Other)、冰山单、止损限价单
3Commas/Cryptohopper 核心功能
支持持久化、批量管理、条件触发链
"""
import time
import json
import os
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime

from utils.logger import get_logger

logger = get_logger("smart_orders")

SMART_ORDER_DIR = "data/smart_orders"


class OrderType(Enum):
    TRAILING_TAKE_PROFIT = "trailing_tp"
    OCO = "oco"
    ICEBERG = "iceberg"
    STOP_LIMIT = "stop_limit"


@dataclass
class SmartOrder:
    """智能订单"""
    id: str = ""
    type: OrderType = OrderType.TRAILING_TAKE_PROFIT
    symbol: str = ""
    side: str = "sell"
    amount: float = 0.0
    # Trailing TP
    activation_price: float = 0.0    # 激活价格
    callback_rate: float = 1.0       # 回调比例 %
    highest_price: float = 0.0       # 追踪到的最高/低价
    # OCO
    take_profit_price: float = 0.0
    stop_loss_price: float = 0.0
    # Iceberg
    total_amount: float = 0.0        # 总量
    visible_amount: float = 0.0      # 可见量
    placed_amount: float = 0.0       # 已挂量
    slice_size: float = 0.0          # 每次挂单量
    slice_interval_sec: float = 30.0 # 挂单间隔秒
    last_slice_time: float = 0.0     # 上次挂单时间
    # Stop Limit
    stop_price: float = 0.0          # 触发价
    limit_price: float = 0.0         # 限价
    # Common
    status: str = "pending"          # pending / active / triggered / cancelled / partial
    trigger_price: float = 0.0
    created_at: str = ""
    updated_at: str = ""


class SmartOrderManager:
    """智能订单管理器 — 3Commas 级别"""

    def __init__(self):
        self._orders: Dict[str, SmartOrder] = {}
        self._load()

    # ---- 创建订单 ----

    def create_trailing_tp(self, symbol: str, side: str, amount: float,
                           activation_price: float, callback_rate: float = 1.0) -> Dict:
        """创建追踪止盈单"""
        order = SmartOrder(
            id=self._gen_id("ttp"),
            type=OrderType.TRAILING_TAKE_PROFIT,
            symbol=symbol, side=side, amount=amount,
            activation_price=activation_price,
            callback_rate=callback_rate,
            highest_price=activation_price,
            status="pending",
            created_at=self._now(), updated_at=self._now(),
        )
        self._orders[order.id] = order
        self._save()
        logger.info(f"追踪止盈单创建: {order.id} {symbol} 激活价{activation_price} 回调{callback_rate}%")
        return self._to_dict(order)

    def create_oco(self, symbol: str, side: str, amount: float,
                   take_profit_price: float, stop_loss_price: float) -> Dict:
        """创建 OCO 单（止盈+止损二选一）"""
        order = SmartOrder(
            id=self._gen_id("oco"),
            type=OrderType.OCO,
            symbol=symbol, side=side, amount=amount,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            status="active",
            created_at=self._now(), updated_at=self._now(),
        )
        self._orders[order.id] = order
        self._save()
        logger.info(f"OCO 单创建: {order.id} {symbol} TP={take_profit_price} SL={stop_loss_price}")
        return self._to_dict(order)

    def create_iceberg(self, symbol: str, side: str, total_amount: float,
                       visible_amount: float, slice_size: float = 0,
                       slice_interval_sec: float = 30.0) -> Dict:
        """创建冰山单"""
        if slice_size <= 0:
            slice_size = visible_amount
        order = SmartOrder(
            id=self._gen_id("ice"),
            type=OrderType.ICEBERG,
            symbol=symbol, side=side, amount=visible_amount,
            total_amount=total_amount,
            visible_amount=visible_amount,
            placed_amount=0.0,
            slice_size=slice_size,
            slice_interval_sec=slice_interval_sec,
            last_slice_time=0.0,
            status="active",
            created_at=self._now(), updated_at=self._now(),
        )
        self._orders[order.id] = order
        self._save()
        logger.info(f"冰山单创建: {order.id} {symbol} 总量{total_amount} 可见{visible_amount}")
        return self._to_dict(order)

    def create_stop_limit(self, symbol: str, side: str, amount: float,
                          stop_price: float, limit_price: float) -> Dict:
        """创建止损限价单"""
        order = SmartOrder(
            id=self._gen_id("slm"),
            type=OrderType.STOP_LIMIT,
            symbol=symbol, side=side, amount=amount,
            stop_price=stop_price, limit_price=limit_price,
            status="pending",
            created_at=self._now(), updated_at=self._now(),
        )
        self._orders[order.id] = order
        self._save()
        logger.info(f"止损限价单创建: {order.id} {symbol} 触发{stop_price} 限价{limit_price}")
        return self._to_dict(order)

    # ---- 价格更新 ----

    def tick(self, symbol: str, current_price: float) -> List[Dict]:
        """价格更新，检查所有订单触发条件"""
        triggered = []

        for order in list(self._orders.values()):
            if order.status not in ("pending", "active", "partial"):
                continue
            if order.symbol != symbol:
                continue

            result = self._check_order(order, current_price)
            if result:
                triggered.append(result)

        if triggered:
            self._save()
        return triggered

    def tick_all(self, prices: Dict[str, float]) -> List[Dict]:
        """批量价格更新"""
        all_triggered = []
        for symbol, price in prices.items():
            all_triggered.extend(self.tick(symbol, price))
        return all_triggered

    def _check_order(self, order: SmartOrder, price: float) -> Optional[Dict]:
        """检查单个订单触发条件"""
        if order.type == OrderType.TRAILING_TAKE_PROFIT:
            return self._check_trailing_tp(order, price)
        elif order.type == OrderType.OCO:
            return self._check_oco(order, price)
        elif order.type == OrderType.ICEBERG:
            return self._check_iceberg(order, price)
        elif order.type == OrderType.STOP_LIMIT:
            return self._check_stop_limit(order, price)
        return None

    def _check_trailing_tp(self, order: SmartOrder, price: float) -> Optional[Dict]:
        """追踪止盈逻辑"""
        # 激活检查
        if order.status == "pending":
            if order.side == "sell" and price >= order.activation_price:
                order.status = "active"
                order.highest_price = price
                order.updated_at = self._now()
                logger.info(f"追踪止盈激活: {order.id} 价格{price}")
            elif order.side == "buy" and price <= order.activation_price:
                order.status = "active"
                order.highest_price = price
                order.updated_at = self._now()
                logger.info(f"追踪止盈激活: {order.id} 价格{price}")
            else:
                return None

        if order.status != "active":
            return None

        # 追踪最高/低价
        if order.side == "sell":
            if price > order.highest_price:
                order.highest_price = price
            callback_price = order.highest_price * (1 - order.callback_rate / 100)
            if price <= callback_price:
                order.status = "triggered"
                order.trigger_price = price
                order.updated_at = self._now()
                return {"order_id": order.id, "type": "trailing_tp", "action": "sell",
                        "symbol": order.symbol, "price": price, "amount": order.amount,
                        "highest": order.highest_price}
        else:  # buy
            if price < order.highest_price:
                order.highest_price = price
            callback_price = order.highest_price * (1 + order.callback_rate / 100)
            if price >= callback_price:
                order.status = "triggered"
                order.trigger_price = price
                order.updated_at = self._now()
                return {"order_id": order.id, "type": "trailing_tp", "action": "buy",
                        "symbol": order.symbol, "price": price, "amount": order.amount,
                        "lowest": order.highest_price}

        return None

    def _check_oco(self, order: SmartOrder, price: float) -> Optional[Dict]:
        """OCO 逻辑"""
        if order.side == "sell":
            if price >= order.take_profit_price:
                order.status = "triggered"
                order.trigger_price = price
                order.updated_at = self._now()
                return {"order_id": order.id, "type": "oco_tp", "action": "sell",
                        "symbol": order.symbol, "price": price, "amount": order.amount}
            if price <= order.stop_loss_price:
                order.status = "triggered"
                order.trigger_price = price
                order.updated_at = self._now()
                return {"order_id": order.id, "type": "oco_sl", "action": "sell",
                        "symbol": order.symbol, "price": price, "amount": order.amount}
        else:  # buy
            if price <= order.take_profit_price:
                order.status = "triggered"
                order.trigger_price = price
                order.updated_at = self._now()
                return {"order_id": order.id, "type": "oco_tp", "action": "buy",
                        "symbol": order.symbol, "price": price, "amount": order.amount}
            if price >= order.stop_loss_price:
                order.status = "triggered"
                order.trigger_price = price
                order.updated_at = self._now()
                return {"order_id": order.id, "type": "oco_sl", "action": "buy",
                        "symbol": order.symbol, "price": price, "amount": order.amount}
        return None

    def _check_iceberg(self, order: SmartOrder, price: float) -> Optional[Dict]:
        """冰山单逻辑 — 按间隔分批挂单"""
        if order.placed_amount >= order.total_amount:
            order.status = "triggered"
            order.updated_at = self._now()
            return None  # 已全部完成

        now = time.time()
        if now - order.last_slice_time < order.slice_interval_sec:
            return None  # 间隔未到

        remaining = order.total_amount - order.placed_amount
        slice_qty = min(order.slice_size, remaining)

        order.placed_amount += slice_qty
        order.last_slice_time = now
        order.status = "partial" if order.placed_amount < order.total_amount else "triggered"
        order.updated_at = self._now()

        return {"order_id": order.id, "type": "iceberg_slice",
                "action": order.side, "symbol": order.symbol,
                "price": price, "amount": slice_qty,
                "placed_total": order.placed_amount,
                "remaining": order.total_amount - order.placed_amount}

    def _check_stop_limit(self, order: SmartOrder, price: float) -> Optional[Dict]:
        """止损限价逻辑"""
        if order.status != "pending":
            return None

        triggered = False
        if order.side == "sell" and price <= order.stop_price:
            triggered = True
        elif order.side == "buy" and price >= order.stop_price:
            triggered = True

        if triggered:
            order.status = "triggered"
            order.trigger_price = price
            order.updated_at = self._now()
            return {"order_id": order.id, "type": "stop_limit",
                    "action": order.side, "symbol": order.symbol,
                    "stop_price": order.stop_price, "limit_price": order.limit_price,
                    "amount": order.amount}
        return None

    # ---- 管理操作 ----

    def cancel(self, order_id: str) -> bool:
        if order_id in self._orders:
            self._orders[order_id].status = "cancelled"
            self._orders[order_id].updated_at = self._now()
            self._save()
            return True
        return False

    def cancel_all(self, symbol: str = "") -> int:
        """取消所有订单，返回取消数量"""
        count = 0
        for order in self._orders.values():
            if order.status in ("pending", "active", "partial"):
                if symbol and order.symbol != symbol:
                    continue
                order.status = "cancelled"
                order.updated_at = self._now()
                count += 1
        if count:
            self._save()
        return count

    def get_order(self, order_id: str) -> Optional[Dict]:
        order = self._orders.get(order_id)
        return self._to_dict(order) if order else None

    def list_orders(self, symbol: str = "", status: str = "",
                    order_type: str = "") -> List[Dict]:
        orders = list(self._orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        if status:
            orders = [o for o in orders if o.status == status]
        if order_type:
            orders = [o for o in orders if o.type.value == order_type]
        return [self._to_dict(o) for o in orders]

    def get_stats(self) -> Dict:
        """统计信息"""
        total = len(self._orders)
        by_status = {}
        by_type = {}
        for o in self._orders.values():
            by_status[o.status] = by_status.get(o.status, 0) + 1
            by_type[o.type.value] = by_type.get(o.type.value, 0) + 1
        return {"total": total, "by_status": by_status, "by_type": by_type}

    # ---- 持久化 ----

    def _save(self):
        os.makedirs(SMART_ORDER_DIR, exist_ok=True)
        path = os.path.join(SMART_ORDER_DIR, "orders.json")
        data = {}
        for oid, order in self._orders.items():
            d = asdict(order)
            d["type"] = order.type.value
            data[oid] = d
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def _load(self):
        path = os.path.join(SMART_ORDER_DIR, "orders.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for oid, d in data.items():
                d["type"] = OrderType(d["type"])
                self._orders[oid] = SmartOrder(**d)
        except Exception as e:
            logger.error(f"加载智能订单失败: {e}")

    # ---- 工具方法 ----

    def _to_dict(self, order: SmartOrder) -> Dict:
        d = asdict(order)
        d["type"] = order.type.value
        return d

    def _gen_id(self, prefix: str) -> str:
        return f"{prefix}-{hashlib.md5(f'{time.time()}'.encode()).hexdigest()[:8]}"

    def _now(self) -> str:
        return datetime.now().isoformat()
