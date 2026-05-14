"""
量化交易 Bot - 主入口
"""
import argparse
import sys
from utils.logger import get_logger
from config import (
    SYMBOL, SYMBOLS, TIMEFRAME, BACKTEST_DAYS, INITIAL_BALANCE,
    STRATEGY, RISK_STOP_LOSS, RISK_TAKE_PROFIT, RISK_TRAILING_STOP,
    RISK_MAX_DAILY_TRADES, RISK_MAX_DAILY_LOSS, RISK_MAX_CONSECUTIVE_LOSSES,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FEISHU_WEBHOOK_URL,
    SERVERCHAN_SENDKEY, WEB_HOST, WEB_PORT,
)
from db.database import Database
from data_fetcher import fetch_ohlcv_ccxt, generate_mock_data
from backtest.engine import run_backtest, print_backtest_report
from backtest.monte_carlo import run_monte_carlo, print_mc_report, print_mc_histogram
from optimizer.grid_search import grid_search, print_optimizer_report
from strategy import list_strategies, get_strategy

logger = get_logger("main")


def cmd_backtest(use_mock: bool = False, export_xlsx: bool = False, export_pdf: bool = False):
    """运行回测"""
    if use_mock:
        candles = generate_mock_data(BACKTEST_DAYS)
    else:
        candles = fetch_ohlcv_ccxt(SYMBOL, TIMEFRAME, BACKTEST_DAYS)

    if not candles:
        logger.error("无法获取K线数据, 回测终止")
        sys.exit(1)

    db = Database()
    result = run_backtest(candles, strategy_name=STRATEGY)
    print_backtest_report(result)

    if export_xlsx:
        from reports.exporter import export_excel
        import os
        os.makedirs("output", exist_ok=True)
        path = f"output/backtest_{STRATEGY}.xlsx"
        export_excel(result, path)
        logger.info(f"Excel 已导出: {path}")

    if export_pdf:
        from reports.exporter import export_html_report
        import os
        os.makedirs("output", exist_ok=True)
        path = f"output/backtest_{STRATEGY}.html"
        export_html_report(result, path)
        logger.info(f"HTML 报告已导出: {path} (可用浏览器打印为 PDF)")

    db.close()


def cmd_monte_carlo(use_mock: bool = False, sims: int = 10000):
    """蒙特卡洛模拟"""
    if use_mock:
        candles = generate_mock_data(BACKTEST_DAYS)
    else:
        candles = fetch_ohlcv_ccxt(SYMBOL, TIMEFRAME, BACKTEST_DAYS)

    if not candles:
        logger.error("无法获取K线数据")
        sys.exit(1)

    bt_result = run_backtest(candles, strategy_name=STRATEGY)
    if not bt_result.get("trades"):
        logger.error("回测无交易记录, 无法进行蒙特卡洛模拟")
        sys.exit(1)

    trade_returns = [t["profit_pct"] for t in bt_result["trades"]]
    mc_result = run_monte_carlo(trade_returns, simulations=sims)
    print_mc_report(mc_result)
    print_mc_histogram(mc_result)


def cmd_optimize(use_mock: bool = False, sort_by: str = "profit_pct"):
    """参数优化"""
    if use_mock:
        candles = generate_mock_data(BACKTEST_DAYS)
    else:
        candles = fetch_ohlcv_ccxt(SYMBOL, TIMEFRAME, BACKTEST_DAYS)

    if not candles:
        logger.error("无法获取K线数据")
        sys.exit(1)

    strategy_obj = get_strategy(STRATEGY)
    param_space = strategy_obj.param_space if hasattr(strategy_obj, "param_space") else {}
    results = grid_search(candles, STRATEGY, param_space, sort_by=sort_by)
    print_optimizer_report(results, sort_by=sort_by)


def cmd_live(symbols: list = None):
    """实盘运行"""
    from live.engine import LiveEngine
    syms = symbols or SYMBOLS
    engine = LiveEngine(syms)
    try:
        engine.run()
    except KeyboardInterrupt:
        logger.info("收到停止信号, 关闭实盘引擎")
        engine.stop()


def cmd_status():
    """查看状态"""
    db = Database()
    try:
        history = db.get_balance_history(limit=10)
        if not history:
            logger.info("暂无交易记录")
            return
        latest = history[-1]
        logger.info(f"最新余额: {latest.get('total_value', 0):.2f} USDT")
        logger.info(f"收益率: {latest.get('profit_pct', 0):.2f}%")
    finally:
        db.close()


def cmd_list_strategies():
    """列出策略"""
    strategies = list_strategies()
    for name, info in strategies.items():
        print(f"  {name:20s} {info.get('name', '')}")


def main():
    parser = argparse.ArgumentParser(description="QuantBot Pro - 量化交易系统")
    subparsers = parser.add_subparsers(dest="command")

    # backtest 命令
    bt_parser = subparsers.add_parser("backtest", help="运行回测")
    bt_parser.add_argument("--mock", action="store_true", help="使用模拟数据")
    bt_parser.add_argument("--export-xlsx", action="store_true", help="导出 Excel 报告")
    bt_parser.add_argument("--export-pdf", action="store_true", help="导出 PDF 报告 (HTML)")

    # montecarlo 命令
    mc_parser = subparsers.add_parser("montecarlo", help="蒙特卡洛模拟")
    mc_parser.add_argument("--mock", action="store_true", help="使用模拟数据")
    mc_parser.add_argument("--sims", type=int, default=10000, help="模拟次数")

    # optimize 命令
    opt_parser = subparsers.add_parser("optimize", help="参数优化")
    opt_parser.add_argument("--mock", action="store_true", help="使用模拟数据")
    opt_parser.add_argument("--sort", default="profit_pct", help="排序字段")

    # live 命令
    live_parser = subparsers.add_parser("live", help="实盘运行")
    live_parser.add_argument("--symbols", nargs="+", help="交易对列表 (默认使用配置文件)")

    # status 命令
    subparsers.add_parser("status", help="查看交易状态")

    # strategies 命令
    subparsers.add_parser("strategies", help="列出可用策略")

    # web 命令
    web_parser = subparsers.add_parser("web", help="启动 Web 看板")
    web_parser.add_argument("--host", default=WEB_HOST, help="监听地址")
    web_parser.add_argument("--port", type=int, default=WEB_PORT, help="监听端口")

    args = parser.parse_args()

    if args.command == "backtest":
        cmd_backtest(use_mock=args.mock, export_xlsx=args.export_xlsx, export_pdf=args.export_pdf)
    elif args.command == "montecarlo":
        cmd_monte_carlo(use_mock=args.mock, sims=args.sims)
    elif args.command == "optimize":
        cmd_optimize(use_mock=args.mock, sort_by=args.sort)
    elif args.command == "live":
        cmd_live(symbols=args.symbols)
    elif args.command == "status":
        cmd_status()
    elif args.command == "strategies":
        cmd_list_strategies()
    elif args.command == "web":
        from web.app import start_web
        start_web(host=args.host, port=args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
