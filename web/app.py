"""
量化交易 Bot - Web 看板
FastAPI + ECharts 暗色主题 SPA
"""
import json
import os
import sys
import threading
from typing import Any

# 确保项目根目录在 path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from config import SYMBOL, TIMEFRAME, BACKTEST_DAYS, INITIAL_BALANCE, STRATEGY, WEB_HOST, WEB_PORT
from db.database import Database
from data_fetcher import fetch_ohlcv_ccxt, generate_mock_data
from backtest.engine import run_backtest
from backtest.monte_carlo import run_monte_carlo
from optimizer.grid_search import grid_search
from strategy import list_strategies, get_strategy, generate_signals
from user.manager import UserManager
from exchange.real import APIKeyManager
from kms_service import KMSService, KMSConfig, EncryptedPayload
from latency_monitor import latency_monitor
from strategy_marketplace import StrategyMarketplace
from copy_trading import CopyTradingService
from strategy_grid import GridTradingBot, GridConfig, GridType
from strategy_dca import DCABot, DCAConfig
from smart_orders import SmartOrderManager, OrderType
from signal_bot import SignalBot
from portfolio import PortfolioManager, PortfolioConfig
from factor_library import FactorLibrary

app = FastAPI(title="QuantBot", version="2.0", docs_url="/api/docs")

db = Database()
user_mgr = UserManager()
key_mgr = APIKeyManager()
kms = KMSService()
marketplace = StrategyMarketplace()
copy_trading = CopyTradingService()
smart_orders = SmartOrderManager()
signal_bot = SignalBot()
portfolio_mgr = PortfolioManager(PortfolioConfig())
factor_screener = FactorLibrary()

OUTPUT_DIR = os.path.join(ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============ 页面 ============

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ============ 回测 API ============

class BacktestRequest(BaseModel):
    strategy: str = STRATEGY
    symbol: str = SYMBOL
    timeframe: str = TIMEFRAME
    days: int = BACKTEST_DAYS
    mock: bool = False
    params: dict = {}


@app.post("/api/backtest")
async def api_backtest(req: BacktestRequest):
    if req.mock:
        candles = generate_mock_data(req.days)
    else:
        candles = fetch_ohlcv_ccxt(req.symbol, req.timeframe, req.days)

    if not candles:
        return JSONResponse({"success": False, "error": "无法获取K线数据"}, status_code=500)

    result = run_backtest(req.strategy, candles, req.symbol, **req.params)
    if result:
        db.save_backtest(req.strategy, req.symbol, result, req.params)
    return JSONResponse({"success": True, "result": result})


@app.post("/api/montecarlo")
async def api_montecarlo(req: BacktestRequest):
    if req.mock:
        candles = generate_mock_data(req.days)
    else:
        candles = fetch_ohlcv_ccxt(req.symbol, req.timeframe, req.days)

    if not candles:
        return JSONResponse({"success": False, "error": "无法获取K线数据"}, status_code=500)

    from backtest.monte_carlo import run_monte_carlo
    result = run_backtest(req.strategy, candles, req.symbol, **req.params)
    if not result:
        return JSONResponse({"success": False, "error": "回测无结果"}, status_code=500)

    # 提取交易收益率列表
    trade_returns = result.get("trade_returns", [])
    if not trade_returns:
        # 从 trades 构造收益率
        trades = result.get("trades", [])
        trade_returns = [t.get("profit_pct", 0) for t in trades] if trades else []
    if not trade_returns:
        return JSONResponse({"success": False, "error": "无交易记录，无法进行蒙特卡洛模拟"}, status_code=400)

    mc = run_monte_carlo(trade_returns)
    return JSONResponse({"success": True, "backtest": result, "montecarlo": mc})


@app.get("/api/benchmark")
async def api_benchmark(symbol: str = SYMBOL, timeframe: str = TIMEFRAME, days: int = BACKTEST_DAYS):
    """基准对比：买入持有收益"""
    candles = fetch_ohlcv_ccxt(symbol, timeframe, days)
    if not candles or len(candles) < 2:
        return JSONResponse({"success": False, "error": "数据不足"})

    first = candles[0]["close"]
    last = candles[-1]["close"]
    benchmark_pct = (last - first) / first * 100
    return JSONResponse({"success": True, "symbol": symbol, "benchmark_pct": round(benchmark_pct, 2)})


# ============ 策略 API ============

@app.get("/api/strategies")
async def api_strategies():
    return JSONResponse({"strategies": list_strategies()})


# ============ 优化 API ============

class OptimizeRequest(BaseModel):
    strategy: str = STRATEGY
    symbol: str = SYMBOL
    timeframe: str = TIMEFRAME
    days: int = BACKTEST_DAYS
    mock: bool = False
    param_grid: dict = {}
    sort_by: str = "profit_pct"


@app.post("/api/optimize")
async def api_optimize(req: OptimizeRequest):
    if req.mock:
        candles = generate_mock_data(req.days)
    else:
        candles = fetch_ohlcv_ccxt(req.symbol, req.timeframe, req.days)

    if not candles:
        return JSONResponse({"success": False, "error": "无法获取K线数据"}, status_code=500)

    # 如果没有 param_grid，用策略默认的
    if not req.param_grid:
        s = get_strategy(req.strategy)
        if s and hasattr(s, "param_space") and s.param_space:
            req.param_grid = s.param_space
        else:
            return JSONResponse({"success": False, "error": "未提供参数搜索空间"}, status_code=400)

    results = grid_search(candles, req.strategy, req.param_grid, req.symbol, req.sort_by)
    return JSONResponse({"success": True, "results": results})


# ============ 用户 API ============

@app.get("/api/users")
async def api_list_users():
    return JSONResponse({"users": user_mgr.list_users()})


@app.post("/api/users")
async def api_create_user(data: dict):
    username = data.get("username", "")
    password = data.get("password", "")
    role = data.get("role", "user")
    if not username or not password:
        raise HTTPException(400, "用户名和密码不能为空")
    user = user_mgr.create_user(username, password, role)
    if not user:
        raise HTTPException(409, "用户名已存在")
    return JSONResponse({"success": True, "user": user})


@app.delete("/api/users/{username}")
async def api_delete_user(username: str):
    if user_mgr.delete_user(username):
        return JSONResponse({"success": True})
    raise HTTPException(404, "用户不存在")


# ============ API Key 管理 ============

@app.get("/api/keys")
async def api_list_keys():
    keys = []
    for exchange, info in key_mgr._keys.items():
        keys.append({"exchange": exchange, "updated_at": info.get("updated_at", "")})
    return JSONResponse({"keys": keys})


@app.post("/api/keys")
async def api_set_key(data: dict):
    exchange = data.get("exchange", "")
    api_key = data.get("api_key", "")
    api_secret = data.get("api_secret", "")
    passphrase = data.get("passphrase", "")
    if not exchange or not api_key or not api_secret:
        raise HTTPException(400, "参数不完整")
    key_mgr.set_key(exchange, api_key, api_secret, passphrase)
    return JSONResponse({"success": True})


@app.delete("/api/keys/{exchange}")
async def api_remove_key(exchange: str):
    key_mgr.remove_key(exchange)
    return JSONResponse({"success": True})


# ============ 历史记录 ============

@app.get("/api/history")
async def api_history(limit: int = 20):
    return JSONResponse({"records": db.get_backtest_history(limit)})


# ============ 下载 ============

@app.get("/api/download/{filename}")
async def api_download(filename: str):
    filepath = os.path.realpath(os.path.join(OUTPUT_DIR, filename))
    if not filepath.startswith(os.path.realpath(OUTPUT_DIR)):
        raise HTTPException(403, "禁止访问")
    if not os.path.isfile(filepath):
        raise HTTPException(404, "文件不存在")
    return FileResponse(filepath, filename=filename)


# ============ KMS 加密 API ============

@app.post("/api/kms/encrypt")
async def api_kms_encrypt(data: dict):
    plaintext = data.get("plaintext", "")
    if not plaintext:
        raise HTTPException(400, "plaintext 不能为空")
    payload = kms.encrypt(plaintext)
    return JSONResponse({"encrypted": {
        "ciphertext": payload.ciphertext,
        "data_key_encrypted": payload.data_key_encrypted,
        "algorithm": payload.algorithm,
        "key_id": payload.key_id,
        "iv": payload.iv,
    }})

@app.post("/api/kms/decrypt")
async def api_kms_decrypt(data: dict):
    payload = EncryptedPayload(
        ciphertext=data.get("ciphertext", ""),
        data_key_encrypted=data.get("data_key_encrypted", ""),
        algorithm=data.get("algorithm", "AES-256-GCM"),
        key_id=data.get("key_id", ""),
        iv=data.get("iv", ""),
    )
    plaintext = kms.decrypt(payload)
    return JSONResponse({"plaintext": plaintext})

@app.post("/api/kms/rotate")
async def api_kms_rotate():
    ok = kms.rotate_key()
    return JSONResponse({"success": ok})


# ============ 延迟监控 API ============

@app.get("/api/latency")
async def api_latency(source: str = "", operation: str = ""):
    from latency_monitor import DataSource
    src = None
    if source:
        try:
            src = DataSource(source)
        except ValueError:
            pass
    return JSONResponse(latency_monitor.get_stats(source=src, operation=operation))

@app.get("/api/latency/summary")
async def api_latency_summary():
    return JSONResponse(latency_monitor.get_summary())


# ============ 策略市场 API ============

@app.get("/api/marketplace")
async def api_marketplace_list(limit: int = 20):
    return JSONResponse({"listings": marketplace.search(limit=limit)})

@app.get("/api/marketplace/trending")
async def api_marketplace_trending(limit: int = 10):
    return JSONResponse({"listings": marketplace.get_trending(limit)})

@app.post("/api/marketplace/publish")
async def api_marketplace_publish(data: dict):
    listing = marketplace.publish(
        name=data.get("name", ""),
        author=data.get("author", ""),
        description=data.get("description", ""),
        strategy_type=data.get("strategy_type", ""),
        params=data.get("params", {}),
        backtest_summary=data.get("backtest_summary", {}),
        tags=data.get("tags", []),
        price=data.get("price", 0.0),
    )
    return JSONResponse({"success": True, "id": listing.id})

@app.post("/api/marketplace/subscribe/{listing_id}")
async def api_marketplace_subscribe(listing_id: str, data: dict):
    user = data.get("user", "")
    result = marketplace.subscribe(listing_id, user)
    if result is None:
        raise HTTPException(404, "策略不存在")
    return JSONResponse({"success": True, "strategy": result})

@app.post("/api/marketplace/review/{listing_id}")
async def api_marketplace_review(listing_id: str, data: dict):
    rev = marketplace.review(listing_id, data.get("user", ""), data.get("rating", 0), data.get("comment", ""))
    if rev is None:
        raise HTTPException(404, "策略不存在")
    return JSONResponse({"success": True})


# ============ 跟单交易 API ============

@app.get("/api/copy-trading/traders")
async def api_copy_traders(limit: int = 10):
    return JSONResponse({"traders": copy_trading.get_top_traders(limit)})

@app.post("/api/copy-trading/subscribe")
async def api_copy_subscribe(data: dict):
    sub = copy_trading.subscribe(
        user=data.get("user", ""),
        trader_id=data.get("trader_id", ""),
        amount_pct=data.get("amount_pct", 10.0),
        max_loss_pct=data.get("max_loss_pct", 5.0),
    )
    return JSONResponse({"success": True})

@app.get("/api/copy-trading/pnl/{user}")
async def api_copy_pnl(user: str):
    return JSONResponse(copy_trading.get_copy_pnl(user))

@app.get("/api/copy-trading/subscriptions/{user}")
async def api_copy_subscriptions(user: str):
    return JSONResponse({"subscriptions": copy_trading.get_subscriptions(user)})


# ============ 网格交易 API ============

@app.post("/api/grid/create")
async def api_grid_create(data: dict):
    current_price = data.get("current_price", 0)
    if current_price <= 0:
        # 尝试从 REST 获取当前价
        try:
            import ccxt
            ex = ccxt.binance({"enableRateLimit": True})
            ticker = ex.fetch_ticker(data.get("symbol", "BTC/USDT"))
            current_price = ticker["last"]
        except Exception:
            raise HTTPException(400, "current_price 必须提供或可从交易所获取")
    cfg = GridConfig(
        symbol=data.get("symbol", "BTC/USDT"),
        grid_type=GridType(data.get("grid_type", "arithmetic")),
        upper_price=data.get("upper_price", 0),
        lower_price=data.get("lower_price", 0),
        grid_count=data.get("grid_count", 10),
        total_investment=data.get("total_investment", 10000),
    )
    bot = GridTradingBot(cfg)
    bot.start(current_price)
    return JSONResponse({"success": True, "stats": bot.get_stats()})

@app.post("/api/grid/tick")
async def api_grid_tick(data: dict):
    """模拟网格 tick（实际运行中由 WebSocket 驱动）"""
    # 这里只是 API 示例，实际网格由 WebSocket 回调驱动
    return JSONResponse({"message": "网格交易由 WebSocket 实时驱动，此端点仅供测试"})

@app.get("/api/grids")
async def api_grid_list():
    """列出所有网格"""
    from strategy_grid import GridTradingBot
    return JSONResponse({"grids": GridTradingBot.list_grids()})

@app.post("/api/grid/{grid_id}/stop")
async def api_grid_stop(grid_id: str):
    from strategy_grid import GridTradingBot
    bot = GridTradingBot.load(grid_id)
    if not bot:
        raise HTTPException(404, "网格不存在")
    bot.stop()
    return JSONResponse({"success": True})

@app.get("/api/grid/{grid_id}/stats")
async def api_grid_stats(grid_id: str):
    from strategy_grid import GridTradingBot
    bot = GridTradingBot.load(grid_id)
    if not bot:
        raise HTTPException(404, "网格不存在")
    return JSONResponse(bot.get_stats())


# ============ DCA 定投 API ============

@app.post("/api/dca/create")
async def api_dca_create(data: dict):
    current_price = data.get("current_price", 0)
    if current_price <= 0:
        try:
            import ccxt
            ex = ccxt.binance({"enableRateLimit": True})
            ticker = ex.fetch_ticker(data.get("symbol", "BTC/USDT"))
            current_price = ticker["last"]
        except Exception:
            raise HTTPException(400, "current_price 必须提供或可从交易所获取")
    cfg = DCAConfig(
        symbol=data.get("symbol", "BTC/USDT"),
        base_order=data.get("base_order", 100),
        safety_order=data.get("safety_order", 200),
        max_safety_orders=data.get("max_safety_orders", 5),
        price_deviation_pct=data.get("price_deviation_pct", 2.0),
        take_profit_pct=data.get("take_profit_pct", 3.0),
    )
    bot = DCABot(cfg)
    bot.start(current_price)
    return JSONResponse({"success": True, "stats": bot.get_stats()})

@app.get("/api/dca/bots")
async def api_dca_list():
    """列出所有 DCA bot"""
    from strategy_dca import DCABot
    return JSONResponse({"bots": DCABot.list_bots()})

@app.post("/api/dca/{bot_id}/stop")
async def api_dca_stop(bot_id: str):
    from strategy_dca import DCABot
    bot = DCABot.load(bot_id)
    if not bot:
        raise HTTPException(404, "DCA bot 不存在")
    bot.stop()
    return JSONResponse({"success": True})

@app.post("/api/dca/{bot_id}/tick")
async def api_dca_tick(bot_id: str, data: dict):
    from strategy_dca import DCABot
    bot = DCABot.load(bot_id)
    if not bot:
        raise HTTPException(404, "DCA bot 不存在")
    price = data.get("price", 0)
    if price <= 0:
        raise HTTPException(400, "price 必须提供")
    events = bot.tick(price)
    return JSONResponse({"events": events, "stats": bot.get_stats()})


# ============ 智能订单 API ============

@app.post("/api/smart-orders/trailing-tp")
async def api_trailing_tp(data: dict):
    order = smart_orders.create_trailing_tp(
        symbol=data.get("symbol", "BTC/USDT"),
        side=data.get("side", "sell"),
        amount=data.get("amount", 0.01),
        activation_price=data.get("activation_price", 0),
        callback_rate=data.get("callback_rate", 1.0),
    )
    return JSONResponse({"success": True, "order": smart_orders.get_order(order.id)})

@app.post("/api/smart-orders/oco")
async def api_oco(data: dict):
    order = smart_orders.create_oco(
        symbol=data.get("symbol", "BTC/USDT"),
        side=data.get("side", "sell"),
        amount=data.get("amount", 0.01),
        take_profit_price=data.get("take_profit_price", 0),
        stop_loss_price=data.get("stop_loss_price", 0),
    )
    return JSONResponse({"success": True, "order": smart_orders.get_order(order.id)})

@app.post("/api/smart-orders/iceberg")
async def api_iceberg(data: dict):
    order = smart_orders.create_iceberg(
        symbol=data.get("symbol", "BTC/USDT"),
        side=data.get("side", "buy"),
        total_amount=data.get("total_amount", 1.0),
        visible_amount=data.get("visible_amount", 0.1),
    )
    return JSONResponse({"success": True, "order": smart_orders.get_order(order.id)})

@app.get("/api/smart-orders")
async def api_smart_orders_list(symbol: str = "", status: str = ""):
    return JSONResponse({"orders": smart_orders.list_orders(symbol, status)})

@app.post("/api/smart-orders/{order_id}/cancel")
async def api_smart_order_cancel(order_id: str):
    ok = smart_orders.cancel(order_id)
    return JSONResponse({"success": ok})

@app.post("/api/smart-orders/stop-limit")
async def api_stop_limit(data: dict):
    order = smart_orders.create_stop_limit(
        symbol=data.get("symbol", "BTC/USDT"),
        side=data.get("side", "sell"),
        amount=data.get("amount", 0.01),
        stop_price=data.get("stop_price", 0),
        limit_price=data.get("limit_price", 0),
    )
    return JSONResponse({"success": True, "order": smart_orders.get_order(order.id)})

@app.post("/api/smart-orders/tick")
async def api_smart_orders_tick(data: dict):
    """批量更新智能订单价格"""
    prices = data.get("prices", {})
    triggered = smart_orders.tick_all(prices)
    return JSONResponse({"triggered": triggered})

@app.get("/api/smart-orders/stats")
async def api_smart_orders_stats():
    return JSONResponse(smart_orders.get_stats())


# ============ 信号机器人 API ============

@app.post("/api/signals/rule")
async def api_signal_rule_create(data: dict):
    rule = signal_bot.create_rule(
        name=data.get("name", ""),
        symbol=data.get("symbol", "BTC/USDT"),
        action=data.get("action", "buy"),
        amount_pct=data.get("amount_pct", 30),
        source=data.get("source", "tradingview"),
    )
    return JSONResponse({"success": True, "rule_id": rule.id})

@app.post("/api/signals/webhook")
async def api_signal_webhook(data: dict):
    """接收外部 Webhook 信号"""
    result = signal_bot.process_webhook(
        source=data.get("source", "tradingview"),
        payload=data,
    )
    return JSONResponse(result)

@app.get("/api/signals/rules")
async def api_signal_rules():
    return JSONResponse({"rules": signal_bot.get_rules()})

@app.get("/api/signals/records")
async def api_signal_records(limit: int = 50):
    return JSONResponse({"records": signal_bot.get_records(limit)})

@app.get("/api/signals/stats")
async def api_signal_stats():
    return JSONResponse(signal_bot.get_stats())

@app.delete("/api/signals/rule/{rule_id}")
async def api_signal_rule_delete(rule_id: str):
    ok = signal_bot.remove_rule(rule_id)
    return JSONResponse({"success": ok})


# ============ 投资组合 API ============

@app.post("/api/portfolio/weights")
async def api_portfolio_weights(data: dict):
    portfolio_mgr.set_target_weights(data.get("weights", {}))
    return JSONResponse({"success": True})

@app.post("/api/portfolio/update-price")
async def api_portfolio_price(data: dict):
    portfolio_mgr.update_prices(data.get("prices", {}))
    return JSONResponse(portfolio_mgr.portfolio_stats())

@app.get("/api/portfolio/stats")
async def api_portfolio_stats():
    return JSONResponse(portfolio_mgr.portfolio_stats())

@app.post("/api/portfolio/rebalance")
async def api_portfolio_rebalance():
    orders = portfolio_mgr.check_rebalance()
    return JSONResponse({"rebalance_orders": orders})

@app.get("/api/portfolio/risk-parity")
async def api_portfolio_risk_parity():
    weights = portfolio_mgr.risk_parity_weights()
    return JSONResponse({"weights": weights})

@app.get("/api/portfolio/correlation")
async def api_portfolio_correlation():
    """相关性矩阵"""
    corr = portfolio_mgr.correlation_matrix()
    return JSONResponse({"correlation": corr})

@app.get("/api/portfolio/efficient-frontier")
async def api_portfolio_efficient_frontier(n_points: int = 20):
    """有效前沿"""
    frontier = portfolio_mgr.efficient_frontier(n_points)
    return JSONResponse({"frontier": frontier})

@app.get("/api/portfolio/analytics")
async def api_portfolio_analytics():
    """组合分析指标 (Sharpe/Sortino/Calmar/VaR)"""
    return JSONResponse(portfolio_mgr.portfolio_stats())

@app.get("/api/portfolio/positions")
async def api_portfolio_positions():
    return JSONResponse({"positions": portfolio_mgr.get_positions()})

@app.get("/api/kms/mode")
async def api_kms_mode():
    return JSONResponse({"mode": kms.get_mode()})


# ============ 因子选股 API ============

@app.get("/api/factors")
async def api_factors_list():
    return JSONResponse({"factors": factor_screener.get_factor_info()})

@app.post("/api/factors/screen")
async def api_factors_screen(data: dict):
    stock_data = data.get("stocks", [])
    factor_names = data.get("factors", None)
    top_n = data.get("top_n", 10)
    result = factor_screener.screen_top(stock_data, top_n, factor_names)
    return JSONResponse({"results": result})

@app.get("/api/factors/ashare")
async def api_factors_ashare(limit: int = 50):
    data = factor_screener.fetch_a_share_data(limit)
    return JSONResponse({"stocks": data, "count": len(data)})

@app.get("/api/factors/categories")
async def api_factors_categories():
    return JSONResponse({"categories": factor_screener.get_categories()})

@app.post("/api/factors/ic-analysis")
async def api_factors_ic(data: dict):
    """IC/IR 分析"""
    factor_name = data.get("factor_name", "")
    period_values = data.get("period_values", [])
    forward_returns = data.get("forward_returns", [])
    if not factor_name or not period_values or not forward_returns:
        raise HTTPException(400, "参数不完整")
    result = factor_screener.analyze_ic(factor_name, period_values, forward_returns)
    return JSONResponse({"result": result})

@app.post("/api/factors/backtest")
async def api_factors_backtest(data: dict):
    """因子回测"""
    factor_name = data.get("factor_name", "")
    period_values = data.get("period_values", [])
    forward_returns = data.get("forward_returns", [])
    if not factor_name or not period_values or not forward_returns:
        raise HTTPException(400, "参数不完整")
    result = factor_screener.backtest_factor(factor_name, period_values, forward_returns)
    return JSONResponse({"result": result})

@app.post("/api/factors/multi-score")
async def api_factors_multi_score(data: dict):
    """多因子打分"""
    factor_data = data.get("factor_data", {})
    top_n = data.get("top_n", 50)
    result = factor_screener.select_stocks(factor_data, top_n)
    return JSONResponse({"results": result})

@app.get("/api/factors/ashare-score")
async def api_factors_ashare_score(limit: int = 100, top_n: int = 20):
    """一键选股：拉数据 → 算因子 → 打分 → 选股"""
    result = factor_screener.fetch_and_score(limit, top_n)
    return JSONResponse(result)


# ============ 蒙特卡洛高级 API ============

@app.post("/api/montecarlo/parametric-var")
async def api_parametric_var(data: dict):
    """参数化 VaR"""
    from backtest.monte_carlo import parametric_var
    returns = data.get("returns", [])
    confidence = data.get("confidence", 95)
    if not returns:
        raise HTTPException(400, "returns 不能为空")
    result = parametric_var(returns, confidence)
    return JSONResponse(result)

@app.post("/api/montecarlo/stress-test")
async def api_stress_test(data: dict):
    """压力测试"""
    from backtest.monte_carlo import stress_test
    returns = data.get("returns", [])
    scenarios = data.get("scenarios", None)
    if not returns:
        raise HTTPException(400, "returns 不能为空")
    result = stress_test(returns, scenarios)
    return JSONResponse(result)


# ============ 实盘交易 API ============

_live_engine = None


def get_live_engine():
    """获取实盘引擎单例"""
    global _live_engine
    if _live_engine is None:
        from live.engine import LiveEngine
        _live_engine = LiveEngine()
    return _live_engine


@app.post("/api/live/start")
async def api_live_start(data: dict = None):
    """启动实盘引擎（后台线程）"""
    engine = get_live_engine()
    if engine.running:
        return JSONResponse({"success": False, "error": "实盘已在运行"})
    data = data or {}
    if data.get("strategy"):
        engine.strategy_name = data["strategy"]
    if data.get("symbol"):
        engine.symbol = data["symbol"]
    if data.get("timeframe"):
        engine.timeframe = data["timeframe"]
    if data.get("websocket"):
        engine.use_websocket = True
    # 后台线程启动
    t = threading.Thread(target=engine.start, daemon=True)
    t.start()
    return JSONResponse({"success": True, "message": "实盘引擎已启动"})


@app.post("/api/live/stop")
async def api_live_stop():
    """停止实盘引擎"""
    engine = get_live_engine()
    if not engine.running:
        return JSONResponse({"success": False, "error": "实盘未运行"})
    engine.stop()
    return JSONResponse({"success": True, "message": "实盘引擎已停止"})


@app.get("/api/live/status")
async def api_live_status():
    """获取实盘状态"""
    engine = get_live_engine()
    return JSONResponse(engine.get_status())


@app.post("/api/live/grid")
async def api_live_create_grid(data: dict):
    """通过实盘引擎创建网格"""
    engine = get_live_engine()
    if not engine.running:
        return JSONResponse({"success": False, "error": "实盘未运行，请先启动"})
    from strategy_grid import GridConfig, GridType
    cfg = GridConfig(
        symbol=data.get("symbol", engine.symbol),
        grid_type=GridType(data.get("grid_type", "arithmetic")),
        upper_price=data.get("upper_price", 0),
        lower_price=data.get("lower_price", 0),
        grid_count=data.get("grid_count", 10),
        total_investment=data.get("total_investment", 10000),
    )
    bot = engine.create_grid(cfg)
    return JSONResponse({"success": True, "stats": bot.get_stats()})


@app.post("/api/live/dca")
async def api_live_create_dca(data: dict):
    """通过实盘引擎创建 DCA"""
    engine = get_live_engine()
    if not engine.running:
        return JSONResponse({"success": False, "error": "实盘未运行，请先启动"})
    from strategy_dca import DCAConfig
    cfg = DCAConfig(
        symbol=data.get("symbol", engine.symbol),
        base_order=data.get("base_order", 100),
        safety_order=data.get("safety_order", 200),
        max_safety_orders=data.get("max_safety_orders", 5),
        price_deviation_pct=data.get("price_deviation_pct", 2.0),
        take_profit_pct=data.get("take_profit_pct", 3.0),
    )
    bot = engine.create_dca(cfg)
    return JSONResponse({"success": True, "stats": bot.get_stats()})


@app.post("/api/live/signal-webhook")
async def api_live_signal_webhook(data: dict):
    """通过实盘引擎处理信号（自动下单）"""
    engine = get_live_engine()
    if not engine.running:
        return JSONResponse({"success": False, "error": "实盘未运行"})
    result = engine.process_signal_webhook(
        source=data.get("source", "tradingview"),
        payload=data,
    )
    return JSONResponse(result)


# ============ 启动 ============

def start_web(host: str = WEB_HOST, port: int = WEB_PORT):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_web()
