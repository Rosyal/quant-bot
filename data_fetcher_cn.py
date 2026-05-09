"""
A 股现货 K 线 (AkShare → 与 crypto 相同的 candle 结构).

- 需可访问数据源网络; 安装: pip install akshare pandas
- 代码为 6 位: 600519、000001; 也接受 600519.SH / sh600519
- 实盘下单不在此模块 (需券商 QMT/xtp/中泰等); 本仓库仅统一行情入口供回测/同步/轮询
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from utils.logger import get_logger

logger = get_logger("data_cn")


def normalize_cn_symbol(symbol: str) -> str:
    """归一为 6 位证券代码。"""
    s = (symbol or "").strip().upper().replace(" ", "")
    s = s.replace(".XSHE", "").replace(".XSHG", "")
    if "." in s:
        left, _right = s.split(".", 1)
        if re.fullmatch(r"\d{6}", left):
            return left
        if left in ("SH", "SZ") and re.fullmatch(r"\d{6}", _right):
            return _right
    m = re.search(r"(\d{6})", s)
    if m:
        return m.group(1)
    s = re.sub(r"\D", "", s)
    return s.zfill(6)[-6:] if s else ""


def _col(df: pd.DataFrame, *names: str) -> pd.Series:
    for n in names:
        if n in df.columns:
            return df[n]
    raise KeyError(f"找不到列 {names} 之一, 实际列: {list(df.columns)}")


def akshare_df_to_candles(df: pd.DataFrame) -> list[dict[str, Any]]:
    """AkShare 返回的 DataFrame → 统一 OHLCV。"""
    if df is None or df.empty:
        return []
    time_col = None
    for c in ("时间", "日期", "time", "date", "datetime"):
        if c in df.columns:
            time_col = c
            break
    if time_col is None:
        logger.error("K 线 DataFrame 缺少时间列")
        return []

    o = _col(df, "开盘", "open", "Open")
    h = _col(df, "最高", "high", "High")
    low = _col(df, "最低", "low", "Low")
    cl = _col(df, "收盘", "close", "Close")
    vol = _col(df, "成交量", "volume", "Volume")

    out: list[dict[str, Any]] = []
    for i in range(len(df)):
        ts_raw = df.iloc[i][time_col]
        if pd.isna(ts_raw):
            continue
        if isinstance(ts_raw, (pd.Timestamp, datetime)):
            ts = int(pd.Timestamp(ts_raw).timestamp())
        else:
            ts = int(pd.Timestamp(str(ts_raw)).timestamp())
        out.append(
            {
                "timestamp": ts,
                "open": float(o.iloc[i]),
                "high": float(h.iloc[i]),
                "low": float(low.iloc[i]),
                "close": float(cl.iloc[i]),
                "volume": float(vol.iloc[i]),
            }
        )
    out.sort(key=lambda x: x["timestamp"])
    return out


def _date_yyyymmdd(d: datetime) -> str:
    return d.strftime("%Y%m%d")


def fetch_ohlcv_cn(
    symbol: str,
    timeframe: str,
    days: int,
    *,
    adjust: str | None = None,
) -> list[dict[str, Any]]:
    """
    拉取 A 股 K 线。
    timeframe: 1d | 1m | 5m | 15m | 30m | 1h(60m)
    """
    try:
        import akshare as ak  # type: ignore
    except ImportError:
        logger.error("AkShare 未安装, 请运行: pip install akshare")
        return []

    import config as cfg

    code = normalize_cn_symbol(symbol)
    if not re.fullmatch(r"\d{6}", code):
        logger.error(f"A股代码无效: {symbol!r} → {code!r}")
        return []

    adj = (adjust or getattr(cfg, "CN_A_ADJUST", "qfq") or "qfq").strip()
    tf = (timeframe or "1d").strip().lower()
    end = datetime.now()
    start = end - timedelta(days=max(int(days), 1) + 10)

    try:
        if tf in ("1d", "d", "day", "1day"):
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=_date_yyyymmdd(start),
                end_date=_date_yyyymmdd(end),
                adjust=adj,
            )
            candles = akshare_df_to_candles(df)
        elif tf in ("1m", "5m", "15m", "30m", "60m", "1h"):
            period_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60", "1h": "60"}
            p = period_map[tf]
            start_s = start.strftime("%Y-%m-%d %H:%M:%S")
            end_s = end.strftime("%Y-%m-%d %H:%M:%S")
            df = ak.stock_zh_a_hist_min_em(
                symbol=code,
                period=p,
                start_date=start_s,
                end_date=end_s,
                adjust=adj,
            )
            candles = akshare_df_to_candles(df)
        else:
            logger.warning(f"A股未识别周期 {tf!r}, 改用日线")
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=_date_yyyymmdd(start),
                end_date=_date_yyyymmdd(end),
                adjust=adj,
            )
            candles = akshare_df_to_candles(df)
    except Exception as e:  # noqa: BLE001
        logger.error(f"AkShare 拉取失败 {code} {tf}: {e}")
        return []

    logger.info(f"A股 K 线 {code} {tf} 共 {len(candles)} 根")
    return candles


def fetch_ohlcv_cn_latest(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    *,
    adjust: str | None = None,
) -> list[dict[str, Any]]:
    """最近 limit 根 (按周期估算回溯天数)。"""
    tf = (timeframe or "1d").strip().lower()
    if tf in ("1d", "d", "day", "1day"):
        days = max(int(limit * 2), 30)
    elif tf in ("1h", "60m"):
        days = max(int(limit // 4) + 30, 14)
    elif tf in ("30m",):
        days = max(int(limit // 8) + 20, 10)
    elif tf in ("15m",):
        days = max(int(limit // 12) + 15, 8)
    elif tf in ("5m",):
        days = max(int(limit // 36) + 10, 5)
    else:  # 1m
        days = max(int(limit // 240) + 5, 3)
    all_c = fetch_ohlcv_cn(symbol, timeframe, days, adjust=adjust)
    return all_c[-max(1, int(limit)) :] if all_c else []


def fetch_ohlcv_cn_since(
    symbol: str,
    timeframe: str,
    since_ms: int,
    *,
    adjust: str | None = None,
) -> list[dict[str, Any]]:
    """自 since_ms (毫秒) 之后的数据 (含重叠一根由上层 sync 处理)。"""
    since_sec = max(0, int(since_ms // 1000))
    start = datetime.utcfromtimestamp(since_sec)
    end = datetime.now()
    days_span = max((end - start).days + 15, 5)
    candles = fetch_ohlcv_cn(symbol, timeframe, days_span, adjust=adjust)
    return [c for c in candles if c["timestamp"] * 1000 >= since_ms]
