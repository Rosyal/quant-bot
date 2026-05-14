"""
实盘交易引擎 — 全模块集成
WebSocket 实时价格 → 驱动网格/DCA/智能订单 tick
信号机器人 → 自动下单
跟单 → 自动跟单
策略信号 → 自动交易
"""
import asyncio
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from utils.logger import get_logger
from config import SYMBOL, TIMEFRAME, STRATEGY, INITIAL_BALANCE, WS_ENABLED, WS_EXCHANGES
from risk.manager import RiskManager
from notification.notifier import Notifier

logger = get_logger("live.engine")


@dataclass
class LivePosition:
    """实盘持仓"""
    symbol: str = ""
    side: str = ""        # long / short
    amount: float = 0.0
    entry_price: float = 0.0
    opened_at: str = ""


class LiveEngine:
    """
    实盘交易引擎 — 全模块集成
    
    核心循环:
    1. WebSocket/REST 获取实时价格
    2. 驱动网格/DCA/智能订单 tick
    3. 策略信号检测 + 风控
    4. 信号机器人处理
    5. 跟单执行
    """

    def __init__(self, exchange=None, strategy_name: str = STRATEGY,
                 symbol: str = SYMBOL, timeframe: str = TIMEFRAME,
                 use_websocket: bool = False):
        self.exchange = exchange
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.use_websocket = use_websocket or WS_ENABLED
        self.risk = RiskManager()
        self.notifier = Notifier()
        self.running = False
        self._positions: Dict[str, LivePosition] = {}

        # 子模块（延迟初始化）
        self._grid_mgr = None
        self._dca_bots: Dict = {}
        self._smart_orders = None
        self._signal_bot = None
        self._copy_trading = None
        self._ws_fetcher = None
        self._strategy = None

        # 统计
        self._tick_count = 0
        self._last_price: Dict[str, float] = {}
        self._started_at = ""

    # ============================================================
    # 初始化
    # ============================================================

    def init_modules(self):
        """初始化所有子模块"""
        # 策略
        from strategy import get_strategy
        self._strategy = get_strategy(self.strategy_name)

        # 智能订单
        from smart_orders import SmartOrderManager
        self._smart_orders = SmartOrderManager()

        # 信号机器人
        from signal_bot import SignalBot
        self._signal_bot = SignalBot()

        # 跟单
        from copy_trading import CopyTradingService
        self._copy_trading = CopyTradingService()

        # 网格管理器
        from strategy_grid import GridManager
        self._grid_mgr = GridManager()

        # WebSocket
        if self.use_websocket:
            self._init_websocket()

        logger.info(f"实盘引擎模块初始化完成: strategy={self.strategy_name}, ws={self.use_websocket}")

    def _init_websocket(self):
        """初始化 WebSocket 数据源"""
        try:
            from websocket_fetcher import WebSocketFetcher, ExchangeType
            exchanges = [ExchangeType(e) for e in WS_EXCHANGES if e in ["binance", "okx", "bybit"]]
            if not exchanges:
                exchanges = [ExchangeType.BINANCE]
            self._ws_fetcher = WebSocketFetcher(
                exchanges=exchanges,
                symbols=[self.symbol],
                on_slippage_change=self._on_slippage_change,
            )
            logger.info("WebSocket 数据源已初始化")
        except Exception as e:
            logger.warning(f"WebSocket 初始化失败，降级到 REST: {e}")
            self._ws_fetcher = None

    def _on_slippage_change(self, multiplier: float):
        """延迟超标回调 — 调宽滑点"""
        logger.warning(f"延迟超标，滑点倍数调整为 {multiplier:.2f}x")

    # ============================================================
    # 启动/停止
    # ============================================================

    def start(self):
        """启动实盘交易"""
        self.init_modules()
        self.running = True
        self._started_at = datetime.now().isoformat()
        logger.info(f"实盘引擎启动: {self.symbol} | {self.strategy_name} | {self.timeframe}")
        self.notifier.send("实盘启动", f"{self.symbol} {self.strategy_name}")

        try:
            if self._ws_fetcher:
                # WebSocket 模式 — 异步事件循环
                self._run_with_websocket()
            else:
                # REST 轮询模式
                self._run_polling()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """停止实盘"""
        self.running = False
        # 停止所有网格
        if self._grid_mgr:
            for gid, bot in self._grid_mgr._grids.items():
                bot.stop()
        # 停止所有 DCA
        for bid, bot in self._dca_bots.items():
            bot.stop()
        logger.info("实盘引擎已停止")
        self.notifier.send("实盘停止", f"{self.symbol}")

    # ============================================================
    # REST 轮询模式
    # ============================================================

    def _run_polling(self):
        """REST 轮询主循环"""
        interval = self._get_interval_seconds()
        logger.info(f"REST 轮询模式，间隔 {interval}s")

        while self.running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"交易循环异常: {e}")
            time.sleep(interval)

    # ============================================================
    # WebSocket 模式
    # ============================================================

    def _run_with_websocket(self):
        """WebSocket 实时驱动"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _main():
            await self._ws_fetcher.start()
            logger.info("WebSocket 已连接，开始实时交易")

            while self.running:
                try:
                    # 从 WebSocket 缓存获取最新价格
                    ticker = self._ws_fetcher.get_ticker(self.symbol)
                    if ticker and ticker.get("last"):
                        self._process_price(self.symbol, ticker["last"])

                    # 策略信号（用 OHLCV）
                    ohlcv = self._ws_fetcher.get_ohlcv(self.symbol, self.timeframe, 100)
                    if ohlcv and len(ohlcv) >= 30:
                        self._process_strategy(ohlcv)

                except Exception as e:
                    logger.error(f"WebSocket 循环异常: {e}")

                await asyncio.sleep(1)  # 1秒检查一次

        try:
            loop.run_until_complete(_main())
        finally:
            loop.run_until_complete(self._ws_fetcher.stop())
            loop.close()

    # ============================================================
    # 核心逻辑
    # ============================================================

    def _tick(self):
        """单次 REST 轮询"""
        self._tick_count += 1

        # 1. 获取当前价格
        price = self._fetch_current_price()
        if price <= 0:
            return

        self._last_price[self.symbol] = price

        # 2. 驱动子模块 tick
        self._process_price(self.symbol, price)

        # 3. 策略信号
        self._fetch_and_process_strategy()

    def _fetch_current_price(self) -> float:
        """获取当前价格"""
        # 优先从 WebSocket 缓存
        if self._ws_fetcher:
            ticker = self._ws_fetcher.get_ticker(self.symbol)
            if ticker and ticker.get("last"):
                return ticker["last"]

        # 降级到 REST
        if self.exchange:
            try:
                ticker = self.exchange._exchange.fetch_ticker(self.symbol)
                return ticker.get("last", 0)
            except Exception:
                pass

        # 最后尝试 ccxt
        try:
            import ccxt
            ex = ccxt.binance({"enableRateLimit": True})
            ticker = ex.fetch_ticker(self.symbol)
            return ticker.get("last", 0)
        except Exception as e:
            logger.error(f"获取价格失败: {e}")
            return 0

    def _process_price(self, symbol: str, price: float):
        """处理价格更新 — 驱动所有子模块"""
        # 1. 网格 tick
        if self._grid_mgr:
            try:
                events = self._grid_mgr.tick_all({symbol: price})
                for ev in events:
                    self._execute_grid_event(ev)
            except Exception as e:
                logger.error(f"网格 tick 异常: {e}")

        # 2. DCA tick
        for bid, bot in list(self._dca_bots.items()):
            if bot.config.symbol == symbol:
                try:
                    events = bot.tick(price)
                    for ev in events:
                        self._execute_dca_event(bid, ev)
                except Exception as e:
                    logger.error(f"DCA tick 异常 {bid}: {e}")

        # 3. 智能订单 tick
        if self._smart_orders:
            try:
                triggered = self._smart_orders.tick(symbol, price)
                for ev in triggered:
                    self._execute_smart_order_event(ev)
            except Exception as e:
                logger.error(f"智能订单 tick 异常: {e}")

    def _fetch_and_process_strategy(self):
        """获取K线并处理策略信号"""
        try:
            from data_fetcher import fetch_ohlcv_ccxt
            candles = fetch_ohlcv_ccxt(self.symbol, self.timeframe, days=5)
            if candles and len(candles) >= 30:
                self._process_strategy(candles)
        except Exception as e:
            logger.error(f"策略信号处理异常: {e}")

    def _process_strategy(self, candles: list):
        """策略信号检测 + 风控 + 下单"""
        if not self._strategy:
            return

        signal = self._strategy.on_candle(len(candles) - 1, candles)
        current_price = candles[-1]["close"]

        # 风控
        buy_price = self._positions.get(self.symbol, LivePosition()).entry_price
        has_position = self.symbol in self._positions
        signal = self.risk.check_signal(signal, buy_price, current_price, 1 if has_position else 0)

        if signal == "buy" and not has_position:
            self._execute_buy(self.symbol, current_price)
        elif signal == "sell" and has_position:
            self._execute_sell(self.symbol, current_price)

    # ============================================================
    # 订单执行
    # ============================================================

    def _execute_buy(self, symbol: str, price: float):
        """执行买入"""
        amount = INITIAL_BALANCE * 0.3 / price if price > 0 else 0
        if amount <= 0:
            return

        if self.exchange:
            result = self.exchange.create_market_buy(symbol, amount)
            if result:
                self._positions[symbol] = LivePosition(
                    symbol=symbol, side="long", amount=amount,
                    entry_price=price, opened_at=datetime.now().isoformat(),
                )
                logger.info(f"买入: {symbol} {amount:.6f} @ {price:.2f}")
                self.notifier.send("买入信号", f"{symbol} {amount:.6f} @ {price:.2f}")
        else:
            logger.info(f"[模拟] 买入: {symbol} {amount:.6f} @ {price:.2f}")
            self._positions[symbol] = LivePosition(
                symbol=symbol, side="long", amount=amount,
                entry_price=price, opened_at=datetime.now().isoformat(),
            )

    def _execute_sell(self, symbol: str, price: float):
        """执行卖出"""
        pos = self._positions.get(symbol)
        if not pos:
            return

        pnl_pct = (price - pos.entry_price) / pos.entry_price * 100 if pos.entry_price > 0 else 0

        if self.exchange:
            result = self.exchange.create_market_sell(symbol, pos.amount)
            if result:
                self.risk.record_trade(price - pos.entry_price)
                del self._positions[symbol]
                logger.info(f"卖出: {symbol} @ {price:.2f} (盈亏 {pnl_pct:+.2f}%)")
                self.notifier.send("卖出信号", f"{symbol} @ {price:.2f} ({pnl_pct:+.2f}%)")
        else:
            logger.info(f"[模拟] 卖出: {symbol} @ {price:.2f} (盈亏 {pnl_pct:+.2f}%)")
            self.risk.record_trade(price - pos.entry_price)
            del self._positions[symbol]

    def _execute_grid_event(self, event: dict):
        """执行网格触发事件"""
        action = event.get("action", "")
        symbol = event.get("symbol", "")
        price = event.get("price", 0)
        amount = event.get("amount", 0)

        if action == "place_buy":
            self._execute_buy(symbol, price)
            logger.info(f"网格买入: {symbol} {amount:.6f} @ {price:.2f}")
        elif action == "place_sell":
            self._execute_sell(symbol, price)
            logger.info(f"网格卖出: {symbol} {amount:.6f} @ {price:.2f}")

    def _execute_dca_event(self, bot_id: str, event: dict):
        """执行 DCA 触发事件"""
        event_type = event.get("type", "")
        symbol = event.get("symbol", "")
        price = event.get("price", 0)
        amount = event.get("amount", 0)

        if event_type == "base_buy":
            logger.info(f"DCA 基础定投: {symbol} {amount:.6f} @ {price:.2f}")
        elif event_type == "safety_buy":
            logger.info(f"DCA 加仓: {symbol} {amount:.6f} @ {price:.2f}")
        elif event_type == "take_profit":
            self._execute_sell(symbol, price)
            logger.info(f"DCA 止盈: {symbol} @ {price:.2f}")

    def _execute_smart_order_event(self, event: dict):
        """执行智能订单触发事件"""
        order_type = event.get("type", "")
        action = event.get("action", "")
        symbol = event.get("symbol", "")
        price = event.get("price", 0)
        amount = event.get("amount", 0)

        if action == "sell":
            self._execute_sell(symbol, price)
        elif action == "buy":
            self._execute_buy(symbol, price)

        logger.info(f"智能订单触发: {order_type} {action} {symbol} @ {price:.2f}")

    # ============================================================
    # 子模块管理 API
    # ============================================================

    def create_grid(self, config) -> object:
        """创建网格"""
        from strategy_grid import GridTradingBot
        price = self._last_price.get(config.symbol, 0)
        if price <= 0:
            price = self._fetch_current_price()
        bot = self._grid_mgr.create_grid(config, price)
        logger.info(f"网格创建: {config.symbol} {config.grid_type.value} {config.grid_count}格")
        return bot

    def create_dca(self, config) -> object:
        """创建 DCA"""
        from strategy_dca import DCABot
        price = self._last_price.get(config.symbol, 0)
        if price <= 0:
            price = self._fetch_current_price()
        bot = DCABot(config)
        bot.start(price)
        self._dca_bots[bot.bot_id] = bot
        logger.info(f"DCA 创建: {config.symbol} 基础{config.base_order}U")
        return bot

    def process_signal_webhook(self, source: str, payload: dict) -> dict:
        """处理信号 Webhook"""
        result = self._signal_bot.process_webhook(source, payload)
        # 如果信号被执行，触发下单
        if isinstance(result, dict) and "results" in result:
            for r in result["results"]:
                if r.get("status") == "executed":
                    record = r.get("record", {})
                    symbol = record.get("symbol", "")
                    action = record.get("action", "")
                    price = self._last_price.get(symbol, 0)
                    if action == "buy" and price > 0:
                        self._execute_buy(symbol, price)
                    elif action == "sell" and price > 0:
                        self._execute_sell(symbol, price)
        return result

    # ============================================================
    # 状态查询
    # ============================================================

    def get_status(self) -> dict:
        """获取实盘状态"""
        return {
            "running": self.running,
            "started_at": self._started_at,
            "tick_count": self._tick_count,
            "symbol": self.symbol,
            "strategy": self.strategy_name,
            "positions": {s: {"side": p.side, "amount": p.amount,
                              "entry_price": p.entry_price}
                         for s, p in self._positions.items()},
            "last_price": self._last_price,
            "grids": self._grid_mgr.get_all_stats() if self._grid_mgr else [],
            "dca_bots": [bot.get_stats() for bot in self._dca_bots.values()],
            "websocket": self._ws_fetcher is not None,
        }

    def _get_interval_seconds(self) -> int:
        """根据 timeframe 计算轮询间隔"""
        mapping = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
        return mapping.get(self.timeframe, 3600)
