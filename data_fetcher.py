"""
数据获取模块
使用 ccxt 从交易所获取历史K线数据 (免费公开接口, 无需API Key)
"""
from __future__ import annotations
import time
from datetime import datetime, timedelta
from utils.logger import get_logger
from config import TIMEFRAME, BACKTEST_DAYS

logger = get_logger("data")


def timeframe_to_seconds(timeframe: str) -> int:
    tf = (timeframe or "1h").strip().lower()
    m = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return m.get(tf, 3600)


def _normalize_ccxt_row(c: list) -> dict:
    return {
        "timestamp": c[0] // 1000,
        "open": c[1],
        "high": c[2],
        "low": c[3],
        "close": c[4],
        "volume": c[5],
    }


def _dedupe_sort(candles: list[dict]) -> list[dict]:
    candles.sort(key=lambda x: x["timestamp"])
    seen: set[int] = set()
    out: list[dict] = []
    for c in candles:
        if c["timestamp"] not in seen:
            seen.add(c["timestamp"])
            out.append(c)
    return out


def detect_ohlcv_gaps(
    candles: list[dict],
    timeframe: str,
    *,
    max_report: int = 20,
) -> list[tuple[int, int, int]]:
    """
    检测相邻 K 线时间间隔是否异常大于 1.5 倍周期。
    返回 [(前一戳, 后一戳, 实际间隔秒), ...]
    """
    if len(candles) < 2:
        return []
    step = timeframe_to_seconds(timeframe)
    gaps: list[tuple[int, int, int]] = []
    for i in range(1, len(candles)):
        dt = candles[i]["timestamp"] - candles[i - 1]["timestamp"]
        if dt > int(step * 1.5):
            gaps.append((candles[i - 1]["timestamp"], candles[i]["timestamp"], dt))
    return gaps[:max_report]


def fetch_ohlcv_ccxt_since(
    symbol: str,
    timeframe: str,
    since_ms: int,
    *,
    max_batches: int = 80,
) -> list[dict]:
    """从 since_ms (毫秒) 起增量拉取直到接近当前时间"""
    try:
        import ccxt
    except ImportError:
        logger.error("ccxt 未安装, 请运行: pip install ccxt")
        return []

    exchange = ccxt.binance({"enableRateLimit": True})
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    all_rows: list[dict] = []
    since = since_ms
    batches = 0

    while batches < max_batches:
        try:
            raw = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except Exception as e:
            logger.error(f"增量获取失败: {e}")
            break
        if not raw:
            break
        for c in raw:
            all_rows.append(_normalize_ccxt_row(c))
        since = raw[-1][0] + 1
        batches += 1
        if raw[-1][0] >= now_ms - 2000 or len(raw) < 1000:
            break
        time.sleep(exchange.rateLimit / 1000)

    return _dedupe_sort(all_rows)


def fetch_ohlcv_ccxt_latest(
    symbol: str,
    timeframe: str,
    limit: int = 200,
) -> list[dict]:
    """最近 limit 根 K 线 (用于实盘轮询)"""
    try:
        import ccxt
    except ImportError:
        logger.error("ccxt 未安装")
        return []
    exchange = ccxt.binance({"enableRateLimit": True})
    try:
        raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        logger.error(f"获取最新 K 线失败: {e}")
        return []
    return _dedupe_sort([_normalize_ccxt_row(c) for c in raw])


def sync_symbol_to_db(db, symbol: str, timeframe: str, *, days_if_empty: int) -> dict:
    """
    增量写入 SQLite: 无历史则全量拉 days_if_empty; 否则从库内最大时间戳前重叠若干根续拉。
    返回: {"new_bars": int, "gaps": [...], "total_in_db": int}
    """
    from db.database import Database

    if not isinstance(db, Database):
        raise TypeError("db 须为 Database 实例")

    max_ts = db.get_ohlcv_max_timestamp(symbol, timeframe)
    tf_sec = timeframe_to_seconds(timeframe)

    if max_ts is None:
        candles = fetch_ohlcv_ccxt(symbol, timeframe, days_if_empty)
    else:
        overlap = 5
        since_ms = max(0, (max_ts - overlap * tf_sec)) * 1000
        candles = fetch_ohlcv_ccxt_since(symbol, timeframe, since_ms)

    new_bars = len(candles)
    if candles:
        db.save_ohlcv(symbol, timeframe, candles)

    merged = db.get_ohlcv(symbol, timeframe, limit=50_000)
    gaps = detect_ohlcv_gaps(merged, timeframe)
    if gaps:
        logger.warning(
            f"{symbol} {timeframe} 发现 {len(gaps)} 处可能缺档 "
            f"(相邻间隔 > 1.5×周期), 示例: {gaps[:3]}"
        )

    return {
        "new_bars": new_bars,
        "gaps_found": len(gaps),
        "gaps": gaps,
        "total_in_db": db.get_ohlcv_count(symbol, timeframe),
    }


def fetch_ohlcv_ccxt(symbol: str, timeframe: str, days: int = BACKTEST_DAYS) -> list[dict]:
    """
    使用 ccxt 获取历史K线数据
    :param symbol: 交易对
    :param timeframe: K线周期
    :param days: 获取多少天的数据
    :return: K线数据列表
    """
    try:
        import ccxt
    except ImportError:
        logger.error("ccxt 未安装, 请运行: pip install ccxt")
        return []

    # 使用 Binance 公开接口 (无需API Key)
    exchange = ccxt.binance({"enableRateLimit": True})

    # 计算起始时间
    since = int(
        (datetime.utcnow() - timedelta(days=days)).timestamp() * 1000
    )

    logger.info(f"正在从 Binance 获取 {symbol} {timeframe} 最近 {days} 天数据...")

    all_candles = []
    while True:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not candles:
                break

            for c in candles:
                all_candles.append(_normalize_ccxt_row(c))

            # 更新 since 为最后一根K线的时间
            since = candles[-1][0] + 1

            # 如果获取的数据少于1000条, 说明已经到头了
            if len(candles) < 1000:
                break

            time.sleep(exchange.rateLimit / 1000)  # 遵守频率限制

        except Exception as e:
            logger.error(f"获取数据失败: {e}")
            break

    unique_candles = _dedupe_sort(all_candles)

    logger.info(f"获取完成: {len(unique_candles)} 条K线数据")
    return unique_candles


def generate_mock_data(
    days: int = BACKTEST_DAYS,
    seed: int | None = 42,
    *,
    silent: bool = False,
) -> list[dict]:
    """
    生成模拟K线数据 (用于无网络环境测试)
    模拟一个有趋势的价格走势
    :param seed: 随机种子; None 表示不复位随机状态(连续调用可衔接随机流)
    :param silent: True 时不打日志 (大批量蒙特卡洛用)
    """
    import random

    if not silent:
        logger.info(f"生成 {days} 天模拟K线数据...")

    if seed is not None:
        random.seed(seed)
    candles = []
    base_price = 40000.0  # 模拟 BTC 起始价格
    current_time = int(
        (datetime.utcnow() - timedelta(days=days)).timestamp()
    )

    # 每小时一根K线
    interval = 3600
    total_candles = days * 24

    for i in range(total_candles):
        # 模拟趋势 + 随机波动
        trend = 50 * (1 if random.random() > 0.48 else -1)  # 轻微上涨趋势
        noise = random.gauss(0, 200)
        change = trend + noise

        open_price = base_price
        close_price = open_price + change
        high_price = max(open_price, close_price) + abs(random.gauss(0, 100))
        low_price = min(open_price, close_price) - abs(random.gauss(0, 100))
        volume = random.uniform(100, 1000)

        candles.append({
            "timestamp": current_time + i * interval,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": round(volume, 2),
        })

        base_price = close_price

    if not silent:
        logger.info(f"模拟数据生成完成: {len(candles)} 条K线")
    return candles
