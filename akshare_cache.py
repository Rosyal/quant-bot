"""
AkShare 数据缓存 — A股数据基础设施
LRU 缓存 + TTL + 预热 + 线程安全 + 多数据源
聚宽级别数据服务
"""
import time
import json
import os
import threading
import hashlib
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import OrderedDict

from utils.logger import get_logger

logger = get_logger("akshare_cache")

CACHE_DATA_DIR = "data/akshare_cache"


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str = ""
    data: Any = None
    created_at: float = 0.0
    ttl: int = 3600       # 秒
    hit_count: int = 0
    size_bytes: int = 0


class LRUCache:
    """线程安全 LRU 缓存"""

    def __init__(self, max_size: int = 500, default_ttl: int = 3600):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry.created_at < entry.ttl:
                    # 命中，移到末尾
                    self._cache.move_to_end(key)
                    entry.hit_count += 1
                    self._hits += 1
                    return entry.data
                else:
                    # 过期
                    del self._cache[key]
            self._misses += 1
            return None

    def set(self, key: str, data: Any, ttl: int = 0):
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # 淘汰最旧

            entry = CacheEntry(
                key=key, data=data,
                created_at=time.time(),
                ttl=ttl or self._default_ttl,
                size_bytes=len(json.dumps(data, default=str)) if data else 0,
            )
            self._cache[key] = entry

    def invalidate(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0,
                "total_bytes": sum(e.size_bytes for e in self._cache.values()),
            }


class AkShareCache:
    """AkShare 数据缓存服务 — 聚宽级别"""

    def __init__(self, max_cache_size: int = 500, default_ttl: int = 3600):
        self._cache = LRUCache(max_cache_size, default_ttl)
        self._ak = None
        self._warmup_done = False
        self._lock = threading.RLock()

        # TTL 配置：不同数据类型不同过期时间
        self._ttl_config = {
            "stock_zh_a_hist": 1800,        # 日K 30分钟
            "stock_zh_a_hist_min": 60,       # 分钟K 1分钟
            "stock_individual_info_em": 86400, # 个股信息 24小时
            "stock_zh_index_daily": 1800,     # 指数日K 30分钟
            "stock_board_industry_name_em": 86400,  # 行业板块 24小时
            "stock_board_concept_name_em": 86400,    # 概念板块 24小时
            "stock_financial_abstract_ths": 86400,   # 财务摘要 24小时
            "stock_financial_analysis_indicator": 86400,  # 财务指标 24小时
            "stock_zh_a_spot_em": 30,         # 实时行情 30秒
            "stock_zh_a_gdhs": 86400,         # 股东户数 24小时
            "stock_institute_hold": 86400,    # 机构持仓 24小时
            "stock_rank_forecast_cninfo": 86400,  # 分析师预测 24小时
            "index_stock_cons": 86400,        # 指数成分 24小时
            "stock_dividend_cninfo": 86400,   # 分红数据 24小时
        }

    def _get_ak(self):
        """延迟导入 akshare"""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
                logger.info("AkShare 初始化成功")
            except ImportError:
                raise ImportError("请安装 akshare: pip install akshare")
        return self._ak

    def _cache_key(self, func_name: str, **kwargs) -> str:
        """生成缓存 key"""
        params = json.dumps(kwargs, sort_keys=True, default=str)
        hash_part = hashlib.md5(params.encode()).hexdigest()[:12]
        return f"{func_name}:{hash_part}"

    def _fetch(self, func_name: str, ttl: int = 0, **kwargs) -> Any:
        """通用缓存获取"""
        key = self._cache_key(func_name, **kwargs)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        ak = self._get_ak()
        func = getattr(ak, func_name, None)
        if func is None:
            raise AttributeError(f"AkShare 无此函数: {func_name}")

        data = func(**kwargs)
        effective_ttl = ttl or self._ttl_config.get(func_name, 3600)
        self._cache.set(key, data, effective_ttl)
        return data

    # ============================================================
    # 行情数据
    # ============================================================

    def get_stock_daily(self, symbol: str, start_date: str = "",
                        end_date: str = "", adjust: str = "qfq") -> Any:
        """获取A股日K线"""
        params = {"symbol": symbol, "period": "daily", "adjust": adjust}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._fetch("stock_zh_a_hist", **params)

    def get_stock_minute(self, symbol: str, period: str = "5",
                         adjust: str = "qfq") -> Any:
        """获取A股分钟K线"""
        return self._fetch("stock_zh_a_hist_min", symbol=symbol,
                           period=period, adjust=adjust)

    def get_stock_realtime(self) -> Any:
        """获取A股实时行情"""
        return self._fetch("stock_zh_a_spot_em", ttl=30)

    def get_stock_info(self, symbol: str) -> Any:
        """获取个股基本信息"""
        return self._fetch("stock_individual_info_em", symbol=symbol)

    # ============================================================
    # 指数数据
    # ============================================================

    def get_index_daily(self, symbol: str = "000300",
                        start_date: str = "", end_date: str = "") -> Any:
        """获取指数日K线"""
        params = {"symbol": symbol}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._fetch("stock_zh_index_daily", **params)

    def get_index_constituents(self, symbol: str = "000300") -> Any:
        """获取指数成分股"""
        return self._fetch("index_stock_cons", symbol=symbol)

    # ============================================================
    # 板块数据
    # ============================================================

    def get_industry_boards(self) -> Any:
        """获取行业板块列表"""
        return self._fetch("stock_board_industry_name_em")

    def get_concept_boards(self) -> Any:
        """获取概念板块列表"""
        return self._fetch("stock_board_concept_name_em")

    def get_board_stocks(self, symbol: str = "BK0477") -> Any:
        """获取板块成分股"""
        return self._fetch("stock_board_industry_cons_em", symbol=symbol)

    # ============================================================
    # 财务数据
    # ============================================================

    def get_financial_abstract(self, symbol: str) -> Any:
        """获取财务摘要"""
        return self._fetch("stock_financial_abstract_ths", symbol=symbol)

    def get_financial_indicator(self, symbol: str) -> Any:
        """获取财务分析指标"""
        return self._fetch("stock_financial_analysis_indicator", symbol=symbol)

    def get_dividend(self, symbol: str) -> Any:
        """获取分红数据"""
        return self._fetch("stock_dividend_cninfo", symbol=symbol)

    # ============================================================
    # 股东/机构数据
    # ============================================================

    def get_shareholder_count(self, symbol: str) -> Any:
        """获取股东户数"""
        return self._fetch("stock_zh_a_gdhs", symbol=symbol)

    def get_institution_hold(self, quarter: str = "20243") -> Any:
        """获取机构持仓"""
        return self._fetch("stock_institute_hold", quarter=quarter)

    def get_analyst_forecast(self, date: str = "") -> Any:
        """获取分析师预测"""
        params = {}
        if date:
            params["date"] = date
        return self._fetch("stock_rank_forecast_cninfo", **params)

    # ============================================================
    # 通用查询
    # ============================================================

    def query(self, func_name: str, ttl: int = 0, **kwargs) -> Any:
        """通用 AkShare 查询（带缓存）"""
        return self._fetch(func_name, ttl=ttl, **kwargs)

    # ============================================================
    # 缓存管理
    # ============================================================

    def warmup(self, symbols: List[str] = None):
        """预热缓存 — 提前加载常用数据"""
        if self._warmup_done:
            return
        logger.info("开始预热 AkShare 缓存...")

        try:
            # 预热实时行情
            self.get_stock_realtime()
            logger.info("预热: 实时行情 ✓")

            # 预热指数
            self.get_index_daily("000300")
            logger.info("预热: 沪深300 ✓")

            # 预热板块
            self.get_industry_boards()
            logger.info("预热: 行业板块 ✓")

            # 预热指定个股
            if symbols:
                for sym in symbols[:20]:  # 最多20只
                    try:
                        self.get_stock_daily(sym)
                    except Exception:
                        pass
                logger.info(f"预热: {min(len(symbols), 20)} 只个股 ✓")

            self._warmup_done = True
            logger.info("AkShare 缓存预热完成")
        except Exception as e:
            logger.error(f"预热失败: {e}")

    def invalidate_symbol(self, symbol: str):
        """清除某只股票的所有缓存"""
        # 简单实现：清除所有缓存（精确清除需要遍历key）
        self._cache.clear()
        logger.info(f"已清除 {symbol} 相关缓存")

    def get_stats(self) -> dict:
        """缓存统计"""
        return self._cache.stats()

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._warmup_done = False
