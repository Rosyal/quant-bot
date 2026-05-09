# 实盘网关集成说明（占位）

本仓库 **不包含** 真实报单到交易所/券商的完整网关实现。上线前须由贵方：

1. 选定通道（如 QMT、CTP、FIX、各所 REST/WebSocket）。  
2. 实现最小接口（建议新模块 `broker/<vendor>_gateway.py`）：
   - `submit_order(request) -> broker_order_id`  
   - `cancel_order(broker_order_id)`  
   - `stream_fills(callback)` 或轮询 `query_order(broker_order_id)`  
3. 将回报写入与 `oms_orders` / `oms_executions` 对齐的表结构，或经 ETL 导入。  
4. 与 `python main.py reconcile` 输出做**日终勾稽**。  

安全：网关进程须与看板进程分离；密钥只经 KMS/环境变量注入；生产关闭 `ROUTER_BACKEND=noop` 前须通过合规评审。
