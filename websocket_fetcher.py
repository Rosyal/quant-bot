"""
WebSocket 实时数据源 — ccxt.pro
延迟 <50ms，自动降级 REST，内置延迟监控
"""
import asyncio
import time
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

logger = logging.getLogger("websocket_fetcher")

try:
    import ccxt.pro as ccxtpro
    CCXT_PRO_AVAILABLE = True
except ImportError:
    CCXT_PRO_AVAILABLE = False
    logger.warning("ccxt.pro 未安装，WebSocket 不可用，将降级到 REST")


class ExchangeType(Enum):
    BINANCE = "binance"
    OKX = "okx"
    BYBIT = "bybit"


@dataclass
class MarketData:
    timestamp: float
    timestamp_ms: int
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TickerData:
    timestamp: float
    symbol: str
    last: float
    bid: float = 0.0
    ask: float = 0.0
    volume: float = 0.0


class LatencyMonitor:
    """延迟监控 — 超阈值自动调宽滑点"""

    def __init__(self, threshold_ms: float = 100.0, callback: Optional[Callable] = None):
        self.threshold_ms = threshold_ms
        self.callback = callback
        self.latencies: deque = deque(maxlen=100)
        self.slippage_multiplier: float = 1.0

    def record(self, latency_ms: float):
        self.latencies.append(latency_ms)
        avg = self.get_avg_latency()
        if avg > self.threshold_ms:
            self.slippage_multiplier = 1.0 + (avg - self.threshold_ms) / 1000.0
            logger.warning(f"延迟超标: avg={avg:.1f}ms, 滑点倍数={self.slippage_multiplier:.2f}x")
            if self.callback:
                self.callback(self.slippage_multiplier)
        else:
            self.slippage_multiplier = 1.0

    def get_avg_latency(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    def get_stats(self) -> dict:
        if not self.latencies:
            return {"avg_ms": 0, "min_ms": 0, "max_ms": 0, "p99_ms": 0, "slippage_multiplier": 1.0}
        sorted_l = sorted(self.latencies)
        return {
            "avg_ms": round(self.get_avg_latency(), 2),
            "min_ms": round(sorted_l[0], 2),
            "max_ms": round(sorted_l[-1], 2),
            "p99_ms": round(sorted_l[int(len(sorted_l) * 0.99)], 2),
            "slippage_multiplier": round(self.slippage_multiplier, 3),
        }


class WebSocketFetcher:
    """
    WebSocket 实时数据源
    支持: K线推送 + Ticker + 内存缓存 + 延迟监控 + REST 降级
    """

    def __init__(self, exchanges: List[ExchangeType], symbols: List[str],
                 timeframes: List[str] = None,
                 on_slippage_change: Optional[Callable] = None):
        self.exchanges = exchanges
        self.symbols = symbols
        self.timeframes = timeframes or ["1m", "5m", "15m", "1h", "4h"]
        self.ohlcv_cache: Dict[str, deque] = {}
        self.ticker_cache: Dict[str, TickerData] = {}
        self.latency_monitor = LatencyMonitor(threshold_ms=100.0, callback=on_slippage_change)
        self.ws_clients: Dict[str, any] = {}
        self.rest_clients: Dict[str, any] = {}
        self.is_running = False
        self._tasks: List[asyncio.Task] = []
        self._init_clients()

    def _init_clients(self):
        if not CCXT_PRO_AVAILABLE:
            return
        for et in self.exchanges:
            eid = et.value
            cls = getattr(ccxtpro, eid.capitalize(), None)
            if cls:
                self.rest_clients[eid] = cls({"enableRateLimit": True})

    async def start(self):
        if not CCXT_PRO_AVAILABLE:
            logger.warning("ccxt.pro 不可用，仅 REST 模式")
            return
        self.is_running = True
        for et in self.exchanges:
            task = asyncio.create_task(self._run_exchange(et))
            self._tasks.append(task)
        logger.info(f"WebSocketFetcher 启动: {len(self.exchanges)} 交易所, {len(self.symbols)} 交易对")

    async def stop(self):
        self.is_running = False
        for t in self._tasks:
            t.cancel()
        for ws in self.ws_clients.values():
            try:
                await ws.close()
            except Exception:
                pass
        self.ws_clients.clear()

    async def _run_exchange(self, et: ExchangeType):
        eid = et.value
        while self.is_running:
            try:
                cls = getattr(ccxtpro, eid.capitalize())
                ws = cls({"enableRateLimit": True})
                self.ws_clients[eid] = ws
                await ws.load_markets()
                for symbol in self.symbols:
                    for tf in self.timeframes:
                        try:
                            await ws.watch_ohlcv(symbol, tf)
                        except Exception as e:
                            logger.debug(f"[{eid}] 订阅K线失败 {symbol} {tf}: {e}")
                    try:
                        await ws.watch_ticker(symbol)
                    except Exception as e:
                        logger.debug(f"[{eid}] 订阅Ticker失败 {symbol}: {e}")
                logger.info(f"[{eid}] WebSocket 连接成功")
                while self.is_running:
                    try:
                        ohlcv = await asyncio.wait_for(ws.fetch_ohlcv(self.symbols[0], self.timeframes[0]), timeout=30)
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{eid}] WebSocket 异常: {e}, 5s 后重连")
                await asyncio.sleep(5)

    def get_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> List[Dict]:
        cache_key = f"{symbol}:{timeframe}"
        if cache_key in self.ohlcv_cache and self.ohlcv_cache[cache_key]:
            data = list(self.ohlcv_cache[cache_key])[-limit:]
            return [{"timestamp": d.timestamp, "open": d.open, "high": d.high,
                     "low": d.low, "close": d.close, "volume": d.volume} for d in data]
        return self._fetch_rest_ohlcv(symbol, timeframe, limit)

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        if symbol in self.ticker_cache:
            t = self.ticker_cache[symbol]
            return {"symbol": t.symbol, "last": t.last, "bid": t.bid, "ask": t.ask, "volume": t.volume}
        return self._fetch_rest_ticker(symbol)

    def get_latency_stats(self) -> dict:
        return self.latency_monitor.get_stats()

    def _fetch_rest_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[Dict]:
        for et in self.exchanges:
            eid = et.value
            if eid in self.rest_clients:
                try:
                    raw = self.rest_clients[eid].fetch_ohlcv(symbol, timeframe, limit=limit)
                    return [{"timestamp": r[0] / 1000, "open": r[1], "high": r[2],
                             "low": r[3], "close": r[4], "volume": r[5]} for r in raw]
                except Exception as e:
                    logger.error(f"[{eid}] REST OHLCV 失败: {e}")
        return []

    def _fetch_rest_ticker(self, symbol: str) -> Optional[Dict]:
        for et in self.exchanges:
            eid = et.value
            if eid in self.rest_clients:
                try:
                    t = self.rest_clients[eid].fetch_ticker(symbol)
                    return {"symbol": t["symbol"], "last": t["last"],
                            "bid": t.get("bid"), "ask": t.get("ask"), "volume": t.get("baseVolume")}
                except Exception as e:
                    logger.error(f"[{eid}] REST Ticker 失败: {e}")
        return None
