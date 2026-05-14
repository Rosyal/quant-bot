"""
回测引擎
"""
import math
from datetime import datetime
from config import INITIAL_BALANCE, TRADE_AMOUNT_PCT, FEE_RATE, TIMEFRAME
from exchange.paper import PaperExchange
from utils.logger import get_logger

logger = get_logger("backtest")


def _run_backtest_core(candles: list[dict], strategy_name: str, symbol: str = "BTC/USDT",
                       slippage_pct: float = 0.05) -> dict:
    """回测核心逻辑"""
    from strategy import generate_signals

    signals = generate_signals(strategy_name, candles)
    if not signals:
        logger.warning("策略未产生任何信号")
        return {}

    exchange = PaperExchange(INITIAL_BALANCE, FEE_RATE, slippage_pct)
    equity_curve = []
    benchmark_curve = []
    peak = INITIAL_BALANCE
    max_drawdown = 0
    max_drawdown_pct = 0
    monthly_returns = {}

    # 基准: 买入持有
    first_price = candles[0]["close"] if candles else 0
    benchmark_coins = (INITIAL_BALANCE * 0.99) / first_price if first_price > 0 else 0
    benchmark_invested = benchmark_coins > 0

    for signal in signals:
        price = signal.get("price", 0)
        if price <= 0:
            continue

        # 执行交易
        if signal["signal"] == "buy":
            result = exchange.buy(symbol, price, TRADE_AMOUNT_PCT)
            if result:
                buy_price = price
        elif signal["signal"] == "sell":
            result = exchange.sell(symbol, price)
            if result:
                buy_price = 0.0

        # 资金曲线
        bal = exchange.get_balance(price)
        eq_point = {
            "timestamp": signal["timestamp"],
            "balance": round(bal["total_value"], 2),
        }
        # 基准曲线 (嵌入到 equity_curve 中方便前端渲染)
        if benchmark_invested:
            benchmark_value = benchmark_coins * price
            eq_point["benchmark_balance"] = round(benchmark_value, 2)
            benchmark_curve.append({
                "timestamp": signal["timestamp"],
                "balance": round(benchmark_value, 2),
            })
        equity_curve.append(eq_point)
        if bal["total_value"] > peak:
            peak = bal["total_value"]
        dd = peak - bal["total_value"]
        dd_pct = (dd / peak) * 100 if peak > 0 else 0
        if dd_pct > max_drawdown_pct:
            max_drawdown = dd
            max_drawdown_pct = dd_pct

        # 月度收益
        month_key = datetime.fromtimestamp(signal["timestamp"]).strftime("%Y-%m")
        monthly_returns[month_key] = bal["profit_pct"]

    # 最终统计
    final_bal = exchange.get_balance(candles[-1]["close"])

    # 交易统计
    profits = [t["profit_pct"] for t in exchange.trades if t.get("profit_pct", 0) != 0]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0

    # 收益率序列 (用于夏普)
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["balance"]
        curr = equity_curve[i]["balance"]
        if prev > 0:
            returns.append((curr - prev) / prev * 100)

    # 夏普比率
    if returns:
        avg_r = sum(returns) / len(returns)
        std_r = math.sqrt(sum((r - avg_r) ** 2 for r in returns) / (len(returns) - 1)) if len(returns) > 1 else 0
        periods_per_year = 365.25 * 24 / {"1m": 1, "5m": 5, "15m": 15, "1h": 1, "4h": 4, "1d": 24}.get(TIMEFRAME, 1)
        sharpe = round((avg_r / std_r) * math.sqrt(periods_per_year), 2) if std_r > 0 else 0
    else:
        sharpe = 0

    # 基准统计
    benchmark_final = benchmark_curve[-1]["balance"] if benchmark_curve else INITIAL_BALANCE
    benchmark_pct = ((benchmark_final - INITIAL_BALANCE) / INITIAL_BALANCE) * 100 if INITIAL_BALANCE else 0
    alpha = final_bal["profit_pct"] - benchmark_pct

    # 月度分解
    monthly_data = {}
    for month, pct in sorted(monthly_returns.items()):
        monthly_data[month] = round(pct, 2)

    result = {
        "strategy": strategy_name,
        "symbol": symbol,
        "initial_balance": INITIAL_BALANCE,
        "total_value": round(final_bal["total_value"], 2),
        "profit": round(final_bal["profit"], 2),
        "profit_pct": round(final_bal["profit_pct"], 2),
        "buy_count": sum(1 for t in exchange.trades if t["side"] == "buy"),
        "sell_count": sum(1 for t in exchange.trades if t["side"] == "sell"),
        "total_trades": len(exchange.trades),
        "win_rate": round((len(wins) / len(profits) * 100) if profits else 0, 2),
        "avg_profit_pct": round((sum(profits) / len(profits)) if profits else 0, 2),
        "max_win": round(max(wins) if wins else 0, 2),
        "max_loss": round(min(losses) if losses else 0, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0,
        "sharpe_ratio": sharpe,
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "first_date": datetime.fromtimestamp(candles[0]["timestamp"]).strftime("%Y-%m-%d"),
        "last_date": datetime.fromtimestamp(candles[-1]["timestamp"]).strftime("%Y-%m-%d"),
        # 基准对比
        "benchmark_profit_pct": round(benchmark_pct, 2),
        "alpha": round(alpha, 2),
        # 月度分解
        "monthly_returns": monthly_data,
        # 交易记录
        "trades": [
            {
                "timestamp": t["timestamp"],
                "time": datetime.fromtimestamp(t["timestamp"]).strftime("%Y-%m-%d %H:%M"),
                "side": t["side"],
                "price": t["price"],
                "coin_amount": round(t["amount"], 6),
                "amount": round(t["amount"], 6),
                "fee": round(t["fee"], 4),
                "total": round(t["total"], 2),
                "profit": round(t.get("profit", 0), 2),
                "profit_pct": round(t.get("profit_pct", 0), 2),
            }
            for t in exchange.trades
        ],
        # 原始数据
        "candles": candles,
        "signals": signals,
        "equity_curve": equity_curve,
        "benchmark_curve": benchmark_curve,
    }

    return result


def run_backtest(candles: list[dict], strategy_name: str = "ma_cross", **kwargs) -> dict:
    """运行回测"""
    symbol = kwargs.get("symbol", "BTC/USDT")
    slippage_pct = kwargs.get("slippage_pct", 0.05)
    logger.info(f"开始回测: {len(candles)} 条K线, {symbol}, 策略={strategy_name}")
    result = _run_backtest_core(candles, strategy_name, symbol, slippage_pct)
    if result:
        logger.info(f"回测完成: 收益={result['profit_pct']:+.2f}%, 交易={result['total_trades']}次")
    return result


def print_backtest_report(result: dict):
    """打印回测报告"""
    if not result:
        print("回测无结果")
        return
    print(f"\n{'='*50}")
    print(f"  回测报告: {result['strategy']} | {result['symbol']}")
    print(f"  时间范围: {result['first_date']} ~ {result['last_date']}")
    print(f"{'='*50}")
    print(f"  初始资金:       {result['initial_balance']:>12.2f} USDT")
    print(f"  最终资金:       {result['total_value']:>12.2f} USDT")
    print(f"  总盈亏:         {result['profit']:>+12.2f} USDT ({result['profit_pct']:>+8.2f}%)")
    print(f"  买入持有基准:   {result.get('benchmark_profit_pct', 0):>+11.2f}%")
    print(f"  超额收益(α):    {result.get('alpha', 0):>+11.2f}%")
    print(f"{'-'*50}")
    print(f"  总交易次数:     {result['total_trades']:>12d}")
    print(f"  胜率:           {result['win_rate']:>11.2f}%")
    print(f"  盈亏比:         {result['profit_factor']:>12.2f}")
    print(f"  夏普比率:       {result['sharpe_ratio']:>12.2f}")
    print(f"  最大回撤:       {result['max_drawdown_pct']:>11.2f}%")
    print(f"{'='*50}\n")
