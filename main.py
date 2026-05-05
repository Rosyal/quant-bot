"""
量化交易 Bot - 主入口
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from utils.logger import get_logger
from config import (
    SYMBOL,
    SYMBOLS,
    TIMEFRAME,
    BACKTEST_DAYS,
    INITIAL_BALANCE,
    STRATEGY,
    REPORTS_DIR,
)
from db.database import Database
from data_fetcher import fetch_ohlcv_ccxt, generate_mock_data, sync_symbol_to_db
from backtest.engine import run_backtest, print_backtest_report

logger = get_logger("main")


def cmd_backtest(use_mock: bool = False, strategy: str | None = None, days: int | None = None):
    """运行回测"""
    d = days if days is not None else BACKTEST_DAYS
    if use_mock:
        candles = generate_mock_data(d)
    else:
        candles = fetch_ohlcv_ccxt(SYMBOL, TIMEFRAME, d)

    if not candles:
        logger.error("无法获取K线数据, 回测终止")
        sys.exit(1)

    db = Database()
    db.save_ohlcv(SYMBOL, TIMEFRAME, candles)

    result = run_backtest(candles, strategy=strategy)
    print_backtest_report(result)

    db.close()


def cmd_compare(use_mock: bool = False, days: int | None = None):
    """同一批 K 线下对比多策略 (默认真实 BTC)"""
    import logging

    d = days if days is not None else BACKTEST_DAYS
    if use_mock:
        candles = generate_mock_data(d)
    else:
        logger.info(f"拉取真实 K 线: {SYMBOL} {TIMEFRAME} 最近 {d} 天...")
        candles = fetch_ohlcv_ccxt(SYMBOL, TIMEFRAME, d)

    if not candles:
        logger.error("无法获取K线数据")
        sys.exit(1)

    order = [
        "ma_cross",
        "bb_mean_revert",
        "rsi_macd",
        "vibe",
        "ensemble",
    ]
    logging.disable(logging.CRITICAL)
    try:
        results = {name: run_backtest(candles, quiet=True, strategy=name) for name in order}
    finally:
        logging.disable(logging.NOTSET)

    print("\n" + "=" * 72)
    print(f"  策略对比  |  {SYMBOL} {TIMEFRAME}  |  {len(candles)} 根K线")
    ts0 = candles[0]["timestamp"]
    ts1 = candles[-1]["timestamp"]
    print(
        f"  区间: {datetime.fromtimestamp(ts0).strftime('%Y-%m-%d')} ~ "
        f"{datetime.fromtimestamp(ts1).strftime('%Y-%m-%d')}"
    )
    print("=" * 72)
    hdr = (
        f"  {'策略':<12} {'总收益%':>10} {'最终资产':>12} "
        f"{'胜率%':>8} {'卖出笔数':>8} {'PF':>8}"
    )
    print(hdr)
    print("  " + "-" * 68)

    def pf_str(pf: float) -> str:
        if pf == float("inf"):
            return "inf"
        return f"{pf:.2f}"

    for name in order:
        r = results.get(name) or {}
        if not r:
            print(f"  {name:<12} {'(无数据)':>10}")
            continue
        print(
            f"  {name:<12} {r.get('profit_pct', 0):>+10.2f} "
            f"{r.get('total_value', 0):>12.2f} {r.get('win_rate', 0):>8.1f} "
            f"{r.get('sell_count', 0):>8d} {pf_str(float(r.get('profit_factor', 0))):>8}"
        )
    print("=" * 72 + "\n")


def cmd_status():
    """查看账户状态"""
    db = Database()
    trades = db.get_trades(SYMBOL)
    stats = db.get_trade_stats(SYMBOL)
    balance_history = db.get_balance_history(limit=10)

    print("\n" + "=" * 50)
    print("  交易统计")
    print("=" * 50)
    print(f"  总交易次数:   {stats['total_trades']}")
    print(f"  买入次数:     {stats['buys']}")
    print(f"  卖出次数:     {stats['sells']}")
    print(f"  总手续费:     {stats['total_fees']:.4f} USDT")
    print(f"  总盈亏:       {stats['total_profit']:+.2f} USDT")
    print(f"  平均盈亏率:   {stats['avg_profit_pct']:+.2f}%")

    if trades:
        print("\n  最近交易:")
        print("  " + "-" * 46)
        for t in trades[-10:]:
            dt = datetime.fromtimestamp(t["timestamp"]).strftime("%m-%d %H:%M")
            side = "买入" if t["side"] == "buy" else "卖出"
            print(
                f"  {dt}  {side}  {t['amount']:.6f} @ {t['price']:.2f} "
                f"(手续费: {t['fee']:.4f})"
            )

    print("=" * 50 + "\n")
    db.close()


def cmd_monte_carlo(runs: int, days: int, seed_offset: int):
    """
    蒙特卡洛: 多组随机种子生成模拟 K 线, 分别回测并汇总。
    """
    import logging
    from statistics import mean, median

    if runs < 1:
        print("runs 必须 >= 1")
        sys.exit(1)

    print(
        f"\n蒙特卡洛回测: {runs} 组 | 每组 {days} 天 | "
        f"策略={STRATEGY} | 种子 {seed_offset}..{seed_offset + runs - 1}\n"
    )

    logging.disable(logging.CRITICAL)
    profit_pcts: list[float] = []
    win_rates: list[float] = []
    sell_counts: list[int] = []
    pf_list: list[float] = []

    try:
        for i in range(runs):
            seed = seed_offset + i
            candles = generate_mock_data(days, seed=seed, silent=True)
            res = run_backtest(candles, quiet=True)
            if not res:
                continue
            profit_pcts.append(float(res.get("profit_pct", 0)))
            sell_counts.append(int(res.get("sell_count", 0)))
            wr = float(res.get("win_rate", 0))
            pf = float(res.get("profit_factor", 0))
            if res.get("sell_count", 0) > 0:
                win_rates.append(wr)
                if pf != float("inf"):
                    pf_list.append(pf)
    finally:
        logging.disable(logging.NOTSET)

    with_trades = len(win_rates)
    ge75 = sum(1 for w in win_rates if w >= 75.0)
    prof_pos = sum(1 for p in profit_pcts if p > 0)

    def pctile(vals: list[float], q: float) -> float:
        if not vals:
            return float("nan")
        s = sorted(vals)
        k = (len(s) - 1) * q
        f = int(k)
        c = min(f + 1, len(s) - 1)
        if f == c:
            return s[f]
        return s[f] + (s[c] - s[f]) * (k - f)

    lines = [
        "=" * 58,
        "  蒙 特 卡 洛 汇 总",
        "=" * 58,
        f"  完成组数:           {runs}",
        f"  有平仓交易的组数:   {with_trades} "
        f"({100.0 * with_trades / runs:.1f}% 的随机行情下发生过卖出)",
        "-" * 58,
        f"  总收益率>0 的组数:  {prof_pos} ({100.0 * prof_pos / runs:.1f}%)",
        f"  胜率 ≥75% 的组数:    {ge75} / {with_trades} "
        f"({(100.0 * ge75 / with_trades) if with_trades else 0:.1f}% 含交易组)",
        "-" * 58,
        "  总收益率 % (全部组):",
        f"    均值 {mean(profit_pcts) if profit_pcts else 0:+.4f}%",
        f"    中位 {median(profit_pcts) if profit_pcts else 0:+.4f}%",
        f"    P25  {pctile(profit_pcts, 0.25):+.4f}%  P75  {pctile(profit_pcts, 0.75):+.4f}%",
        "  胜率 % (仅含已平仓组):",
        f"    均值 {mean(win_rates) if win_rates else 0:.2f}%",
        f"    中位 {median(win_rates) if win_rates else 0:.2f}%",
        f"    P25  {pctile(win_rates, 0.25):.2f}%  P75  {pctile(win_rates, 0.75):.2f}%",
        "  盈亏比 PF (已平仓组, 不含 inf):",
        f"    均值 {mean(pf_list) if pf_list else 0:.3f}",
        "=" * 58,
        "",
    ]
    print("\n".join(lines))


def cmd_optimize(use_mock: bool, days: int | None, train_ratio: float):
    """VIBE 参数网格搜索 (训练/测试切分)"""
    import logging

    d = days if days is not None else BACKTEST_DAYS
    if use_mock:
        candles = generate_mock_data(d)
    else:
        logger.info(f"拉取 K 线用于优化: {SYMBOL} {TIMEFRAME} {d} 天...")
        candles = fetch_ohlcv_ccxt(SYMBOL, TIMEFRAME, d)
    if not candles:
        logger.error("无 K 线数据")
        sys.exit(1)

    from optimization.grid_search import run_vibe_grid_search

    logging.disable(logging.CRITICAL)
    try:
        res = run_vibe_grid_search(candles, train_ratio=train_ratio, quiet=True)
    finally:
        logging.disable(logging.NOTSET)
    if res.get("error"):
        print(res["error"])
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  VIBE 网格搜索 (训练选优 → 测试验证)")
    print("=" * 60)
    print(f"  训练 K 线: {res['train_bars']}  测试 K 线: {res['test_bars']}")
    print(f"  最优参数: {res['best_params']}")
    print(f"  训练段 score(Sharpe 或收益): {res['train_score']:.4f}")
    print("  --- 训练 ---", res["train_summary"])
    print("  --- 测试 ---", res["test_summary"])
    print("=" * 60 + "\n")


def cmd_sync_ohlcv():
    """增量同步 SYMBOLS 的 K 线到 SQLite"""
    db = Database()
    print("\n增量同步 K 线 → DB")
    for sym in SYMBOLS:
        info = sync_symbol_to_db(db, sym, TIMEFRAME, days_if_empty=BACKTEST_DAYS)
        print(
            f"  {sym}: 本次写入约 {info['new_bars']} 条, "
            f"库内合计 {info['total_in_db']}, 可疑缺档 {info['gaps_found']}"
        )
    db.close()
    print()


def cmd_live_poll(use_mock: bool, once: bool, strategy: str | None, symbols_csv: str | None):
    from runtime.live_poll import run_live_polling

    syms = [s.strip() for s in symbols_csv.split(",")] if symbols_csv else None
    run_live_polling(use_mock=use_mock, once=once, strategy=strategy, symbols=syms)


def cmd_backtest_all(use_mock: bool, days: int | None, strategy: str | None):
    import logging

    d = days if days is not None else BACKTEST_DAYS
    st = strategy if strategy is not None else STRATEGY
    logging.disable(logging.CRITICAL)
    print("\n" + "=" * 72)
    print(f"  多币种回测 策略={st}  周期={TIMEFRAME}  天数={d}  mock={use_mock}")
    print("=" * 72)
    hdr = f"  {'交易对':<14} {'总收益%':>10} {'最终资产':>12} {'胜率%':>8} {'卖出':>6} {'Sharpe':>8}"
    print(hdr)
    print("  " + "-" * 68)
    try:
        for sym in SYMBOLS:
            if use_mock:
                candles = generate_mock_data(
                    d, seed=abs(hash(sym)) % (2**31), silent=True
                )
            else:
                candles = fetch_ohlcv_ccxt(sym, TIMEFRAME, d)
            if not candles:
                print(f"  {sym:<14} {'(无数据)':>10}")
                continue
            r = run_backtest(candles, quiet=True, strategy=st)
            m = r.get("metrics") or {}
            sh = m.get("sharpe", float("nan"))
            sh_s = f"{sh:.2f}" if sh == sh else "n/a"
            print(
                f"  {sym:<14} {r.get('profit_pct', 0):>+10.2f} "
                f"{r.get('total_value', 0):>12.2f} {r.get('win_rate', 0):>8.1f} "
                f"{r.get('sell_count', 0):>6d} {sh_s:>8}"
            )
    finally:
        logging.disable(logging.NOTSET)
    print("=" * 72 + "\n")


def cmd_chart(
    use_mock: bool,
    days: int | None,
    strategy: str | None,
    symbol: str | None,
    out_dir: str,
):
    import logging

    d = days if days is not None else BACKTEST_DAYS
    st = strategy if strategy is not None else STRATEGY
    sym = symbol or SYMBOL
    if use_mock:
        candles = generate_mock_data(d, seed=42)
    else:
        candles = fetch_ohlcv_ccxt(sym, TIMEFRAME, d)
    if not candles:
        logger.error("无 K 线, 无法出图")
        sys.exit(1)
    logging.disable(logging.CRITICAL)
    try:
        r = run_backtest(candles, strategy=st, include_equity_curve=True, quiet=True)
    finally:
        logging.disable(logging.NOTSET)
    if not r:
        sys.exit(1)
    from visualization.report_chart import save_report_charts

    prefix = f"{sym.replace('/', '-')}_{st}"
    paths = save_report_charts(r, candles, out_dir, prefix=prefix)
    print("\n图表已生成:")
    for p in paths:
        print(" ", p)
    print()


def cmd_list_strategies():
    """列出可用策略"""
    print("\n可用策略:")
    print("  ma_cross       — 双均线金叉/死叉")
    print("  bb_mean_revert — 布林下轨 + RSI 均值回归")
    print("  rsi_macd       — MACD + RSI + 均线过滤")
    print("  vibe           — 趋势 + 布林/RSI + ATR")
    print("  ensemble       — 多子策略投票 (见 ENSEMBLE_COMPONENTS)")
    print("\nconfig.STRATEGY 切换; compare / optimize 子命令见 --help\n")


def main():
    parser = argparse.ArgumentParser(
        description="量化交易 Bot - 模拟盘",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py backtest          # 使用真实数据回测
  python main.py backtest --mock   # 使用模拟数据回测
  python main.py status            # 查看交易状态
  python main.py strategies        # 查看可用策略
  python main.py monte-carlo --runs 10000   # 一万组模拟行情压力测试
  python main.py compare                    # 真实 BTC 多策略对比
  python main.py compare --mock             # 模拟数据对比
  python main.py optimize --mock            # VIBE 网格搜索 (训练/测试)
  python main.py sync                       # 多币种增量同步 K 线到数据库
  python main.py live --mock --once         # 模拟一轮信号轮询
  python main.py backtest-all --mock       # 多币种批量回测
  python main.py chart --mock              # 权益/回撤/月度图 → reports/
        """,
    )
    subparsers = parser.add_subparsers(dest="command")

    # backtest 命令
    bt_parser = subparsers.add_parser("backtest", help="运行策略回测")
    bt_parser.add_argument(
        "--mock", action="store_true", help="使用模拟数据 (无需网络)"
    )
    bt_parser.add_argument(
        "--strategy",
        default=None,
        help="策略名: ma_cross | bb_mean_revert | rsi_macd | vibe | ensemble",
    )
    bt_parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"回测天数 (默认 {BACKTEST_DAYS})",
    )

    cmp_parser = subparsers.add_parser(
        "compare",
        help="同一批K线多策略对比 (含 ensemble / 布林等)",
    )
    cmp_parser.add_argument("--mock", action="store_true", help="使用模拟数据")
    cmp_parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"天数 (默认 {BACKTEST_DAYS})",
    )

    opt_parser = subparsers.add_parser(
        "optimize",
        help="VIBE 策略网格搜索 (70%% 训练选 Sharpe, 30%% 样本外测试)",
    )
    opt_parser.add_argument("--mock", action="store_true", help="模拟数据")
    opt_parser.add_argument("--days", type=int, default=None, help="K 线天数")
    opt_parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="训练集占比 (默认 0.7)",
    )

    subparsers.add_parser("sync", help="增量同步 config.SYMBOLS 的 K 线到 SQLite")

    live_parser = subparsers.add_parser(
        "live",
        help="REST 轮询最新 K 线并推送信号 (飞书/Webhook, 不下单)",
    )
    live_parser.add_argument("--mock", action="store_true", help="模拟行情")
    live_parser.add_argument(
        "--once",
        action="store_true",
        help="只跑一轮后退出 (调试)",
    )
    live_parser.add_argument("--strategy", default=None, help="覆盖 STRATEGY")
    live_parser.add_argument(
        "--symbols",
        default=None,
        help="逗号分隔交易对, 默认 SYMBOLS",
    )

    ba_parser = subparsers.add_parser(
        "backtest-all",
        help="对 SYMBOLS 逐个回测并汇总",
    )
    ba_parser.add_argument("--mock", action="store_true")
    ba_parser.add_argument("--days", type=int, default=None)
    ba_parser.add_argument("--strategy", default=None)

    ch_parser = subparsers.add_parser(
        "chart",
        help="回测并导出权益/回撤/月度收益图 (需 matplotlib)",
    )
    ch_parser.add_argument("--mock", action="store_true")
    ch_parser.add_argument("--days", type=int, default=None)
    ch_parser.add_argument("--strategy", default=None)
    ch_parser.add_argument("--symbol", default=None, help=f"默认 {SYMBOL}")
    ch_parser.add_argument(
        "--output-dir",
        default=REPORTS_DIR,
        help=f"输出目录 (默认 {REPORTS_DIR})",
    )

    # status 命令
    subparsers.add_parser("status", help="查看交易状态")

    # strategies 命令
    subparsers.add_parser("strategies", help="列出可用策略")

    mc_parser = subparsers.add_parser(
        "monte-carlo",
        help="蒙特卡洛: 多组随机模拟 K 线分别回测并汇总",
    )
    mc_parser.add_argument(
        "--runs",
        type=int,
        default=10000,
        help="随机行情组数 (默认 10000)",
    )
    mc_parser.add_argument(
        "--days",
        type=int,
        default=BACKTEST_DAYS,
        help=f"每组模拟天数 (默认 {BACKTEST_DAYS})",
    )
    mc_parser.add_argument(
        "--seed-offset",
        type=int,
        default=0,
        help="种子起始偏移, 第 i 组种子 = seed-offset + i",
    )

    args = parser.parse_args()

    if args.command == "backtest":
        cmd_backtest(
            use_mock=args.mock,
            strategy=args.strategy,
            days=getattr(args, "days", None),
        )
    elif args.command == "compare":
        cmd_compare(use_mock=args.mock, days=args.days)
    elif args.command == "optimize":
        cmd_optimize(
            use_mock=args.mock,
            days=args.days,
            train_ratio=args.train_ratio,
        )
    elif args.command == "sync":
        cmd_sync_ohlcv()
    elif args.command == "live":
        cmd_live_poll(
            use_mock=args.mock,
            once=args.once,
            strategy=args.strategy,
            symbols_csv=args.symbols,
        )
    elif args.command == "backtest-all":
        cmd_backtest_all(
            use_mock=args.mock,
            days=args.days,
            strategy=args.strategy,
        )
    elif args.command == "chart":
        cmd_chart(
            use_mock=args.mock,
            days=args.days,
            strategy=args.strategy,
            symbol=args.symbol,
            out_dir=args.output_dir,
        )
    elif args.command == "monte-carlo":
        cmd_monte_carlo(
            runs=args.runs,
            days=args.days,
            seed_offset=args.seed_offset,
        )
    elif args.command == "status":
        cmd_status()
    elif args.command == "strategies":
        cmd_list_strategies()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
