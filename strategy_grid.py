"""
网格交易策略 — 加密货币最热门策略
在价格区间内自动挂买卖单，震荡市持续获利
支持：等差/等比网格、自动调参、止损、持久化、多网格管理
3Commas Grid Bot 级别
"""
import math
import json
import os
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime

from utils.logger import get_logger

logger = get_logger("grid_trading")

GRID_DATA_DIR = "data/grids"


class GridType(Enum):
    ARITHMETIC = "arithmetic"  # 等差网格
    GEOMETRIC = "geometric"    # 等比网格


@dataclass
class GridOrder:
    """网格订单"""
    id: str = ""
    side: str = ""       # buy / sell
    price: float = 0.0
    amount: float = 0.0
    filled: bool = False
    profit: float = 0.0
    timestamp: str = ""


@dataclass
class GridConfig:
    """网格配置"""
    symbol: str = "BTC/USDT"
    grid_type: GridType = GridType.ARITHMETIC
    upper_price: float = 0.0      # 网格上界
    lower_price: float = 0.0      # 网格下界
    grid_count: int = 10          # 网格数量
    total_investment: float = 10000.0  # 总投入 USDT
    stop_loss_pct: float = 10.0   # 跌破下界止损 %
    take_profit_pct: float = 0.0  # 涨破上界止盈 % (0=不止盈)
    auto_range: bool = False      # 自动根据ATR计算区间
    atr_multiplier: float = 2.0   # ATR倍数（auto_range时用）


@dataclass
class GridState:
    """网格运行状态"""
    running: bool = False
    orders: List[Dict] = field(default_factory=list)
    current_price: float = 0.0
    filled_count: int = 0
    total_profit: float = 0.0
    started_at: str = ""
    last_tick_at: str = ""


class GridTradingBot:
    """网格交易机器人 — 3Commas 级别"""

    def __init__(self, config: GridConfig, grid_id: str = ""):
        self.config = config
        self.grid_id = grid_id or hashlib.md5(
            f"{config.symbol}:{time.time()}".encode()).hexdigest()[:10]
        self.state = GridState()
        self._price_history: List[float] = []

    def start(self, current_price: float):
        """启动网格"""
        cfg = self.config
        if cfg.auto_range and current_price > 0:
            # 自动计算区间（基于价格的 ±ATR*multiplier 近似）
            atr_approx = current_price * 0.03  # 默认3%近似ATR
            cfg.lower_price = round(current_price - atr_approx * cfg.atr_multiplier, 2)
            cfg.upper_price = round(current_price + atr_approx * cfg.atr_multiplier, 2)

        if cfg.upper_price <= cfg.lower_price:
            raise ValueError(f"网格上界({cfg.upper_price})必须大于下界({cfg.lower_price})")

        self.state.current_price = current_price
        self.state.running = True
        self.state.started_at = datetime.now().isoformat()
        self._generate_orders()
        self._save()
        logger.info(f"网格启动: {cfg.symbol} [{cfg.lower_price}-{cfg.upper_price}] "
                     f"{cfg.grid_count}格 {cfg.grid_type.value}")

    def _generate_orders(self):
        """生成网格订单"""
        cfg = self.config
        orders = []
        amount_per_grid = cfg.total_investment / cfg.grid_count

        for i in range(cfg.grid_count + 1):
            if cfg.grid_type == GridType.ARITHMETIC:
                price = cfg.lower_price + (cfg.upper_price - cfg.lower_price) * i / cfg.grid_count
            else:  # GEOMETRIC
                if cfg.lower_price <= 0:
                    continue
                ratio = (cfg.upper_price / cfg.lower_price) ** (i / cfg.grid_count)
                price = cfg.lower_price * ratio

            price = round(price, 2)
            qty = round(amount_per_grid / price, 8) if price > 0 else 0

            # 买单（低于当前价）
            if price < self.state.current_price:
                orders.append({
                    "id": f"buy-{self.grid_id}-{i}",
                    "side": "buy", "price": price, "amount": qty,
                    "filled": False, "profit": 0.0,
                    "timestamp": datetime.now().isoformat(),
                })
            # 卖单（高于当前价）
            elif price > self.state.current_price:
                orders.append({
                    "id": f"sell-{self.grid_id}-{i}",
                    "side": "sell", "price": price, "amount": qty,
                    "filled": False, "profit": 0.0,
                    "timestamp": datetime.now().isoformat(),
                })

        self.state.orders = orders
        logger.info(f"生成 {len(orders)} 个网格订单")

    def tick(self, current_price: float) -> List[Dict]:
        """价格更新，检查触发"""
        if not self.state.running:
            return []

        self.state.current_price = current_price
        self.state.last_tick_at = datetime.now().isoformat()
        self._price_history.append(current_price)
        if len(self._price_history) > 1000:
            self._price_history = self._price_history[-1000:]

        triggered = []

        # 止损检查
        cfg = self.config
        if cfg.stop_loss_pct > 0 and current_price <= cfg.lower_price * (1 - cfg.stop_loss_pct / 100):
            self.state.running = False
            triggered.append({"action": "stop_loss", "price": current_price,
                              "message": f"触发止损: 价格{current_price}低于下界{cfg.lower_price}"})
            self._save()
            return triggered

        # 止盈检查
        if cfg.take_profit_pct > 0 and current_price >= cfg.upper_price * (1 + cfg.take_profit_pct / 100):
            self.state.running = False
            triggered.append({"action": "take_profit", "price": current_price,
                              "message": f"触发止盈: 价格{current_price}高于上界{cfg.upper_price}"})
            self._save()
            return triggered

        # 检查订单触发
        for order in self.state.orders:
            if order["filled"]:
                continue

            if order["side"] == "buy" and current_price <= order["price"]:
                order["filled"] = True
                self.state.filled_count += 1
                # 生成对应卖单
                sell_price = order["price"] * (1 + self._grid_profit_rate())
                triggered.append({
                    "action": "place_buy",
                    "grid_id": self.grid_id,
                    "price": round(order["price"], 2),
                    "amount": order["amount"],
                    "target_sell_price": round(sell_price, 2),
                })

            elif order["side"] == "sell" and current_price >= order["price"]:
                order["filled"] = True
                self.state.filled_count += 1
                profit = order["amount"] * (order["price"] - self._avg_buy_price(order["price"]))
                self.state.total_profit += profit
                triggered.append({
                    "action": "place_sell",
                    "grid_id": self.grid_id,
                    "price": round(order["price"], 2),
                    "amount": order["amount"],
                    "profit": round(profit, 4),
                })

        self._save()
        return triggered

    def _grid_profit_rate(self) -> float:
        """每格预期利润率"""
        cfg = self.config
        if cfg.grid_type == GridType.ARITHMETIC:
            return (cfg.upper_price - cfg.lower_price) / cfg.grid_count / cfg.lower_price
        else:
            return (cfg.upper_price / cfg.lower_price) ** (1 / cfg.grid_count) - 1

    def _avg_buy_price(self, sell_price: float) -> float:
        """估算对应买入价（简化：卖价-一格利润）"""
        cfg = self.config
        if cfg.grid_type == GridType.ARITHMETIC:
            step = (cfg.upper_price - cfg.lower_price) / cfg.grid_count
            return sell_price - step
        else:
            ratio = (cfg.upper_price / cfg.lower_price) ** (1 / cfg.grid_count)
            return sell_price / ratio

    def get_stats(self) -> dict:
        """网格统计"""
        cfg = self.config
        total_orders = len(self.state.orders)
        filled = self.state.filled_count
        unfilled = sum(1 for o in self.state.orders if not o["filled"])
        return {
            "grid_id": self.grid_id,
            "running": self.state.running,
            "symbol": cfg.symbol,
            "grid_type": cfg.grid_type.value,
            "grid_count": cfg.grid_count,
            "price_range": f"[{cfg.lower_price:.2f}, {cfg.upper_price:.2f}]",
            "current_price": self.state.current_price,
            "total_orders": total_orders,
            "filled_orders": filled,
            "unfilled_orders": unfilled,
            "total_profit": round(self.state.total_profit, 4),
            "roi_pct": round(self.state.total_profit / cfg.total_investment * 100, 2) if cfg.total_investment > 0 else 0,
            "started_at": self.state.started_at,
            "last_tick_at": self.state.last_tick_at,
        }

    def stop(self):
        self.state.running = False
        self._save()
        logger.info("网格交易已停止")

    def _save(self):
        """持久化网格状态"""
        os.makedirs(GRID_DATA_DIR, exist_ok=True)
        path = os.path.join(GRID_DATA_DIR, f"{self.grid_id}.json")
        data = {
            "grid_id": self.grid_id,
            "config": {k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(self.config).items()},
            "state": asdict(self.state),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    @classmethod
    def load(cls, grid_id: str) -> Optional["GridTradingBot"]:
        """加载已保存的网格"""
        path = os.path.join(GRID_DATA_DIR, f"{grid_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg_data = data["config"]
        cfg_data["grid_type"] = GridType(cfg_data["grid_type"])
        config = GridConfig(**cfg_data)
        bot = cls(config, grid_id=grid_id)
        state_data = data["state"]
        bot.state = GridState(**state_data)
        return bot

    @classmethod
    def list_grids(cls) -> List[dict]:
        """列出所有网格"""
        if not os.path.exists(GRID_DATA_DIR):
            return []
        results = []
        for fname in os.listdir(GRID_DATA_DIR):
            if fname.endswith(".json"):
                gid = fname.replace(".json", "")
                bot = cls.load(gid)
                if bot:
                    results.append(bot.get_stats())
        return results


class GridManager:
    """多网格管理器 — 同时运行多个网格"""

    def __init__(self):
        self._grids: Dict[str, GridTradingBot] = {}

    def create_grid(self, config: GridConfig, current_price: float) -> GridTradingBot:
        bot = GridTradingBot(config)
        bot.start(current_price)
        self._grids[bot.grid_id] = bot
        return bot

    def tick_all(self, prices: Dict[str, float]) -> List[Dict]:
        """批量更新价格，返回所有触发事件"""
        events = []
        for gid, bot in self._grids.items():
            if bot.config.symbol in prices:
                triggered = bot.tick(prices[bot.config.symbol])
                for t in triggered:
                    t["grid_id"] = gid
                events.extend(triggered)
        return events

    def stop_grid(self, grid_id: str) -> bool:
        bot = self._grids.get(grid_id)
        if bot:
            bot.stop()
            return True
        return False

    def get_all_stats(self) -> List[dict]:
        return [bot.get_stats() for bot in self._grids.values()]

    def get_total_profit(self) -> float:
        return sum(bot.state.total_profit for bot in self._grids.values())
