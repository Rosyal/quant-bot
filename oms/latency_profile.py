"""
执行路径延迟画像 (仿真)

真实「共址级」延迟依赖托管机房、内核旁路、FPGA 等; 此处用统计区间刻画 **模型化 RTT+撮合**，
便于压测与对比 retail / colo / cross_region 策略敏感度。
"""
from __future__ import annotations

import random

import config as cfg


def modelled_exchange_latency_ns(profile: str | None = None) -> int:
    """
    返回一段合成延迟 (纳秒), **不**阻塞线程; 写入 ExecutionReport.detail['modelled_exchange_latency_ns']。
    """
    p = (profile or getattr(cfg, "EMS_LATENCY_PROFILE", "retail") or "retail").strip().lower()
    if p == "colo":
        return int(random.uniform(15_000.0, 150_000.0))  # ~15–150 µs
    if p == "cross_region" or p == "xregion":
        return int(random.uniform(35_000_000.0, 140_000_000.0))  # ~35–140 ms
    # retail / 默认
    return int(random.uniform(4_000_000.0, 45_000_000.0))  # ~4–45 ms
