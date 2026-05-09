"""
OMS / EMS 脚手架: 订单对象、多通道路由、纳秒计时。

微秒级共址延迟需独立二进制服务; 此处为 Python 扩展点与失败切换演示。
"""

from oms.ems import MultiChannelEMS, channel_paper_stub, channel_sim_latency_stub
from oms.types import ExecutionReport, OrderRequest, OrderSide, OrderType

__all__ = [
    "MultiChannelEMS",
    "channel_paper_stub",
    "channel_sim_latency_stub",
    "ExecutionReport",
    "OrderRequest",
    "OrderSide",
    "OrderType",
]
