"""
Walk-Forward 优化器
"""
from utils.logger import get_logger

logger = get_logger("optimizer.walk_forward")


def walk_forward(candles: list[dict], strategy_name: str, param_grid: dict,
                 train_pct: float = 0.7, symbol: str = "BTC/USDT") -> list[dict]:
    """
    Walk-Forward 分析：训练集优化参数 → 测试集验证。
    返回每轮的训练/测试结果。
    """
    from optimizer.grid_search import grid_search

    split = int(len(candles) * train_pct)
    train_candles = candles[:split]
    test_candles = candles[split:]

    if not train_candles or not test_candles:
        logger.warning("数据不足以做 Walk-Forward")
        return []

    # 训练集优化
    train_results = grid_search(train_candles, strategy_name, param_grid, symbol)
    if not train_results:
        return []

    best_params = train_results[0]["params"]

    # 测试集验证
    from strategy import get_strategy
    from exchange.paper import PaperExchange
    from config import INITIAL_BALANCE, FEE_RATE

    s = get_strategy(strategy_name, **best_params)
    signals = s.generate_signals(test_candles)
    exchange = PaperExchange(INITIAL_BALANCE, FEE_RATE)

    for signal in signals:
        price = signal.get("price", 0)
        if price <= 0:
            continue
        sig = signal.get("signal", "hold")
        if sig == "buy" and exchange.coin == 0:
            exchange.buy(symbol, price)
        elif sig == "sell" and exchange.coin > 0:
            exchange.sell(symbol, price)

    final = exchange.get_balance(test_candles[-1]["close"] if test_candles else 0)
    test_profit = (final["total_value"] - INITIAL_BALANCE) / INITIAL_BALANCE * 100

    return [{
        "best_params": best_params,
        "train_profit_pct": train_results[0]["profit_pct"],
        "test_profit_pct": round(test_profit, 2),
        "train_trades": train_results[0]["total_trades"],
        "test_trades": len(exchange.trades),
    }]
