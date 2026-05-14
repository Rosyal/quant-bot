"""
量化交易 Bot - 数据获取
支持 ccxt 实时数据 / 模拟数据
"""
import random
import time
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger("data")


def fetch_ohlcv_ccxt(symbol: str = "BTC/USDT", timeframe: str = "1h", days: int = 90) -> list[dict]:
    """通过 ccxt 获取 K线数据"""
    try:
        import ccxt
    except ImportError:
        logger.warning("ccxt 未安装, 回退到模拟数据")
        return generate_mock_data(days)

    try:
        exchange = ccxt.binance({"enableRateLimit": True})
        since = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=days * 24)

        candles = []
        for item in ohlcv:
            candles.append({
                "timestamp": item[0] // 1000,
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            })
        logger.info(f"获取 {len(candles)} 条K线: {symbol} {timeframe}")
        return candles
    except Exception as e:
        logger.error(f"ccxt 获取失败: {e}")
        return []


def generate_mock_data(days: int = 90, base_price: float = 40000.0) -> list[dict]:
    """生成模拟K线数据"""
    logger.info(f"生成 {days} 天模拟K线数据...")
    candles = []
    price = base_price
    current_time = int((datetime.utcnow() - timedelta(days=days)).timestamp())

    for i in range(days * 24):
        change = random.gauss(0, 0.005)
        price *= (1 + change)
        price = max(price * 0.5, price)

        open_p = price
        high_p = price * (1 + abs(random.gauss(0, 0.003)))
        low_p = price * (1 - abs(random.gauss(0, 0.003)))
        close_p = price * (1 + random.gauss(0, 0.002))
        volume = random.uniform(10, 500)

        candles.append({
            "timestamp": current_time + i * 3600,
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": round(volume, 2),
        })

    logger.info(f"模拟数据生成完成: {len(candles)} 条K线")
    return candles
