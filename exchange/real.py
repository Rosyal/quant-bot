"""
实盘交易所接口
通过 ccxt 连接真实交易所, 支持 API Key 管理
"""
import os
import json
from datetime import datetime
from utils.logger import get_logger

logger = get_logger("exchange.real")


class APIKeyManager:
    """API Key 安全管理"""

    def __init__(self, keys_file: str = "data/api_keys.json"):
        self.keys_file = keys_file
        self._keys: dict[str, dict] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.keys_file):
            with open(self.keys_file, "r") as f:
                self._keys = json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(self.keys_file) or ".", exist_ok=True)
        with open(self.keys_file, "w") as f:
            json.dump(self._keys, f, indent=2)

    def set_key(self, exchange: str, api_key: str, api_secret: str, passphrase: str = ""):
        """保存 API Key"""
        self._keys[exchange] = {
            "api_key": api_key,
            "api_secret": api_secret,
            "passphrase": passphrase,
            "updated_at": datetime.now().isoformat(),
        }
        self._save()
        logger.info(f"API Key 已保存: {exchange}")

    def get_key(self, exchange: str) -> dict | None:
        """获取 API Key"""
        return self._keys.get(exchange)

    def remove_key(self, exchange: str):
        """删除 API Key"""
        self._keys.pop(exchange, None)
        self._save()


class RealExchange:
    """实盘交易所"""

    def __init__(self, exchange_name: str, key_manager: APIKeyManager):
        self.exchange_name = exchange_name
        self.key_manager = key_manager
        self._exchange = None

    def _connect(self) -> bool:
        if self._exchange:
            return True
        key_info = self.key_manager.get_key(self.exchange_name)
        if not key_info:
            logger.error(f"未配置 {self.exchange_name} 的 API Key")
            return False
        try:
            import ccxt
            exchange_class = getattr(ccxt, self.exchange_name, None)
            if not exchange_class:
                logger.error(f"ccxt 不支持交易所: {self.exchange_name}")
                return False
            self._exchange = exchange_class({
                "apiKey": key_info["api_key"],
                "secret": key_info["api_secret"],
                "password": key_info.get("passphrase", ""),
                "enableRateLimit": True,
            })
            return True
        except ImportError:
            logger.error("ccxt 未安装")
            return False

    def get_balance(self) -> dict | None:
        if not self._connect():
            return None
        try:
            return self._exchange.fetch_balance()
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            return None

    def create_market_buy(self, symbol: str, amount: float) -> dict | None:
        if not self._connect():
            return None
        try:
            order = self._exchange.create_market_buy_order(symbol, amount)
            logger.info(f"实盘买入: {symbol} {amount:.6f}")
            return order
        except Exception as e:
            logger.error(f"买入失败: {e}")
            return None

    def create_market_sell(self, symbol: str, amount: float) -> dict | None:
        if not self._connect():
            return None
        try:
            order = self._exchange.create_market_sell_order(symbol, amount)
            logger.info(f"实盘卖出: {symbol} {amount:.6f}")
            return order
        except Exception as e:
            logger.error(f"卖出失败: {e}")
            return None

    def get_open_orders(self, symbol: str | None = None) -> list:
        if not self._connect():
            return []
        try:
            return self._exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"获取订单失败: {e}")
            return []

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        if not self._connect():
            return False
        try:
            self._exchange.cancel_order(order_id, symbol)
            logger.info(f"订单已取消: {order_id}")
            return True
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False
