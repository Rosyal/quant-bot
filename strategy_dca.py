"""
DCA 定投策略 — 熊市神器
定期定额买入 + 动态加仓 + 止盈退出 + 持久化
3Commas DCA Bot 级别
"""
import math
import json
import os
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime

from utils.logger import get_logger

logger = get_logger("dca_bot")

DCA_DATA_DIR = "data/dca"


@dataclass
class DCAConfig:
    """DCA 配置"""
    symbol: str = "BTC/USDT"
    base_order: float = 100.0        # 基础定投金额 USDT
    safety_order: float = 200.0      # 加仓金额 USDT
    max_safety_orders: int = 5       # 最大加仓次数
    price_deviation_pct: float = 2.0 # 触发加仓的价格偏差 %
    safety_order_step_pct: float = 2.0  # 每次加仓价格步进 %
    safety_order_volume_scale: float = 1.5  # 加仓金额倍数
    take_profit_pct: float = 3.0     # 整体止盈 %
    stop_loss_pct: float = 0.0       # 整体止损 % (0=不止损)
    cooldown_minutes: int = 60       # 两次定投最小间隔
    # 高级参数
    trailing_tp_pct: float = 0.0     # 追踪止盈 % (0=固定止盈)
    min_volume_filter: float = 0.0   # 最小24h成交量过滤 (USDT)
    max_spread_pct: float = 0.5      # 最大买卖价差 %


@dataclass
class DCAOrder:
    """DCA 订单"""
    id: str = ""
    side: str = ""        # base_buy / safety_buy / sell
    price: float = 0.0
    amount: float = 0.0
    cost: float = 0.0
    timestamp: str = ""


@dataclass
class DCAState:
    """DCA 运行状态"""
    running: bool = False
    base_orders: List[Dict] = field(default_factory=list)
    safety_orders: List[Dict] = field(default_factory=list)
    safety_order_count: int = 0
    current_price: float = 0.0
    total_cost: float = 0.0
    total_amount: float = 0.0
    avg_price: float = 0.0
    last_order_time: str = ""
    total_profit: float = 0.0
    started_at: str = ""
    highest_price: float = 0.0  # 追踪止盈用


class DCABot:
    """DCA 定投机器人 — 3Commas 级别"""

    def __init__(self, config: DCAConfig, bot_id: str = ""):
        self.config = config
        self.bot_id = bot_id or hashlib.md5(
            f"{config.symbol}:{time.time()}".encode()).hexdigest()[:10]
        self.state = DCAState()

    def start(self, current_price: float):
        """启动 DCA"""
        self.state.current_price = current_price
        self.state.running = True
        self.state.started_at = datetime.now().isoformat()
        self.state.highest_price = current_price
        # 立即下基础单
        self._place_base_order(current_price)
        self._save()
        logger.info(f"DCA 启动: {self.config.symbol} 基础单{self.config.base_order}U")

    def tick(self, current_price: float) -> List[Dict]:
        """价格更新，检查加仓/止盈/止损"""
        if not self.state.running:
            return []

        self.state.current_price = current_price
        if current_price > self.state.highest_price:
            self.state.highest_price = current_price

        actions = []
        cfg = self.config

        # 止损检查
        if cfg.stop_loss_pct > 0 and self.state.avg_price > 0:
            pnl_pct = (current_price - self.state.avg_price) / self.state.avg_price * 100
            if pnl_pct <= -cfg.stop_loss_pct:
                self.state.running = False
                actions.append({"action": "stop_loss", "price": current_price,
                                "pnl_pct": round(pnl_pct, 2)})
                self._save()
                return actions

        # 止盈检查
        if self.state.avg_price > 0:
            pnl_pct = (current_price - self.state.avg_price) / self.state.avg_price * 100

            if cfg.trailing_tp_pct > 0:
                # 追踪止盈：从最高点回落超过阈值时止盈
                trail_pct = (self.state.highest_price - current_price) / self.state.highest_price * 100
                if pnl_pct >= cfg.take_profit_pct and trail_pct >= cfg.trailing_tp_pct:
                    actions.append({"action": "trailing_take_profit", "price": current_price,
                                    "pnl_pct": round(pnl_pct, 2)})
                    self._close_position(current_price)
                    self._save()
                    return actions
            else:
                # 固定止盈
                if pnl_pct >= cfg.take_profit_pct:
                    actions.append({"action": "take_profit", "price": current_price,
                                    "pnl_pct": round(pnl_pct, 2)})
                    self._close_position(current_price)
                    self._save()
                    return actions

        # 加仓检查
        if self.state.safety_order_count < cfg.max_safety_orders and self.state.avg_price > 0:
            deviation = (self.state.avg_price - current_price) / self.state.avg_price * 100
            next_step = cfg.price_deviation_pct + cfg.safety_order_step_pct * self.state.safety_order_count
            if deviation >= next_step:
                # 冷却时间检查
                if self._check_cooldown():
                    volume_scale = cfg.safety_order_volume_scale ** self.state.safety_order_count
                    safety_amount = cfg.safety_order * volume_scale
                    self._place_safety_order(current_price, safety_amount)
                    actions.append({
                        "action": "safety_buy",
                        "price": current_price,
                        "amount": round(safety_amount, 2),
                        "safety_order_num": self.state.safety_order_count,
                    })

        self._save()
        return actions

    def _place_base_order(self, price: float):
        """下基础定投单"""
        amount = self.config.base_order / price
        order = DCAOrder(
            id=f"base-{self.bot_id}-{len(self.state.base_orders)}",
            side="base_buy", price=price, amount=amount,
            cost=self.config.base_order,
            timestamp=datetime.now().isoformat(),
        )
        self.state.base_orders.append(asdict(order))
        self._update_position(order)

    def _place_safety_order(self, price: float, cost: float):
        """下加仓单"""
        amount = cost / price
        order = DCAOrder(
            id=f"safety-{self.bot_id}-{self.state.safety_order_count}",
            side="safety_buy", price=price, amount=amount,
            cost=cost, timestamp=datetime.now().isoformat(),
        )
        self.state.safety_orders.append(asdict(order))
        self.state.safety_order_count += 1
        self._update_position(order)

    def _close_position(self, price: float):
        """止盈/止损平仓"""
        current_value = self.state.total_amount * price
        self.state.total_profit += current_value - self.state.total_cost
        # 重置状态，准备下一轮
        self.state.total_cost = 0
        self.state.total_amount = 0
        self.state.avg_price = 0
        self.state.safety_order_count = 0
        self.state.base_orders = []
        self.state.safety_orders = []
        self.state.highest_price = price
        # 自动下新一轮基础单
        self._place_base_order(price)

    def _update_position(self, order: DCAOrder):
        """更新持仓"""
        self.state.total_cost += order.cost
        self.state.total_amount += order.amount
        self.state.avg_price = self.state.total_cost / self.state.total_amount if self.state.total_amount > 0 else 0
        self.state.last_order_time = order.timestamp

    def _check_cooldown(self) -> bool:
        """冷却时间检查"""
        if not self.state.last_order_time:
            return True
        try:
            last = datetime.fromisoformat(self.state.last_order_time)
            elapsed = (datetime.now() - last).total_seconds() / 60
            return elapsed >= self.config.cooldown_minutes
        except Exception:
            return True

    def get_stats(self) -> dict:
        cfg = self.config
        current_value = self.state.total_amount * self.state.current_price
        pnl = current_value - self.state.total_cost
        return {
            "bot_id": self.bot_id,
            "running": self.state.running,
            "symbol": cfg.symbol,
            "current_price": self.state.current_price,
            "avg_price": round(self.state.avg_price, 2),
            "total_cost": round(self.state.total_cost, 2),
            "total_amount": round(self.state.total_amount, 8),
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / self.state.total_cost * 100, 2) if self.state.total_cost > 0 else 0,
            "base_orders": len(self.state.base_orders),
            "safety_orders": self.state.safety_order_count,
            "max_safety_orders": cfg.max_safety_orders,
            "total_profit": round(self.state.total_profit, 2),
            "started_at": self.state.started_at,
        }

    def stop(self):
        self.state.running = False
        self._save()
        logger.info("DCA 定投已停止")

    def _save(self):
        """持久化 DCA 状态"""
        os.makedirs(DCA_DATA_DIR, exist_ok=True)
        path = os.path.join(DCA_DATA_DIR, f"{self.bot_id}.json")
        data = {
            "bot_id": self.bot_id,
            "config": asdict(self.config),
            "state": asdict(self.state),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    @classmethod
    def load(cls, bot_id: str) -> Optional["DCABot"]:
        """加载已保存的 DCA"""
        path = os.path.join(DCA_DATA_DIR, f"{bot_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = DCAConfig(**data["config"])
        bot = cls(config, bot_id=bot_id)
        bot.state = DCAState(**data["state"])
        return bot

    @classmethod
    def list_bots(cls) -> List[dict]:
        """列出所有 DCA bot"""
        if not os.path.exists(DCA_DATA_DIR):
            return []
        results = []
        for fname in os.listdir(DCA_DATA_DIR):
            if fname.endswith(".json"):
                bid = fname.replace(".json", "")
                bot = cls.load(bid)
                if bot:
                    results.append(bot.get_stats())
        return results
