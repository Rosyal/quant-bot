"""
延迟监控服务 — 全链路 Tick-to-Trade 延迟追踪
"""
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

from utils.logger import get_logger

logger = get_logger("latency_monitor")


class DataSource(Enum):
    WEBSOCKET = "websocket"
    REST = "rest"
    AKSHARE = "akshare"
    MOCK = "mock"


@dataclass
class LatencyRecord:
    source: DataSource
    operation: str
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


class LatencyMonitorService:
    """全链路延迟监控"""

    def __init__(self, max_records: int = 10000, alert_threshold_ms: float = 200.0):
        self.max_records = max_records
        self.alert_threshold_ms = alert_threshold_ms
        self._records: deque = deque(maxlen=max_records)
        self._lock = threading.Lock()
        self._alert_callbacks = []

    def record(self, source: DataSource, operation: str, latency_ms: float):
        rec = LatencyRecord(source=source, operation=operation, latency_ms=latency_ms)
        with self._lock:
            self._records.append(rec)
        if latency_ms > self.alert_threshold_ms:
            logger.warning(f"延迟告警: {source.value}:{operation} = {latency_ms:.1f}ms > {self.alert_threshold_ms}ms")
            for cb in self._alert_callbacks:
                try:
                    cb(rec)
                except Exception:
                    pass

    def measure(self, source: DataSource, operation: str):
        """上下文管理器：自动测量代码块延迟"""
        class _Measure:
            def __init__(self, monitor, src, op):
                self.monitor = monitor
                self.src = src
                self.op = op
                self.start = 0
            def __enter__(self):
                self.start = time.perf_counter()
                return self
            def __exit__(self, *args):
                ms = (time.perf_counter() - self.start) * 1000
                self.monitor.record(self.src, self.op, ms)
        return _Measure(self, source, operation)

    def add_alert_callback(self, callback):
        self._alert_callbacks.append(callback)

    def get_stats(self, source: DataSource = None, operation: str = None,
                  last_n: int = 100) -> dict:
        with self._lock:
            records = list(self._records)
        if source:
            records = [r for r in records if r.source == source]
        if operation:
            records = [r for r in records if r.operation == operation]
        records = records[-last_n:]
        if not records:
            return {"count": 0, "avg_ms": 0, "min_ms": 0, "max_ms": 0, "p50_ms": 0, "p99_ms": 0}
        latencies = sorted(r.latency_ms for r in records)
        return {
            "count": len(latencies),
            "avg_ms": round(sum(latencies) / len(latencies), 2),
            "min_ms": round(latencies[0], 2),
            "max_ms": round(latencies[-1], 2),
            "p50_ms": round(latencies[len(latencies) // 2], 2),
            "p99_ms": round(latencies[int(len(latencies) * 0.99)], 2),
        }

    def get_summary(self) -> dict:
        """按 source+operation 汇总"""
        with self._lock:
            records = list(self._records)
        groups: Dict[str, List[float]] = {}
        for r in records:
            key = f"{r.source.value}:{r.operation}"
            groups.setdefault(key, []).append(r.latency_ms)
        result = {}
        for key, vals in groups.items():
            s = sorted(vals)
            result[key] = {
                "count": len(s),
                "avg_ms": round(sum(s) / len(s), 2),
                "p50_ms": round(s[len(s) // 2], 2),
                "p99_ms": round(s[int(len(s) * 0.99)], 2),
            }
        return result


# 全局单例
latency_monitor = LatencyMonitorService()
