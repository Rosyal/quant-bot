"""
网格搜索优化器
"""
from utils.logger import get_logger
from backtest.engine import _run_backtest_core

logger = get_logger("optimizer.grid_search")


def grid_search(candles: list[dict], strategy_name: str, param_grid: dict,
                symbol: str = "BTC/USDT", sort_by: str = "profit_pct") -> list[dict]:
    """
    网格搜索：遍历参数组合，返回按 sort_by 排序的结果列表。
    param_grid: {"fast": [5,10], "slow": [20,30]} → 2×2=4 种组合
    """
    import itertools

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combos = list(itertools.product(*values))

    results = []
    for combo in combos:
        params = dict(zip(keys, combo))
        try:
            from strategy import get_strategy
            s = get_strategy(strategy_name, **params)
            if s is None:
                continue
            signals = s.generate_signals(candles)
            if not signals:
                continue

            from exchange.paper import PaperExchange
            from config import INITIAL_BALANCE, FEE_RATE
            exchange = PaperExchange(INITIAL_BALANCE, FEE_RATE)
            equity_curve = []
            for signal in signals:
                price = signal.get("price", 0)
                if price <= 0:
                    continue
                sig = signal.get("signal", "hold")
                if sig == "buy" and exchange.coin == 0:
                    exchange.buy(symbol, price)
                elif sig == "sell" and exchange.coin > 0:
                    exchange.sell(symbol, price)
                bal = exchange.get_balance(price)
                equity_curve.append(bal["total_value"])

            if not equity_curve:
                continue

            final = equity_curve[-1]
            profit_pct = (final - INITIAL_BALANCE) / INITIAL_BALANCE * 100
            total_trades = len(exchange.trades)
            wins = sum(1 for t in exchange.trades if t.get("profit", 0) > 0)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

            results.append({
                "params": params,
                "profit_pct": round(profit_pct, 2),
                "total_trades": total_trades,
                "win_rate": round(win_rate, 2),
                "final_value": round(final, 2),
            })
        except Exception as e:
            logger.warning(f"参数组合 {params} 失败: {e}")

    results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return results


def print_optimizer_report(results: list[dict], top_n: int = 10):
    """打印优化报告"""
    if not results:
        print("优化无结果")
        return
    print(f"\n{'='*70}")
    print(f"  参数优化报告 (Top {min(top_n, len(results))})")
    print(f"{'='*70}")
    for i, r in enumerate(results[:top_n], 1):
        print(f"  #{i} 参数={r['params']}  收益={r['profit_pct']:+.2f}%  "
              f"交易={r['total_trades']}  胜率={r['win_rate']:.1f}%")
    print(f"{'='*70}\n")
