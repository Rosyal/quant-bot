"""
量化交易 Bot - 主入口
"""
from __future__ import annotations

import argparse
import json
import os
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
from data_fetcher import fetch_ohlcv, generate_mock_data, sync_symbol_to_db
from backtest.engine import run_backtest, print_backtest_report

logger = get_logger("main")

_PROFILE_ARG_HELP = (
    "风险预设: stability=压低单笔仓位+收紧回撤熔断 (见 runtime/presets.py); "
    "不保证盈利。未指定 --strategy 时 stability 默认策略见预设说明。"
)


def _profile_overrides_and_strategy(
    profile: str | None, strategy: str | None
) -> tuple[dict | None, str | None]:
    """
    返回 (config_overrides, effective_strategy)。
    指定 profile 且未指定 strategy 时, 可能采用预设默认策略 (如 stability→ensemble_strict)。
    """
    from runtime.presets import default_strategy_for_profile, get_profile_overrides

    if not profile or not str(profile).strip():
        return None, strategy
    try:
        ov = get_profile_overrides(profile)
    except ValueError as e:
        logger.error(str(e))
        raise SystemExit(1) from e
    strat = strategy
    if strat is None:
        d = default_strategy_for_profile(profile)
        if d:
            strat = d
    return ov, strat


def _parse_strategies_csv(csv_str: str | None) -> list[str]:
    """逗号分隔策略名 → 列表; 空则使用 COMPARE_STRATEGY_ORDER。"""
    from strategy import COMPARE_STRATEGY_ORDER, STRATEGY_REGISTRY

    if not csv_str or not str(csv_str).strip():
        return list(COMPARE_STRATEGY_ORDER)
    out: list[str] = []
    for part in str(csv_str).split(","):
        n = part.strip().lower()
        if not n:
            continue
        if n not in STRATEGY_REGISTRY:
            logger.error(
                f"未知策略: {n!r}, 可选: {', '.join(sorted(STRATEGY_REGISTRY))}"
            )
            sys.exit(1)
        out.append(n)
    return out


def _export_trades_csv(path: str, trades: list) -> None:
    import csv
    import os

    if not trades:
        logger.warning("无成交记录, 跳过导出")
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fields = ["symbol", "side", "price", "amount", "fee", "total", "timestamp", "strategy"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for t in trades:
            w.writerow({k: t.get(k, "") for k in fields})
    logger.info(f"已导出成交 CSV: {path}")


def cmd_backtest(
    use_mock: bool = False,
    strategy: str | None = None,
    days: int | None = None,
    profile: str | None = None,
    export_trades: str | None = None,
):
    """运行回测"""
    ov, strat = _profile_overrides_and_strategy(profile, strategy)
    d = days if days is not None else BACKTEST_DAYS
    if use_mock:
        candles = generate_mock_data(d)
    else:
        candles = fetch_ohlcv(SYMBOL, TIMEFRAME, d)

    if not candles:
        logger.error("无法获取K线数据, 回测终止")
        sys.exit(1)

    db = Database()
    db.save_ohlcv(SYMBOL, TIMEFRAME, candles)

    if profile and ov:
        logger.info(f"已启用预设 {profile!r}: 低仓位/紧回撤 (不保证盈利)")

    result = run_backtest(
        candles,
        strategy=strat,
        config_overrides=ov,
        include_trades=bool(export_trades),
    )
    print_backtest_report(result)
    if export_trades:
        _export_trades_csv(export_trades, result.get("trades", []))

    db.close()


def cmd_product_brief(
    use_mock: bool,
    days: int | None,
    strategy: str | None,
    profile: str | None,
    as_json: bool,
    *,
    compact_json: bool,
    strategies_csv: str | None,
    walk_forward: bool,
    train_bars: int,
    test_bars: int,
    step: int | None,
    pdf_path: str | None,
):
    """
    生成「产品向」执行摘要 / 完整证据包（含治理三层、多样本外、多策略；非收益承诺）。
    """
    from deliverables.dossier import dossier_to_json, format_dossier_text
    from deliverables.executive_brief import brief_to_json, build_brief, format_brief_text
    from deliverables.pdf_export import write_dossier_pdf
    from deliverables.runner import build_dossier_pipeline

    if compact_json and (strategies_csv or walk_forward or pdf_path):
        logger.error("--compact-json 不能与 --strategies / --walk-forward / --pdf 同时使用")
        sys.exit(1)

    if compact_json:
        ov, strat = _profile_overrides_and_strategy(profile, strategy)
        d = days if days is not None else BACKTEST_DAYS
        st = strat if strat is not None else (strategy if strategy is not None else STRATEGY)
        if use_mock:
            candles = generate_mock_data(d)
        else:
            candles = fetch_ohlcv(SYMBOL, TIMEFRAME, d)
        if not candles:
            logger.error("无法获取K线数据, 终止")
            sys.exit(1)
        result = run_backtest(candles, quiet=True, strategy=st, config_overrides=ov)
        if not result:
            logger.error("回测无有效结果")
            sys.exit(1)
        brief = build_brief(result, symbol=SYMBOL, timeframe=TIMEFRAME)
        print(brief_to_json(brief) if as_json else format_brief_text(brief))
        return

    dossier = build_dossier_pipeline(
        use_mock=use_mock,
        days=days,
        strategy=strategy,
        profile=profile,
        strategies_csv=strategies_csv,
        walk_forward=walk_forward,
        train_bars=train_bars,
        test_bars=test_bars,
        step=step,
    )
    if dossier.get("error"):
        logger.error(dossier.get("message", dossier.get("error")))
        sys.exit(1)

    if pdf_path:
        try:
            write_dossier_pdf(pdf_path, dossier)
            logger.info(f"已写入 PDF: {pdf_path}")
        except RuntimeError as e:
            logger.error(str(e))
            sys.exit(1)

    if as_json:
        print(dossier_to_json(dossier))
    if not as_json:
        print(format_dossier_text(dossier))


def _parse_sensitivity_values(csv_str: str) -> list:
    out: list = []
    for part in csv_str.split(","):
        p = part.strip()
        if not p:
            continue
        out.append(float(p) if "." in p else int(p))
    return out


def cmd_sensitivity(
    use_mock: bool,
    days: int | None,
    strategy: str | None,
    param: str,
    values_csv: str,
    profile: str | None,
):
    """单参数扫描 (市面平台常见敏感性分析简化版)"""
    from research.sensitivity import run_parameter_sensitivity

    ov, strat = _profile_overrides_and_strategy(profile, strategy)
    d = days if days is not None else BACKTEST_DAYS
    candles = generate_mock_data(d) if use_mock else fetch_ohlcv(SYMBOL, TIMEFRAME, d)
    if not candles:
        logger.error("无 K 线")
        sys.exit(1)
    vals = _parse_sensitivity_values(values_csv)
    if not vals:
        logger.error("请提供 --values 如 20,25,30,35")
        sys.exit(1)
    rows = run_parameter_sensitivity(
        candles,
        strategy=strat or STRATEGY,
        param_name=param.strip(),
        values=vals,
        base_overrides=ov,
    )
    print("\n参数敏感性 (固定 K 线)\n")
    print(f"  strategy={strat or STRATEGY}  param={param}")
    for row in rows:
        print(
            f"  {row['param_value']!r}: 收益%={row['profit_pct']!s}  "
            f"Sharpe={row['sharpe']!s}  MDD%={row['max_dd_pct']!s}"
        )
    print()


def cmd_regime_report(use_mock: bool, days: int | None):
    """标的波动率 regime 占比 (滚动波动率分位)"""
    from research.regime import regime_summary

    d = days if days is not None else BACKTEST_DAYS
    candles = generate_mock_data(d) if use_mock else fetch_ohlcv(SYMBOL, TIMEFRAME, d)
    if not candles:
        sys.exit(1)
    closes = [float(c["close"]) for c in candles]
    s = regime_summary(closes, window=20, quantile=0.7)
    print("\n波动率 Regime (高波动 = 滚动波动率 ≥ 70% 分位)\n")
    print(f"  有效 K 线: {int(s['bars_labeled'])}")
    print(f"  高波动根数: {int(s['high_vol_bars'])} ({s['high_vol_pct']:.1f}%)\n")


def cmd_stress_scenario(
    use_mock: bool,
    days: int | None,
    strategy: str | None,
    shock_pct: float,
    profile: str | None,
):
    """最深回撤点起施加一次性权益冲击 (缺口情景)"""
    from research.stress import apply_equity_shock_from_bar

    ov, strat = _profile_overrides_and_strategy(profile, strategy)
    d = days if days is not None else BACKTEST_DAYS
    candles = generate_mock_data(d) if use_mock else fetch_ohlcv(SYMBOL, TIMEFRAME, d)
    if not candles:
        sys.exit(1)
    r = run_backtest(
        candles,
        quiet=True,
        strategy=strat,
        config_overrides=ov,
        include_equity_curve=True,
    )
    eq = r.get("equity_curve") or []
    if len(eq) < 5:
        print("权益曲线过短")
        sys.exit(1)
    shocked, bar = apply_equity_shock_from_bar(eq, shock_pct)
    print("\n压力情景 (自最深回撤点起权益 × (1+冲击))\n")
    print(f"  冲击: {shock_pct*100:+.2f}%  起始 bar: {bar}")
    print(f"  原最终权益: {eq[-1]:.2f} USDT")
    print(f"  情景最终权益: {shocked[-1]:.2f} USDT\n")


def cmd_compare(
    use_mock: bool = False,
    days: int | None = None,
    symbol: str | None = None,
    strategies_csv: str | None = None,
    profile: str | None = None,
):
    """同一批 K 线下对比多策略 (默认真实 BTC / 可选品种与子集策略)"""
    import logging

    from runtime.presets import get_profile_overrides

    ov = None
    if profile:
        try:
            ov = get_profile_overrides(profile)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)
        logger.info(f"对比已套用预设 {profile!r} (仓位/风控覆盖)")

    sym = symbol or SYMBOL
    order = _parse_strategies_csv(strategies_csv)
    d = days if days is not None else BACKTEST_DAYS
    if use_mock:
        candles = generate_mock_data(
            d, seed=abs(hash(sym)) % (2**31), silent=True
        )
    else:
        logger.info(f"拉取真实 K 线: {sym} {TIMEFRAME} 最近 {d} 天...")
        candles = fetch_ohlcv(sym, TIMEFRAME, d)

    if not candles:
        logger.error("无法获取K线数据")
        sys.exit(1)

    logging.disable(logging.CRITICAL)
    try:
        results = {
            name: run_backtest(
                candles, quiet=True, strategy=name, config_overrides=ov
            )
            for name in order
        }
    finally:
        logging.disable(logging.NOTSET)

    print("\n" + "=" * 72)
    print(f"  策略对比  |  {sym} {TIMEFRAME}  |  {len(candles)} 根K线")
    ts0 = candles[0]["timestamp"]
    ts1 = candles[-1]["timestamp"]
    print(
        f"  区间: {datetime.fromtimestamp(ts0).strftime('%Y-%m-%d')} ~ "
        f"{datetime.fromtimestamp(ts1).strftime('%Y-%m-%d')}"
    )
    print("=" * 72)
    hdr = (
        f"  {'策略':<12} {'总收益%':>10} {'最终资产':>12} "
        f"{'胜率%':>8} {'卖出':>6} {'Sharpe':>8} {'回撤%':>8} {'PF':>8}"
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
        m = r.get("metrics") or {}
        sh = m.get("sharpe", float("nan"))
        mdd = m.get("max_drawdown_pct", float("nan"))
        sh_s = f"{sh:.2f}" if sh == sh else "n/a"
        mdd_s = f"{mdd:.2f}" if mdd == mdd else "n/a"
        print(
            f"  {name:<12} {r.get('profit_pct', 0):>+10.2f} "
            f"{r.get('total_value', 0):>12.2f} {r.get('win_rate', 0):>8.1f} "
            f"{r.get('sell_count', 0):>6d} {sh_s:>8} {mdd_s:>8} "
            f"{pf_str(float(r.get('profit_factor', 0))):>8}"
        )
    print("=" * 72 + "\n")


def cmd_compare_matrix(
    use_mock: bool = False,
    days: int | None = None,
    symbols_csv: str | None = None,
    strategies_csv: str | None = None,
    profile: str | None = None,
):
    """对每个交易对分别拉 K 线, 再跑多策略回测 (矩阵批量测试)。"""
    import logging

    from runtime.presets import get_profile_overrides

    ov = None
    if profile:
        try:
            ov = get_profile_overrides(profile)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    d = days if days is not None else BACKTEST_DAYS
    syms = (
        [s.strip() for s in symbols_csv.split(",") if s.strip()]
        if symbols_csv
        else list(SYMBOLS)
    )
    order = _parse_strategies_csv(strategies_csv)

    print("\n" + "=" * 80)
    print(
        f"  策略矩阵测试  |  {TIMEFRAME}  |  {d} 天  |  mock={use_mock}  |  "
        f"{len(syms)} 品种 × {len(order)} 策略"
    )
    print("=" * 80)

    logging.disable(logging.CRITICAL)
    try:
        for sym in syms:
            if use_mock:
                candles = generate_mock_data(
                    d, seed=abs(hash(sym)) % (2**31), silent=True
                )
            else:
                candles = fetch_ohlcv(sym, TIMEFRAME, d)
            if not candles:
                print(f"\n  [{sym}] 无 K 线数据, 跳过\n")
                continue

            ts0 = datetime.fromtimestamp(candles[0]["timestamp"]).strftime("%Y-%m-%d")
            ts1 = datetime.fromtimestamp(candles[-1]["timestamp"]).strftime("%Y-%m-%d")
            print(f"\n  --- {sym}  |  {len(candles)} 根  |  {ts0} ~ {ts1} ---")
            hdr = (
                f"  {'策略':<14} {'总收益%':>10} {'最终资产':>12} "
                f"{'胜率%':>8} {'卖出':>6} {'Sharpe':>8} {'回撤%':>8} {'PF':>8}"
            )
            print(hdr)
            print("  " + "-" * 76)

            def pf_str(pf: float) -> str:
                if pf == float("inf"):
                    return "inf"
                return f"{pf:.2f}"

            for name in order:
                r = run_backtest(
                    candles, quiet=True, strategy=name, config_overrides=ov
                )
                if not r:
                    print(f"  {name:<14} {'(数据不足)':>10}")
                    continue
                m = r.get("metrics") or {}
                sh = m.get("sharpe", float("nan"))
                mdd = m.get("max_drawdown_pct", float("nan"))
                sh_s = f"{sh:.2f}" if sh == sh else "n/a"
                mdd_s = f"{mdd:.2f}" if mdd == mdd else "n/a"
                print(
                    f"  {name:<14} {r.get('profit_pct', 0):>+10.2f} "
                    f"{r.get('total_value', 0):>12.2f} {r.get('win_rate', 0):>8.1f} "
                    f"{r.get('sell_count', 0):>6d} {sh_s:>8} {mdd_s:>8} "
                    f"{pf_str(float(r.get('profit_factor', 0))):>8}"
                )
    finally:
        logging.disable(logging.NOTSET)

    print("\n" + "=" * 80 + "\n")


def cmd_coupled_test(
    runs: int,
    days: int | None,
    use_mock: bool,
    mode: str | None,
    symbol: str | None,
    strategies_csv: str | None,
    seed_offset: int,
    sort_by: str,
    win_round_target: float | None,
    profile: str | None,
):
    """
    多次耦合: 每轮内多策略共享同一批 K 线; mock-seeds 为多组随机行情,
    walk-forward 为时间分窗。
    """
    import logging

    from runtime.coupled_test import print_coupled_report, run_coupled_test
    from runtime.presets import get_profile_overrides

    ov = None
    if profile:
        try:
            ov = get_profile_overrides(profile)
            logger.info(f"耦合测试套用预设 {profile!r} (仓位/风控)")
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    if runs < 1:
        print("runs 必须 >= 1")
        sys.exit(1)

    d = days if days is not None else BACKTEST_DAYS
    strategies = _parse_strategies_csv(strategies_csv)
    sym = symbol or SYMBOL

    eff_mode = (mode or "").strip().lower().replace("_", "-")
    if not eff_mode:
        eff_mode = "mock-seeds" if use_mock else "walk-forward"
    if eff_mode not in ("mock-seeds", "walk-forward"):
        logger.error("mode 须为 mock-seeds 或 walk-forward")
        sys.exit(1)
    if eff_mode == "mock-seeds" and not use_mock:
        logger.error("mock-seeds 模式必须加 --mock (每轮独立模拟行情)")
        sys.exit(1)

    logging.disable(logging.CRITICAL)
    try:
        result = run_coupled_test(
            runs=runs,
            days=d,
            mode=eff_mode,
            symbol=sym,
            strategies=strategies,
            seed_offset=seed_offset,
            use_mock=use_mock,
            config_overrides=ov,
        )
    finally:
        logging.disable(logging.NOTSET)

    print_coupled_report(
        result,
        sort_by=sort_by,
        win_round_ratio_target=win_round_target,
    )
    if not result.get("ok"):
        sys.exit(1)


def cmd_rank_models(
    scope: str,
    runs: int,
    days: int | None,
    use_mock: bool,
    coupled_mode: str | None,
    symbol: str | None,
    strategies_csv: str | None,
    seed_offset: int,
    min_profit_round_rate: float | None,
    profile: str | None,
):
    """
    按 config 权重对「收益/夏普/回撤/盈利轮」打综合分并排序。
    仅历史筛选工具, 排名第一不代表未来最高收益。
    """
    import logging
    import math

    from optimization.composite_score import (
        composite_score_from_backtest,
        composite_score_row,
        load_rank_weights,
    )
    from runtime.coupled_test import run_coupled_test
    from runtime.presets import get_profile_overrides

    ov = None
    if profile:
        try:
            ov = get_profile_overrides(profile)
            logger.info(f"排名套用预设 {profile!r} (仓位/风控)")
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    d = days if days is not None else BACKTEST_DAYS
    strategies = _parse_strategies_csv(strategies_csv)
    sym = symbol or SYMBOL
    w = load_rank_weights()
    w_kwargs = {
        "w_profit": w["w_profit"],
        "w_sharpe": w["w_sharpe"],
        "w_mdd": w["w_mdd"],
        "w_winround": w["w_winround"],
    }

    logging.disable(logging.CRITICAL)
    rows: list[tuple[float, str, dict]] = []
    try:
        if scope == "coupled":
            eff_cm = (coupled_mode or "").strip().lower().replace("_", "-")
            if not eff_cm:
                eff_cm = "mock-seeds" if use_mock else "walk-forward"
            if eff_cm == "mock-seeds" and not use_mock:
                logger.error("综合排名 coupled + mock-seeds 需要 --mock")
                sys.exit(1)
            result = run_coupled_test(
                runs=runs,
                days=d,
                mode=eff_cm,
                symbol=sym,
                strategies=strategies,
                seed_offset=seed_offset,
                use_mock=use_mock,
                config_overrides=ov,
            )
            if not result.get("ok"):
                print(result.get("error", "耦合测试失败"))
                sys.exit(1)
            for st, agg in result["aggregate"].items():
                sc = composite_score_row(agg, **w_kwargs)
                rows.append((sc, st, agg))
            subtitle = (
                f"scope=coupled  {result.get('detail_mode', '')}  "
                f"有效轮数={result.get('runs_effective')}"
                f"{f'  preset={profile}' if profile else ''}"
            )
        else:
            if use_mock:
                candles = generate_mock_data(
                    d, seed=abs(hash(sym)) % (2**31), silent=True
                )
            else:
                candles = fetch_ohlcv(sym, TIMEFRAME, d)
            if not candles:
                logger.error("无法获取 K 线")
                sys.exit(1)
            for st in strategies:
                r = run_backtest(
                    candles, quiet=True, strategy=st, config_overrides=ov
                )
                if not r:
                    continue
                sc = composite_score_from_backtest(r, **w_kwargs)
                m = r.get("metrics") or {}
                sh = m.get("sharpe", float("nan"))
                mdd = m.get("max_drawdown_pct", float("nan"))
                agg = {
                    "n": 1,
                    "profit_pct_mean": float(r.get("profit_pct", 0)),
                    "profit_pct_std": 0.0,
                    "profit_win_rate": 1.0 if r.get("profit_pct", 0) > 0 else 0.0,
                    "sharpe_mean": float(sh) if sh == sh else float("nan"),
                    "sharpe_std": 0.0,
                    "mdd_mean": float(mdd) if mdd == mdd else float("nan"),
                    "sells_mean": float(r.get("sell_count", 0)),
                }
                rows.append((sc, st, agg))
            subtitle = (
                f"scope=single  单段K线  {sym}  {len(candles)} 根"
                f"{f'  preset={profile}' if profile else ''}"
            )
    finally:
        logging.disable(logging.NOTSET)

    rows.sort(key=lambda x: x[0], reverse=True)

    gate_line = ""
    if min_profit_round_rate is not None:
        mr = float(min_profit_round_rate)
        if not (0.0 <= mr <= 1.0):
            logger.error("min-profit-round-rate 须在 0~1 之间 (如 0.65 表示 65%)")
            sys.exit(1)
        filtered = [
            (sc, st, a)
            for sc, st, a in rows
            if float(a.get("profit_win_rate", 0)) >= mr
        ]
        if not filtered:
            print(
                f"\n无策略满足「盈利轮占比」≥ {100 * mr:.0f}% "
                f"(scope={scope}). 可增大 --runs、换策略、改用 ensemble_strict，或降低门槛。\n"
            )
            sys.exit(2)
        rows = filtered
        gate_line = f"  门槛: 仅显示盈利轮占比 ≥ {100 * mr:.0f}% 的策略"

    print("\n" + "=" * 88)
    print("  综合分排名 (历史/样本内, 不保证未来收益)")
    print(f"  权重: 收益={w['w_profit']:.2f} 夏普={w['w_sharpe']:.2f} "
          f"回撤={w['w_mdd']:.2f} 盈利轮={w['w_winround']:.2f}  → 可调 config.RANK_COMPOSITE_W_*")
    print(f"  {subtitle}")
    if gate_line:
        print(gate_line)
    print("=" * 88)
    hdr = (
        f"  {'排名':>4} {'策略':<14} {'综合分':>10} {'N':>4} {'收益均值%':>12} "
        f"{'盈利轮%':>10} {'夏普均值':>10} {'回撤均值%':>10}"
    )
    print(hdr)
    print("  " + "-" * 84)
    for i, (sc, st, a) in enumerate(rows, start=1):
        if a.get("n", 0) <= 0:
            continue
        sm = a["sharpe_mean"]
        sm_s = f"{sm:>10.2f}" if not math.isnan(sm) else f"{'n/a':>10}"
        mdd_m = a["mdd_mean"]
        mdd_s = f"{mdd_m:>10.2f}" if not math.isnan(mdd_m) else f"{'n/a':>10}"
        print(
            f"  {i:>4} {st:<14} {sc:>10.4f} {a['n']:>4} "
            f"{a['profit_pct_mean']:>+12.2f} {100 * a['profit_win_rate']:>9.1f}% "
            f"{sm_s} {mdd_s}"
        )
    print("=" * 88)
    if rows:
        best = rows[0][1]
        print(
            f"  当前样本内综合分最高: {best} "
            f"(请样本外/小资金验证; 勿等同于「最赚钱实盘模型」)\n"
        )
    else:
        print()


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


def cmd_monte_carlo(
    runs: int, days: int, seed_offset: int, profile: str | None = None
):
    """
    蒙特卡洛: 多组随机种子生成模拟 K 线, 分别回测并汇总。
    """
    import logging
    from statistics import mean, median

    from runtime.presets import get_profile_overrides

    ov = None
    if profile:
        try:
            ov = get_profile_overrides(profile)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    if runs < 1:
        print("runs 必须 >= 1")
        sys.exit(1)

    print(
        f"\n蒙特卡洛回测: {runs} 组 | 每组 {days} 天 | "
        f"策略={STRATEGY} | 种子 {seed_offset}..{seed_offset + runs - 1}"
        f"{f' | preset={profile}' if profile else ''}\n"
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
            res = run_backtest(candles, quiet=True, config_overrides=ov)
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
        candles = fetch_ohlcv(SYMBOL, TIMEFRAME, d)
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


def cmd_walk_forward(
    use_mock: bool,
    days: int | None,
    strategy: str | None,
    train_bars: int,
    test_bars: int,
    step: int | None,
    profile: str | None,
):
    """滚动样本外: 固定参数下多段 OOS 表现 (非未来保证)"""
    from backtest.walk_forward import format_walk_forward_report, run_walk_forward

    ov, strat = _profile_overrides_and_strategy(profile, strategy)
    d = days if days is not None else BACKTEST_DAYS
    if use_mock:
        candles = generate_mock_data(d)
    else:
        logger.info(f"Walk-forward: {SYMBOL} {TIMEFRAME}, 约 {d} 天...")
        candles = fetch_ohlcv(SYMBOL, TIMEFRAME, d)
    if not candles:
        logger.error("无 K 线数据")
        sys.exit(1)

    wf = run_walk_forward(
        candles,
        strategy=strat,
        train_bars=train_bars,
        test_bars=test_bars,
        step=step,
        config_overrides=ov,
    )
    print(format_walk_forward_report(wf))
    if wf.get("error"):
        sys.exit(1)


def cmd_audit_log(limit: int):
    """列出审计事件 (SQLite)"""
    db = Database()
    try:
        rows = db.list_audit_events(limit)
    finally:
        db.close()
    if not rows:
        print("(无审计记录; router-dry-run 会写入)")
        return
    for r in rows:
        print(
            f"[{r['id']}] ts={r['ts']} actor={r['actor']} action={r['action']} "
            f"outcome={r['outcome']} latency_ms={r['latency_ms']}"
        )
        if r.get("resource"):
            print(f"    resource={r['resource']}")
        if r.get("payload_json"):
            p = str(r["payload_json"])
            print(f"    payload={p[:240]}{'...' if len(p) > 240 else ''}")


def cmd_portfolio_opt(method: str, mock: bool, limit: int):
    """多资产静态组合权重 (风险平价 / 最小方差)"""
    import numpy as np

    from factors.cross_section import load_close_panel_from_db
    from portfolio.optimizer import optimize_from_price_panel

    if mock:
        rng = np.random.default_rng(42)
        t_n, n_assets = 400, max(3, len(SYMBOLS))
        noise = rng.normal(0, 0.015, (t_n, n_assets))
        closes = 100.0 * np.cumprod(1.0 + noise, axis=0)
        names = [f"M{n}" for n in range(n_assets)]
    else:
        db = Database()
        try:
            _ts, panel = load_close_panel_from_db(db, SYMBOLS, TIMEFRAME, limit)
        finally:
            db.close()
        if len(panel) < 2:
            logger.error("DB 重叠 K 线不足; 请先 sync 或使用 --mock")
            sys.exit(1)
        names = sorted(panel.keys())
        closes = np.column_stack([panel[s] for s in names])
    w, cov = optimize_from_price_panel(closes, method=method)
    vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
    print("\n组合优化 (历史样本, 非投资建议)\n")
    print(f"  method={method}  资产数={len(names)}")
    for sym, wt in zip(names, w):
        print(f"    {sym}: {wt * 100:.2f}%")
    print(f"  逐步收益波动估计 √(w'Σw): {vol * 100:.4f}%\n")


def cmd_factors_xsec(limit: int, symbols_csv: str | None):
    """多品种横截面因子 z-score"""
    from factors.cross_section import load_close_panel_from_db, snapshot_factors

    syms = (
        [s.strip() for s in symbols_csv.split(",") if s.strip()]
        if symbols_csv
        else list(SYMBOLS)
    )
    db = Database()
    try:
        _ts, panel = load_close_panel_from_db(db, syms, TIMEFRAME, limit)
    finally:
        db.close()
    if len(panel) < 2:
        logger.error("至少需两个品种且有对齐 K 线")
        sys.exit(1)
    mom, vol, zm, zv = snapshot_factors(panel)
    print("\n横截面因子 (末根对齐)\n")
    for s in sorted(panel.keys()):
        m = mom.get(s, float("nan"))
        v = vol.get(s, float("nan"))
        print(
            f"  {s}: mom={(m * 100):+.3f}%  vol={(v * 100):.3f}%  "
            f"z_mom={zm.get(s, 0):+.2f}  z_vol={zv.get(s, 0):+.2f}"
        )
    print()


def cmd_router_dry_run(
    symbol: str,
    side: str,
    notional: float,
    mid: float,
    role: str | None,
):
    """执行路由演练: 权限 + 合规 + 冲击模型 + 审计"""
    from routing.execution_router import ExecutionRouter
    from security.permissions import default_role_from_env

    db = Database()
    try:
        router = ExecutionRouter(db=db, role=role or default_role_from_env())
        out = router.dry_run_market_order(
            symbol=symbol,
            side=side,
            notional_usdt=notional,
            mid=mid,
            actor="cli",
        )
    finally:
        db.close()
    print(f"ok={out.ok} backend={out.backend} latency_ms={out.latency_ms:.3f}")
    print(f"reason={out.reason}")
    print(f"effective_price={out.effective_price}")
    print(f"detail={json.dumps(out.detail, ensure_ascii=False)}")


def cmd_oms_submit(
    symbol: str,
    side: str,
    notional: float,
    mid: float,
    force: bool,
    approval_id: int | None,
    gross: float,
    equity: float,
    sym_nv: float,
):
    """全链路: RBAC → 中台规则 → 审批 → 路由/审计 → EMS"""
    cmd_desk_pipeline(
        symbol=symbol,
        side=side,
        notional=notional,
        mid=mid,
        force=force,
        approval_id=approval_id,
        gross=gross,
        equity=equity,
        sym_nv=sym_nv,
        no_ems=False,
    )


def cmd_desk_pipeline(
    symbol: str,
    side: str,
    notional: float,
    mid: float,
    force: bool,
    approval_id: int | None,
    gross: float,
    equity: float,
    sym_nv: float,
    no_ems: bool,
):
    from desk.pipeline import (
        PipelineContext,
        pipeline_stages_to_text,
        run_order_pipeline,
    )
    from security.permissions import default_role_from_env

    db = Database()
    try:
        ctx = PipelineContext(
            symbol=symbol,
            side=side,
            notional_usdt=notional,
            mid=mid,
            actor="cli",
            role=default_role_from_env(),
            force=force,
            approval_id=approval_id,
            gross_exposure_usd=gross,
            equity_usdt=equity,
            symbol_notional_usd=sym_nv,
        )
        pr = run_order_pipeline(ctx, db, run_ems=not no_ems)
        print("\n交易台全链路\n")
        print(pipeline_stages_to_text(pr.stages))
        print(f"\nok={pr.ok}  {pr.message}")
        if pr.client_order_id:
            print(f"  client_order_id: {pr.client_order_id}")
        if pr.router:
            print(f"  router: {pr.router.reason} px={pr.router.effective_price}")
        if pr.ems is not None:
            er = pr.ems
            print(
                f"  ems: {er.status} ch={er.channel} px={er.avg_px} "
                f"lat_ns={er.latency_ns}"
            )
        print()
        if not pr.ok:
            sys.exit(2)
    finally:
        db.close()


def cmd_exposure_report(price_map: str | None, mock: bool):
    """中台: 净敞口 + 简化保证金 (读纸面 JSON 或 --mock)"""
    import config as cfg

    from config import PAPER_LIVE_STATE_PATH
    from middle_office.exposure import (
        gross_exposure_usd,
        load_exposure_from_paper_state,
        notionals_from_positions,
    )
    from middle_office.margin import margin_status

    marks: dict[str, float] = {}
    if price_map:
        for part in price_map.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                marks[k.strip()] = float(v.strip())
    if mock:
        st = {"usdt": 10000.0, "positions": {"BTC/USDT": 0.02, "ETH/USDT": 0.5}}
    else:
        import os

        if not os.path.isfile(PAPER_LIVE_STATE_PATH):
            st = {"usdt": 0.0, "positions": {}}
        else:
            with open(PAPER_LIVE_STATE_PATH, encoding="utf-8") as f:
                st = json.load(f)
    snap = load_exposure_from_paper_state(st, marks)
    notion = notionals_from_positions(snap)
    gross = gross_exposure_usd(notion)
    equity = snap.cash_usdt + sum(notion.values())
    ms = margin_status(
        equity,
        gross,
        initial_rate=float(cfg.MARGIN_INITIAL_RATE),
        maintenance_rate=float(cfg.MARGIN_MAINTENANCE_RATE),
    )
    print("\n中台敞口 / 保证金 (现货多头近似)\n")
    print(f"  现金 USDT: {snap.cash_usdt:.2f}")
    for s, q in snap.positions_qty.items():
        print(f"  持仓 {s}: {q}  标记价={marks.get(s, 0) or '未提供'}")
    print(f"  毛名义 USD: {gross:.2f}  权益(近似): {equity:.2f}")
    print(
        f"  IM 需求: {ms.initial_margin_req:.2f}  MM 需求: {ms.maintenance_margin_req:.2f} "
        f"缓冲: {ms.buffer_usdt:.2f}  穿仓: {'是' if ms.breached else '否'}\n"
    )


def cmd_mo_rules_check(notional: float, symbol: str, gross: float, sym_nv: float):
    """中台规则引擎试算"""
    from middle_office.rules import MiddleOfficeRuleEngine, RuleContext

    ctx = RuleContext(
        notional_usdt=notional,
        symbol=symbol,
        gross_exposure_usd=gross,
        equity_usdt=100000.0,
        extra={"symbol_notional_usd": sym_nv},
    )
    eng = MiddleOfficeRuleEngine()
    for o in eng.evaluate(ctx):
        print(f"  [{o.name}] {'PASS' if o.passed else 'FAIL'} — {o.message}")
    print()


def cmd_approval_submit(requester: str, action: str, payload: str):
    db = Database()
    try:
        rid = db.insert_approval_request(
            requester=requester, action=action, payload_json=payload or "{}"
        )
    finally:
        db.close()
    print(f"已创建审批请求 id={rid}")


def cmd_approval_list(pending_only: bool):
    db = Database()
    try:
        rows = db.list_approval_requests(
            status="pending" if pending_only else None,
            limit=100,
        )
    finally:
        db.close()
    for r in rows:
        print(
            f"id={r['id']} status={r['status']} action={r['action']} "
            f"requester={r['requester']} ts={r['created_ts']}"
        )


def cmd_approval_resolve(req_id: int, approve: bool, decided_by: str, note: str):
    db = Database()
    try:
        ok = db.resolve_approval_request(
            req_id,
            new_status="approved" if approve else "rejected",
            decided_by=decided_by,
            note=note,
        )
    finally:
        db.close()
    print("已更新" if ok else "失败(可能已处理或 id 不存在)")


def cmd_accounts_show():
    db = Database()
    try:
        for aid in ("MAIN", "SUB"):
            db.ensure_account_balance(aid, 0.0)
        cur = db.conn.cursor()
        cur.execute("SELECT account_id, balance_usdt FROM account_balances ORDER BY account_id")
        print("\n账户余额 (账本)\n")
        for row in cur.fetchall():
            print(f"  {row['account_id']}: {row['balance_usdt']:.4f} USDT")
        print()
    finally:
        db.close()


def cmd_accounts_seed(account: str, amount: float):
    db = Database()
    try:
        cur = db.conn.cursor()
        cur.execute(
            """INSERT INTO account_balances (account_id, balance_usdt) VALUES (?, ?)
               ON CONFLICT(account_id) DO UPDATE SET balance_usdt = excluded.balance_usdt""",
            (account, amount),
        )
        db.conn.commit()
    finally:
        db.close()
    print(f"已设置 {account} = {amount:.4f} USDT")


def cmd_accounts_transfer(frm: str, to: str, amount: float, note: str):
    db = Database()
    try:
        r = db.execute_transfer(frm, to, amount, note=note)
    finally:
        db.close()
    print(json.dumps(r, ensure_ascii=False))


def cmd_tax_export(year: int | None, out_path: str):
    db = Database()
    try:
        trades = db.list_sell_trades()
    finally:
        db.close()
    from accounts.tax_export import export_realized_pnl_by_year_csv

    info = export_realized_pnl_by_year_csv(trades, out_path, year=year)
    print(f"税务辅助 CSV 已写: {info}")


def cmd_factor_desk(mock: bool):
    """Barra-lite + 风格因子截面 (演示)"""
    import numpy as np

    from factors.risk_model import portfolio_volatility, single_market_factor_assumption
    from factors.style_factors import style_low_vol_z, style_momentum_z

    if mock:
        rng = np.random.default_rng(7)
        syms = list(SYMBOLS[: min(3, len(SYMBOLS))])
        panel = {s: 100.0 * np.cumprod(1.0 + rng.normal(0, 0.02, 120)) for s in syms}
    else:
        from factors.cross_section import load_close_panel_from_db

        db = Database()
        try:
            _ts, panel = load_close_panel_from_db(db, SYMBOLS, TIMEFRAME, 200)
        finally:
            db.close()
        if len(panel) < 2:
            logger.error("DB 数据不足, 请 --mock")
            sys.exit(1)
    zm = style_momentum_z(panel)
    zlv = style_low_vol_z(panel)
    n = len(panel)
    betas = np.linspace(1.1, 0.9, n)
    idio = np.full(n, 0.0004)
    cov = single_market_factor_assumption(betas, 0.00025, idio)
    w = np.ones(n) / n
    vol = portfolio_volatility(w, cov)
    print("\n因子工作台 (Barra-lite + 风格 z)\n")
    for s in sorted(panel.keys()):
        print(f"  {s}: z_mom={zm.get(s, 0):+.2f} z_lowvol={zlv.get(s, 0):+.2f}")
    print(f"  等权组合 σ (收益步长): {vol*100:.4f}%\n")


def cmd_alt_data_status():
    import config as cfg

    from alternative_data.sentiment_csv import sentiment_stub_status

    path = getattr(cfg, "ALT_DATA_SENTIMENT_CSV", "") or ""
    print(json.dumps(sentiment_stub_status(path), ensure_ascii=False, indent=2))


def cmd_ops_readiness():
    """运营就绪自检 (JSON): OMS/风控开关、待审批、因子与另类数据健康。"""
    import config as cfg

    from factors.platform_health import platform_health

    db = Database()
    try:
        pending = db.list_approval_requests(status="pending", limit=500)
        oms_rows = db.list_oms_orders(limit=200)
    finally:
        db.close()
    out = {
        "router_backend": getattr(cfg, "ROUTER_BACKEND", ""),
        "ccxt_live_enabled": bool(getattr(cfg, "CCXT_LIVE_ENABLED", False)),
        "oms_idempotency_enabled": bool(getattr(cfg, "OMS_IDEMPOTENCY_ENABLED", True)),
        "risk_realtime_rules_enabled": bool(
            getattr(cfg, "RISK_REALTIME_RULES_ENABLED", False)
        ),
        "approval_sla_expire_hours": int(
            getattr(cfg, "APPROVAL_SLA_EXPIRE_HOURS", 168) or 168
        ),
        "pending_approvals_count": len(pending),
        "oms_orders_listed": len(oms_rows),
        "factor_platform": platform_health(),
        "checklist": [
            "配置飞书/企微/SMTP/Server酱 之一用于 live/paper-live 告警",
            "生产须分级开启 ROUTER_BACKEND 与 CCXT_LIVE_ENABLED",
            "定时任务执行: python main.py approval-expire --hours <SLA>",
            "desk 全链路可在 PipelineContext.meta 传入 client_order_id / current_drawdown_pct / daily_loss_pct",
            "上线前: python main.py security-check; 日终: python main.py reconcile",
            "备份: python main.py db-backup; 审计抽样: python main.py regulatory-export --out reports/audit.csv",
            "阅读 docs/DELIVERY_HARDENING.md 与 .env.example (密钥勿入库)",
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_security_check():
    """环境与密钥粗检 (非渗透测试)。"""
    from security.env_hardening import run_security_precheck

    print(json.dumps(run_security_precheck(), ensure_ascii=False, indent=2))


def cmd_reconcile():
    """OMS / 执行 / 划拨 / 审计 摘要对账。"""
    from compliance.reconciliation import reconciliation_to_json, run_reconciliation

    db = Database()
    try:
        data = run_reconciliation(db)
    finally:
        db.close()
    print(reconciliation_to_json(data))


def cmd_regulatory_export(out_path: str, limit: int, hash_actors: bool):
    """审计表 CSV 导出 (占位, 非正式监管报送)。"""
    from compliance.regulatory_stub import export_audit_events_csv

    db = Database()
    try:
        meta = export_audit_events_csv(
            db, out_path, limit=limit, hash_actors=hash_actors
        )
    finally:
        db.close()
    print(json.dumps(meta, ensure_ascii=False, indent=2))


def cmd_db_backup(dest_dir: str | None):
    """SQLite 冷备份 (与 scripts/db_backup.py 行为一致)。"""
    import shutil
    from datetime import datetime

    import config as cfg

    root = os.path.dirname(os.path.abspath(__file__))
    dest = dest_dir or os.path.join(root, "backups")
    src = os.path.abspath(cfg.DB_PATH)
    if not os.path.isfile(src):
        logger.error(f"源库不存在: {src}")
        sys.exit(1)
    os.makedirs(dest, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.basename(src).replace(".db", "")
    dst = os.path.join(dest, f"{base}_{ts}.db")
    shutil.copy2(src, dst)
    print(json.dumps({"source": src, "destination": dst}, ensure_ascii=False, indent=2))


def cmd_approval_expire(hours: int):
    """将超期 pending 审批标为 expired (不可再用于下单)。"""
    db = Database()
    try:
        n = db.expire_pending_approvals(max_age_hours=max(1, int(hours)))
        print(f"已更新 {n} 条审批为 expired (创建早于 {hours} 小时且仍为 pending)")
    finally:
        db.close()


def cmd_oms_orders_list(limit: int, status: str | None):
    """列出 OMS 订单生命周期记录。"""
    db = Database()
    try:
        rows = db.list_oms_orders(limit=limit, status=status)
        if not rows:
            print("(无记录)")
            return
        for r in rows:
            print(
                f"id={r.get('id')} {r.get('client_order_id')} {r.get('symbol')} "
                f"{r.get('side')} status={r.get('status')} notional={r.get('notional_usdt')}"
            )
    finally:
        db.close()


def cmd_institutional():
    """机构化模块说明 (仿真边界)"""
    from security.permissions import role_matrix_doc

    print(
        """
================================================================
  机构化脚手架 (仿真 / 扩展点)
================================================================

  execution/   限价梯度近似 + 平方根冲击 + VWAP 吃单
  portfolio/   多资产风险平价 / 长约束最小方差 (numpy)
  factors/     横截面动量、波动率及 z-score
  routing/     执行路由 + 计时 + 审计钩子 (Python 非纳秒级)
  compliance/  单笔/时段策略 + SQLite & JSONL 审计
  security/    RBAC (QUANT_BOT_ROLE 或 config.SECURITY_DEFAULT_ROLE)

  不替代: 持牌合规结论、银行级托管、交易所共址低延迟链路。

  CLI: portfolio-opt | factors-xsec | router-dry-run | audit-log
  交易台扩展: oms-submit | exposure-report | mo-rules-check |
              approval-submit/list/resolve | approval-expire | oms-orders |
              accounts-* | tax-export | factor-desk | alt-data-status | ops-readiness |
              security-check | reconcile | regulatory-export | db-backup
================================================================
"""
    )
    print(role_matrix_doc())
    print()


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


def cmd_news_sync():
    """从 config.NEWS_RSS_FEEDS 拉取 RSS 入消息池"""
    from news.pool import sync_news_pool

    r = sync_news_pool()
    print(
        f"消息池同步: 抓取约 {r['fetched']} 条, 新入库 {r['inserted']} 条, "
        f"feeds={r['feeds']}"
    )


def cmd_news_list(hours: int, limit: int, category: str | None):
    """列出库内近期消息 (需先 news-sync 且配置 RSS)"""
    import time

    since = int(time.time()) - max(1, hours) * 3600
    db = Database()
    try:
        rows = db.list_news_items(
            limit=max(1, min(200, limit)),
            since_ts=since,
            category=category,
        )
    finally:
        db.close()
    if not rows:
        print(
            "(无记录: 在 config.py 设置 NEWS_RSS_FEEDS 后执行 news-sync, "
            "或放宽 --hours)"
        )
        return
    for r in rows:
        pub = int(r.get("published_at") or 0)
        cat = r.get("category") or ""
        sen = r.get("sentiment") or ""
        title = (r.get("title") or "")[:160]
        print(f"[{cat}/{sen}] @{pub} {title}")
        link = r.get("link") or ""
        if link:
            print(f"  {link}")
        print()


def cmd_live_poll(use_mock: bool, once: bool, strategy: str | None, symbols_csv: str | None):
    from runtime.live_poll import run_live_polling

    syms = [s.strip() for s in symbols_csv.split(",")] if symbols_csv else None
    run_live_polling(use_mock=use_mock, once=once, strategy=strategy, symbols=syms)


def cmd_paper_live(use_mock: bool, once: bool, strategy: str | None, symbols_csv: str | None):
    from runtime.paper_live import run_paper_live

    syms = [s.strip() for s in symbols_csv.split(",")] if symbols_csv else None
    run_paper_live(use_mock=use_mock, once=once, strategy=strategy, symbols=syms)


def cmd_web(host: str, port: int, refresh_sec: int, debug: bool):
    import web.app as web_app

    web_app.DASH_REFRESH_SEC = max(3, int(refresh_sec))
    from web.app import main as web_main

    web_main(host=host, port=port, debug=debug)


def cmd_backtest_all(
    use_mock: bool, days: int | None, strategy: str | None, profile: str | None
):
    import logging

    d = days if days is not None else BACKTEST_DAYS
    ov, st_pf = _profile_overrides_and_strategy(profile, strategy)
    st = st_pf if st_pf is not None else (strategy if strategy is not None else STRATEGY)
    logging.disable(logging.CRITICAL)
    print("\n" + "=" * 72)
    print(
        f"  多币种回测 策略={st}  周期={TIMEFRAME}  天数={d}  mock={use_mock}"
        f"{f'  preset={profile}' if profile else ''}"
    )
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
                candles = fetch_ohlcv(sym, TIMEFRAME, d)
            if not candles:
                print(f"  {sym:<14} {'(无数据)':>10}")
                continue
            r = run_backtest(candles, quiet=True, strategy=st, config_overrides=ov)
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
    profile: str | None = None,
):
    import logging

    d = days if days is not None else BACKTEST_DAYS
    ov, st_pf = _profile_overrides_and_strategy(profile, strategy)
    st = st_pf if st_pf is not None else (strategy if strategy is not None else STRATEGY)
    sym = symbol or SYMBOL
    if use_mock:
        candles = generate_mock_data(d, seed=42)
    else:
        candles = fetch_ohlcv(sym, TIMEFRAME, d)
    if not candles:
        logger.error("无 K 线, 无法出图")
        sys.exit(1)
    logging.disable(logging.CRITICAL)
    try:
        r = run_backtest(
            candles,
            strategy=st,
            include_equity_curve=True,
            quiet=True,
            config_overrides=ov,
        )
    finally:
        logging.disable(logging.NOTSET)
    if not r:
        sys.exit(1)
    from visualization.report_chart import save_report_charts

    prefix = f"{sym.replace('/', '-')}_{st}"
    if profile:
        prefix += f"_{profile}"
    paths = save_report_charts(r, candles, out_dir, prefix=prefix)
    print("\n图表已生成:")
    for p in paths:
        print(" ", p)
    print()


def cmd_client_guide():
    """客户/交付侧：能力摘要 + 风险边界（详细见 CLIENT.md）"""
    import os

    root = os.path.dirname(os.path.abspath(__file__))
    client_md = os.path.join(root, "CLIENT.md")
    print(
        """
================================================================
  Quant Bot — 客户快速说明（非投资建议）
================================================================

  本软件提供：回测、多策略对比、纸面模拟、信号推送、Web 看板等。
  不承诺盈利、不保本；历史与模拟结果不代表未来实盘表现。

  请阅读完整披露文件:
"""
    )
    print(f"    {client_md}")
    print(
        """
  建议首次命令:
    python main.py strategies
    python main.py backtest --mock
    python main.py compare --mock --days 60
    python main.py client-guide
    python main.py product-brief --mock --json   # 证据包（治理三层+可选WF+多策略）

  偏保守参数（仍非保证盈利）:
    python main.py backtest --profile stability --mock

  纸面 + 看板（本地模拟，不接交易所下单）:
    python main.py paper-live --once --mock
    python main.py web

  消息池（RSS→分类入库，通知可附摘要；非投资建议）:
    在 config.py 配置 NEWS_RSS_FEEDS 后:
    python main.py news-sync
    python main.py news-list --hours 72

  样本外滚动（walk-forward，固定参数跨段检验）:
    python main.py walk-forward --mock --train-bars 200 --test-bars 100

================================================================
"""
    )


def cmd_list_strategies():
    """列出可用策略"""
    print("\n可用策略:")
    print("  ma_cross       — 双均线金叉/死叉 (SMA)")
    print("  ema_cross      — 双 EMA 金叉/死叉")
    print("  triple_ma      — 三均线多头排列")
    print("  donchian       — 唐奇安通道突破")
    print("  roc_mom        — ROC 动量阈值")
    print("  bb_mean_revert — 布林下轨 + RSI 均值回归")
    print("  rsi_macd       — MACD + RSI + 均线过滤")
    print("  rsi            — 纯 RSI 超卖/超买")
    print("  macd           — 纯 MACD 金叉/死叉")
    print("  bollinger      — 纯布林带 + ATR 止损")
    print("  vibe           — 趋势 + 布林/RSI + ATR")
    print("  ensemble       — 多子策略投票 (见 ENSEMBLE_COMPONENTS)")
    print("  ensemble_strict— 高门槛投票 (见 ENSEMBLE_STRICT_*, 信号更稀疏)")
    print("\nconfig.STRATEGY 切换; compare / optimize / combo-search 见 --help\n")


def cmd_combo_search(
    use_mock: bool,
    days: int | None,
    symbol: str | None,
    pool_csv: str | None,
    min_size: int,
    max_size: int,
    min_votes: int,
    max_votes: int | None,
    max_eval: int,
    seed: int,
    sort_by: str,
    profile: str | None,
):
    """
    从策略池枚举子集+票数, 投票合成信号后回测排序。
    不能得到「保证长期盈利」的完美方案; 仅历史探索工具。
    """
    import logging

    from runtime.combo_search import print_combo_search_report, run_combo_search
    from runtime.presets import get_profile_overrides

    ov = None
    if profile:
        try:
            ov = get_profile_overrides(profile)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    d = days if days is not None else BACKTEST_DAYS
    sym = symbol or SYMBOL
    if use_mock:
        candles = generate_mock_data(d, seed=seed, silent=True)
    else:
        logger.info(f"拉取 K 线: {sym} {TIMEFRAME} {d} 天...")
        candles = fetch_ohlcv(sym, TIMEFRAME, d)
    if not candles:
        logger.error("无 K 线数据")
        sys.exit(1)

    logging.disable(logging.CRITICAL)
    try:
        try:
            result = run_combo_search(
                candles,
                pool_csv=pool_csv,
                min_size=min_size,
                max_size=max_size,
                min_votes=min_votes,
                max_votes=max_votes,
                max_eval=max_eval,
                seed=seed,
                sort_by=sort_by,
                config_overrides=ov,
            )
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)
    finally:
        logging.disable(logging.NOTSET)

    print_combo_search_report(result)


def main():
    parser = argparse.ArgumentParser(
        description="量化交易 Bot - 模拟盘",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py backtest          # 使用真实数据回测
  python main.py backtest --mock   # 使用模拟数据回测
  python main.py backtest --profile stability --mock  # 稳健预设 (低仓位/紧回撤)
  python main.py status            # 查看交易状态
  python main.py strategies        # 查看可用策略
  python main.py client-guide      # 客户交付摘要与风险边界
  python main.py product-brief --mock --json          # 完整证据包 JSON（CRM/官网）
  python main.py product-brief --mock --strategies ma_cross,rsi_macd --json
  python main.py product-brief --mock --walk-forward --train-bars 200 --test-bars 100 --json
  python main.py product-brief --mock --pdf reports/dossier.pdf
  set QUANT_BOT_BRIEF_API_KEY=xxx && python main.py web   # 见 /api/product-brief?key=
  python main.py monte-carlo --runs 10000   # 一万组模拟行情压力测试
  python main.py compare                    # 真实 BTC 多策略对比
  python main.py compare --mock             # 模拟数据对比
  python main.py compare --strategies rsi,macd,bollinger
  python main.py compare-matrix --mock      # 多品种×多策略矩阵
  python main.py coupled-test --mock --runs 40  # 多次耦合 (多随机路径×全策略)
  python main.py rank-models --mock --runs 25   # 综合分排名 (耦合+加权)
  python main.py rank-models --mock --runs 50 --min-profit-round-rate 0.65  # 仅≥65%%盈利轮
  python main.py combo-search --mock --max-eval 80   # 投票组合池搜索 (历史排名)
  python main.py optimize --mock            # VIBE 网格搜索 (训练/测试)
  python main.py sync                       # 多币种增量同步 K 线到数据库
  python main.py live --mock --once         # 模拟一轮信号轮询
  python main.py paper-live --once          # 纸面模拟一轮 (写 data/paper_live_state.json)
  python main.py web --refresh-sec 8        # Web/PWA 看板 http://127.0.0.1:5050 (手机可添加到主屏幕)
  python main.py backtest-all --mock       # 多币种批量回测
  python main.py chart --mock              # 权益/回撤/月度图 → reports/

  A股行情 (AkShare): config.py 中 MARKET_MODE = "cn_a", SYMBOL = "600519", TIMEFRAME = "1d",
  SYMBOLS = ("600519","000001"); 或环境变量 QUANT_BOT_MARKET=cn_a
  pip install akshare pandas
  python main.py backtest --days 500
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
        help="策略名: ma_cross | ema_cross | triple_ma | donchian | roc_mom | bb_mean_revert | rsi_macd | rsi | macd | bollinger | vibe | ensemble | ensemble_strict",
    )
    bt_parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"回测天数 (默认 {BACKTEST_DAYS})",
    )
    bt_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )
    bt_parser.add_argument(
        "--export-trades",
        default=None,
        metavar="PATH",
        help="导出回测成交明细 CSV (如 reports/trades.csv)",
    )

    sens_parser = subparsers.add_parser(
        "sensitivity",
        help="单参数敏感性: 固定 K 线多次回测 (对比市面参数扫描)",
    )
    sens_parser.add_argument("--mock", action="store_true")
    sens_parser.add_argument("--days", type=int, default=None)
    sens_parser.add_argument("--strategy", default=None)
    sens_parser.add_argument(
        "--param",
        required=True,
        metavar="NAME",
        help="config 属性名, 如 SLOW_PERIOD, VIBE_RSI_BUY",
    )
    sens_parser.add_argument(
        "--values",
        required=True,
        help="逗号分隔数值, 如 20,25,30,35",
    )
    sens_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

    reg_parser = subparsers.add_parser(
        "regime-report",
        help="标的滚动波动率 regime 占比 (高/低波动分段)",
    )
    reg_parser.add_argument("--mock", action="store_true")
    reg_parser.add_argument("--days", type=int, default=None)

    st_parser = subparsers.add_parser(
        "stress-scenario",
        help="自最深回撤点起对权益施加一次性比例冲击 (情景分析)",
    )
    st_parser.add_argument("--mock", action="store_true")
    st_parser.add_argument("--days", type=int, default=None)
    st_parser.add_argument("--strategy", default=None)
    st_parser.add_argument(
        "--shock",
        type=float,
        default=-0.1,
        help="冲击比例, 如 -0.1 表示 -10%% (默认 -0.1)",
    )
    st_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
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
    cmp_parser.add_argument(
        "--symbol",
        default=None,
        help=f"交易对 (默认 config.SYMBOL = {SYMBOL})",
    )
    cmp_parser.add_argument(
        "--strategies",
        default=None,
        help="逗号分隔策略名, 省略则跑全套 COMPARE_STRATEGY_ORDER",
    )
    cmp_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

    cm_parser = subparsers.add_parser(
        "compare-matrix",
        help="多品种×多策略矩阵回测 (对每个 SYMBOL 跑全套策略)",
    )
    cm_parser.add_argument("--mock", action="store_true", help="模拟数据")
    cm_parser.add_argument("--days", type=int, default=None, help=f"天数 (默认 {BACKTEST_DAYS})")
    cm_parser.add_argument(
        "--symbols",
        default=None,
        help="逗号分隔交易对, 默认 config.SYMBOLS",
    )
    cm_parser.add_argument(
        "--strategies",
        default=None,
        help="逗号分隔策略名, 省略则全套",
    )
    cm_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

    ct_parser = subparsers.add_parser(
        "coupled-test",
        help="多次耦合回测: 每轮多策略共享同一K线, 汇总均值/波动/盈利轮占比",
    )
    ct_parser.add_argument(
        "--runs",
        type=int,
        default=30,
        help="轮数: mock-seeds=不同随机路径条数; walk-forward=时间分窗数",
    )
    ct_parser.add_argument("--days", type=int, default=None, help=f"天数 (默认 {BACKTEST_DAYS})")
    ct_parser.add_argument(
        "--mock",
        action="store_true",
        help="mock-seeds 必需; walk-forward 下为单条模拟K线再切段",
    )
    ct_parser.add_argument(
        "--mode",
        default=None,
        help="mock-seeds | walk-forward; 省略时: 有 --mock 则 mock-seeds 否则 walk-forward",
    )
    ct_parser.add_argument(
        "--symbol",
        default=None,
        help=f"walk-forward 拉真实行情用 (默认 {SYMBOL})",
    )
    ct_parser.add_argument(
        "--strategies",
        default=None,
        help="逗号分隔策略名, 省略为 COMPARE_STRATEGY_ORDER",
    )
    ct_parser.add_argument(
        "--seed-offset",
        type=int,
        default=0,
        help="模拟随机种子起始偏移",
    )
    ct_parser.add_argument(
        "--sort",
        dest="sort_by",
        default="sharpe",
        choices=["sharpe", "profit"],
        help="汇总表按何指标排序 (默认 sharpe)",
    )
    ct_parser.add_argument(
        "--win-round-target",
        type=float,
        default=None,
        help="覆盖 config.TARGET_COUPLED_WIN_ROUND_RATIO (0~1), 用于文末「≥65%%盈利轮」对照行",
    )
    ct_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

    rm_parser = subparsers.add_parser(
        "rank-models",
        help="综合分排名: 多策略耦合或单段K线, 按收益/夏普/回撤/盈利轮加权 (仅历史参考)",
    )
    rm_parser.add_argument(
        "--scope",
        choices=["coupled", "single"],
        default="coupled",
        help="coupled=多次耦合汇总; single=同一批K线单次回测 (默认 coupled)",
    )
    rm_parser.add_argument(
        "--runs",
        type=int,
        default=30,
        help="scope=coupled 时轮数 (默认 30)",
    )
    rm_parser.add_argument("--days", type=int, default=None, help=f"天数 (默认 {BACKTEST_DAYS})")
    rm_parser.add_argument(
        "--mock",
        action="store_true",
        help="模拟数据; coupled 下默认 mock-seeds",
    )
    rm_parser.add_argument(
        "--coupled-mode",
        default=None,
        help="scope=coupled 时: mock-seeds | walk-forward (省略则同 coupled-test)",
    )
    rm_parser.add_argument("--symbol", default=None, help=f"品种 (默认 {SYMBOL})")
    rm_parser.add_argument("--strategies", default=None, help="逗号分隔策略, 省略为全套")
    rm_parser.add_argument("--seed-offset", type=int, default=0, help="模拟种子偏移")
    rm_parser.add_argument(
        "--min-profit-round-rate",
        type=float,
        default=None,
        help="仅保留耦合「盈利轮占比」≥该值(0~1, 如0.65)的策略; 无人满足则退出码2",
    )
    rm_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

    cs_parser = subparsers.add_parser(
        "combo-search",
        help="策略池投票组合枚举+回测排序 (非保证盈利; 注意过拟合)",
    )
    cs_parser.add_argument("--mock", action="store_true", help="模拟 K 线")
    cs_parser.add_argument("--days", type=int, default=None, help=f"天数 (默认 {BACKTEST_DAYS})")
    cs_parser.add_argument("--symbol", default=None, help=f"品种 (默认 {SYMBOL})")
    cs_parser.add_argument(
        "--pool",
        default=None,
        help="逗号分隔子策略池, 默认内置 DEFAULT_COMBO_POOL (不含 ensemble*)",
    )
    cs_parser.add_argument("--min-size", type=int, default=3, help="子集最小元素数 (默认 3)")
    cs_parser.add_argument("--max-size", type=int, default=5, help="子集最大元素数 (默认 5)")
    cs_parser.add_argument("--min-votes", type=int, default=2, help="最少同意票数下限 (默认 2)")
    cs_parser.add_argument(
        "--max-votes",
        type=int,
        default=None,
        help="最少同意票数上限; 默认等于子集大小",
    )
    cs_parser.add_argument(
        "--max-eval",
        type=int,
        default=120,
        help="最多评估多少组 (组合爆炸时随机抽样, 默认 120)",
    )
    cs_parser.add_argument("--seed", type=int, default=42, help="抽样随机种子")
    cs_parser.add_argument(
        "--sort",
        dest="sort_by",
        default="composite",
        choices=["composite", "sharpe", "profit"],
        help="排序指标 (默认 composite)",
    )
    cs_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
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

    wf_parser = subparsers.add_parser(
        "walk-forward",
        help="滚动 walk-forward: 多段训练+样本外测试 (固定参数, 抗过拟合参考)",
    )
    wf_parser.add_argument("--mock", action="store_true", help="模拟 K 线")
    wf_parser.add_argument("--days", type=int, default=None, help=f"K 线天数 (默认 {BACKTEST_DAYS})")
    wf_parser.add_argument("--strategy", default=None, help="策略名, 默认 config.STRATEGY")
    wf_parser.add_argument(
        "--train-bars",
        type=int,
        default=500,
        help="每段训练 K 线根数 (默认 500)",
    )
    wf_parser.add_argument(
        "--test-bars",
        type=int,
        default=200,
        help="每段样本外 K 线根数 (默认 200)",
    )
    wf_parser.add_argument(
        "--step",
        type=int,
        default=None,
        help="窗口右移根数; 默认等于 test-bars (样本外段不重叠)",
    )
    wf_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

    subparsers.add_parser("sync", help="增量同步 config.SYMBOLS 的 K 线到 SQLite")

    subparsers.add_parser(
        "news-sync",
        help="从 RSS 拉取消息入消息池 (需 config.NEWS_RSS_FEEDS 与网络)",
    )
    nl_parser = subparsers.add_parser("news-list", help="列出库内近期消息")
    nl_parser.add_argument(
        "--hours",
        type=int,
        default=168,
        help="仅显示最近 N 小时内 (默认 168=7 天)",
    )
    nl_parser.add_argument("--limit", type=int, default=30, help="最多条数 (默认 30)")
    nl_parser.add_argument(
        "--category",
        default=None,
        metavar="CAT",
        help="按分类过滤 (如 regulation, macro, exchange)",
    )

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

    pl_parser = subparsers.add_parser(
        "paper-live",
        help="纸面实盘模拟: 定时拉 K 线 → 模拟买卖 → 持久化 (同一账户多品种)",
    )
    pl_parser.add_argument("--mock", action="store_true", help="模拟 K 线")
    pl_parser.add_argument("--once", action="store_true", help="只跑一轮后退出")
    pl_parser.add_argument("--strategy", default=None, help="覆盖 STRATEGY")
    pl_parser.add_argument(
        "--symbols",
        default=None,
        help="逗号分隔交易对, 默认 SYMBOLS",
    )

    web_parser = subparsers.add_parser(
        "web",
        help="启动 Web 看板 (资金曲线、成交、持仓), 读 paper-live 状态文件",
    )
    web_parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    web_parser.add_argument("--port", type=int, default=5050, help="端口")
    web_parser.add_argument(
        "--refresh-sec",
        type=int,
        default=8,
        metavar="SEC",
        help="看板自动刷新间隔 (秒)",
    )
    web_parser.add_argument("--debug", action="store_true", help="Flask 调试模式")

    ba_parser = subparsers.add_parser(
        "backtest-all",
        help="对 SYMBOLS 逐个回测并汇总",
    )
    ba_parser.add_argument("--mock", action="store_true")
    ba_parser.add_argument("--days", type=int, default=None)
    ba_parser.add_argument("--strategy", default=None)
    ba_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

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
    ch_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

    # status 命令
    subparsers.add_parser("status", help="查看交易状态")

    # strategies 命令
    subparsers.add_parser("strategies", help="列出可用策略")

    subparsers.add_parser(
        "client-guide",
        help="客户/交付：能力摘要与风险边界（详见 CLIENT.md）",
    )

    pb_parser = subparsers.add_parser(
        "product-brief",
        help="产品执行摘要：历史样本+诊断+事实向卖点（不构成投资建议）",
    )
    pb_parser.add_argument("--mock", action="store_true", help="模拟行情（无需网络）")
    pb_parser.add_argument("--days", type=int, default=None, help="回测天数")
    pb_parser.add_argument("--strategy", default=None, help="策略名（默认 config.STRATEGY）")
    pb_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )
    pb_parser.add_argument(
        "--json",
        action="store_true",
        help="输出完整证据包 JSON（schema=quant_bot_product_dossier_v1）",
    )
    pb_parser.add_argument(
        "--compact-json",
        action="store_true",
        help="仅输出旧版单页 brief JSON（不含治理三层/多样本外；与 --pdf/--walk-forward 互斥）",
    )
    pb_parser.add_argument(
        "--strategies",
        default=None,
        metavar="CSV",
        help="额外策略逗号列表，与主策略合并批量 brief（如 ma_cross,rsi_macd）",
    )
    pb_parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="合并 walk-forward 样本外章节（主策略）",
    )
    pb_parser.add_argument(
        "--train-bars",
        type=int,
        default=500,
        help="walk-forward 训练窗 K 线根数 (默认 500)",
    )
    pb_parser.add_argument(
        "--test-bars",
        type=int,
        default=200,
        help="walk-forward 样本外窗 K 线根数 (默认 200)",
    )
    pb_parser.add_argument(
        "--step",
        type=int,
        default=None,
        help="walk-forward 右移根数；默认等于 test-bars",
    )
    pb_parser.add_argument(
        "--pdf",
        default=None,
        metavar="PATH",
        help="另存单页 PDF（需 pip install fpdf2；中文需系统字体或 QUANT_BOT_PDF_FONT）",
    )

    subparsers.add_parser(
        "institutional",
        help="机构化模块说明 (订单簿/组合/因子/路由/审计/权限 — 仿真边界)",
    )

    al_parser = subparsers.add_parser("audit-log", help="查看审计事件 (SQLite)")
    al_parser.add_argument("--limit", type=int, default=40, help="条数 (默认 40)")

    po_parser = subparsers.add_parser(
        "portfolio-opt",
        help="多资产静态权重: 风险平价或最小方差 (需 DB 多品种 K 线或 --mock)",
    )
    po_parser.add_argument(
        "--method",
        choices=["riskparity", "minvar"],
        default="riskparity",
        help="优化目标 (默认 riskparity)",
    )
    po_parser.add_argument("--mock", action="store_true", help="随机价格面板")
    po_parser.add_argument(
        "--limit",
        type=int,
        default=800,
        help="每品种 K 线根数 (默认 800)",
    )

    fx_parser = subparsers.add_parser(
        "factors-xsec",
        help="横截面因子快照 (动量/波动 + z-score, 需 DB 对齐 K 线)",
    )
    fx_parser.add_argument(
        "--symbols",
        default=None,
        help=f"逗号分隔品种, 默认 SYMBOLS",
    )
    fx_parser.add_argument("--limit", type=int, default=800, help="每品种 K 线根数")

    rd_parser = subparsers.add_parser(
        "router-dry-run",
        help="执行路由演练 (权限+合规+冲击价+审计), 不真实下单",
    )
    rd_parser.add_argument("--symbol", default=SYMBOL, help="交易对")
    rd_parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    rd_parser.add_argument("--notional", type=float, default=5000.0, help="美元名义")
    rd_parser.add_argument("--mid", type=float, default=50000.0, help="参考中间价")
    rd_parser.add_argument(
        "--role",
        default=None,
        help="覆盖 RBAC 角色 (默认环境变量或 config)",
    )

    oms_parser = subparsers.add_parser(
        "oms-submit",
        help="OMS/EMS 多通道提交 (sim 失败→paper; 大额需审批或 --force)",
    )
    oms_parser.add_argument("--symbol", default=SYMBOL, help="交易对")
    oms_parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    oms_parser.add_argument("--notional", type=float, default=1000.0)
    oms_parser.add_argument("--mid", type=float, default=50000.0)
    oms_parser.add_argument(
        "--force",
        action="store_true",
        help="跳过「超名义需审批」检查 (演示)",
    )
    oms_parser.add_argument(
        "--approval-id",
        type=int,
        default=None,
        help="已批准的 approval_requests.id (大额且非 --force)",
    )
    oms_parser.add_argument(
        "--gross",
        type=float,
        default=0.0,
        help="当前组合毛敞口 USD (中台规则)",
    )
    oms_parser.add_argument(
        "--equity",
        type=float,
        default=100000.0,
        help="当前权益 USD (中台规则)",
    )
    oms_parser.add_argument(
        "--symbol-notional",
        type=float,
        default=0.0,
        dest="symbol_notional",
        help="当前标的美元名义 (集中度)",
    )

    dp_parser = subparsers.add_parser(
        "desk-pipeline",
        help="显式打印全链路各段 (可选 --no-ems)",
    )
    dp_parser.add_argument("--symbol", default=SYMBOL)
    dp_parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    dp_parser.add_argument("--notional", type=float, default=1000.0)
    dp_parser.add_argument("--mid", type=float, default=50000.0)
    dp_parser.add_argument("--force", action="store_true")
    dp_parser.add_argument("--approval-id", type=int, default=None)
    dp_parser.add_argument("--gross", type=float, default=0.0)
    dp_parser.add_argument("--equity", type=float, default=100000.0)
    dp_parser.add_argument(
        "--symbol-notional",
        type=float,
        default=0.0,
        dest="symbol_notional",
    )
    dp_parser.add_argument(
        "--no-ems",
        action="store_true",
        help="仅跑到路由审计, 不跑 EMS 通道",
    )

    ex_parser = subparsers.add_parser(
        "exposure-report",
        help="中台: 读纸面持仓 + 标记价 → 毛敞口 / 保证金",
    )
    ex_parser.add_argument(
        "--price-map",
        default=None,
        metavar="MAP",
        help='标记价, 如 "BTC/USDT=97000,ETH/USDT=3500"',
    )
    ex_parser.add_argument("--mock", action="store_true", help="使用示例持仓")

    mor_parser = subparsers.add_parser(
        "mo-rules-check",
        help="中台规则引擎试算 (单笔/时段等)",
    )
    mor_parser.add_argument("--notional", type=float, default=5000.0)
    mor_parser.add_argument("--symbol", default="BTC/USDT")
    mor_parser.add_argument("--gross", type=float, default=50000.0, help="当前毛敞口 USD")
    mor_parser.add_argument(
        "--symbol-notional",
        type=float,
        default=20000.0,
        help="当前标的美元名义 (集中度用)",
    )

    ap_s = subparsers.add_parser("approval-submit", help="创建审批请求")
    ap_s.add_argument("--requester", default="cli")
    ap_s.add_argument("--action", required=True)
    ap_s.add_argument("--payload", default="{}", help="JSON 字符串")

    ap_l = subparsers.add_parser("approval-list", help="列出审批")
    ap_l.add_argument("--pending", action="store_true", help="仅 pending")

    ap_r = subparsers.add_parser("approval-resolve", help="审批通过/拒绝")
    ap_r.add_argument("--id", type=int, required=True, dest="req_id")
    ap_r.add_argument("--approve", action="store_true")
    ap_r.add_argument("--reject", action="store_true")
    ap_r.add_argument("--by", required=True, help="审批人标识")
    ap_r.add_argument("--note", default="")

    ac_s = subparsers.add_parser("accounts-show", help="多账户账本余额")
    ac_seed = subparsers.add_parser("accounts-seed", help="设置账户余额 (演示)")
    ac_seed.add_argument("--account", required=True)
    ac_seed.add_argument("--amount", type=float, required=True)
    ac_t = subparsers.add_parser("accounts-transfer", help="账户间划拨 USDT")
    ac_t.add_argument("--from", dest="from_acct", required=True)
    ac_t.add_argument("--to", dest="to_acct", required=True)
    ac_t.add_argument("--amount", type=float, required=True)
    ac_t.add_argument("--note", default="")

    tax_parser = subparsers.add_parser(
        "tax-export",
        help="按年汇总卖出已实现盈亏 CSV (非纳税申报表)",
    )
    tax_parser.add_argument("--year", type=int, default=None, help="仅导出该年; 默认全部年份")
    tax_parser.add_argument(
        "--out",
        default=os.path.join(REPORTS_DIR, "tax_pnl_by_year.csv"),
        help="输出路径",
    )

    fd_parser = subparsers.add_parser(
        "factor-desk",
        help="Barra-lite 协方差 + 风格因子 z (演示)",
    )
    fd_parser.add_argument("--mock", action="store_true")

    subparsers.add_parser(
        "alt-data-status",
        help="另类数据 CSV 配置状态 (情绪等)",
    )

    subparsers.add_parser(
        "ops-readiness",
        help="运营就绪自检 JSON (OMS/风控/因子/审批)",
    )
    ap_exp = subparsers.add_parser(
        "approval-expire",
        help="将超期仍为 pending 的审批标为 expired (SLA 清理)",
    )
    ap_exp.add_argument(
        "--hours",
        type=int,
        required=True,
        help="创建时间早于「当前时刻 − hours」的 pending 一律过期",
    )
    oms_list_p = subparsers.add_parser("oms-orders", help="列出 OMS 订单生命周期记录")
    oms_list_p.add_argument("--limit", type=int, default=50)
    oms_list_p.add_argument(
        "--status",
        default=None,
        help="按状态过滤: new|routing|ems_submitted|filled|partial_filled|rejected|cancelled",
    )

    subparsers.add_parser(
        "security-check",
        help="环境与密钥粗检 JSON (非渗透测试)",
    )
    subparsers.add_parser(
        "reconcile",
        help="OMS/执行/划拨/审计 对账摘要 JSON",
    )
    reg_export_p = subparsers.add_parser(
        "regulatory-export",
        help="审计事件 CSV 导出占位 (非正式监管报送)",
    )
    reg_export_p.add_argument("--out", required=True, help="输出 CSV 路径")
    reg_export_p.add_argument("--limit", type=int, default=10_000)
    reg_export_p.add_argument(
        "--hash-actors",
        action="store_true",
        help="对 actor 列做 SHA256 短哈希脱敏",
    )
    db_bak_p = subparsers.add_parser(
        "db-backup",
        help="SQLite 冷备份到指定目录 (默认 项目根/backups)",
    )
    db_bak_p.add_argument(
        "--dest-dir",
        default=None,
        help="备份目录; 未指定则为 项目根/backups",
    )

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
    mc_parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=_PROFILE_ARG_HELP,
    )

    args = parser.parse_args()

    if args.command == "backtest":
        cmd_backtest(
            use_mock=args.mock,
            strategy=args.strategy,
            days=getattr(args, "days", None),
            profile=getattr(args, "profile", None),
            export_trades=getattr(args, "export_trades", None),
        )
    elif args.command == "compare":
        cmd_compare(
            use_mock=args.mock,
            days=args.days,
            symbol=getattr(args, "symbol", None),
            strategies_csv=getattr(args, "strategies", None),
            profile=getattr(args, "profile", None),
        )
    elif args.command == "compare-matrix":
        cmd_compare_matrix(
            use_mock=args.mock,
            days=args.days,
            symbols_csv=getattr(args, "symbols", None),
            strategies_csv=getattr(args, "strategies", None),
            profile=getattr(args, "profile", None),
        )
    elif args.command == "coupled-test":
        cmd_coupled_test(
            runs=args.runs,
            days=args.days,
            use_mock=args.mock,
            mode=getattr(args, "mode", None),
            symbol=getattr(args, "symbol", None),
            strategies_csv=getattr(args, "strategies", None),
            seed_offset=args.seed_offset,
            sort_by=args.sort_by,
            win_round_target=getattr(args, "win_round_target", None),
            profile=getattr(args, "profile", None),
        )
    elif args.command == "rank-models":
        cmd_rank_models(
            scope=args.scope,
            runs=args.runs,
            days=args.days,
            use_mock=args.mock,
            coupled_mode=getattr(args, "coupled_mode", None),
            symbol=getattr(args, "symbol", None),
            strategies_csv=getattr(args, "strategies", None),
            seed_offset=args.seed_offset,
            min_profit_round_rate=getattr(args, "min_profit_round_rate", None),
            profile=getattr(args, "profile", None),
        )
    elif args.command == "combo-search":
        cmd_combo_search(
            use_mock=args.mock,
            days=args.days,
            symbol=getattr(args, "symbol", None),
            pool_csv=getattr(args, "pool", None),
            min_size=args.min_size,
            max_size=args.max_size,
            min_votes=args.min_votes,
            max_votes=getattr(args, "max_votes", None),
            max_eval=args.max_eval,
            seed=args.seed,
            sort_by=args.sort_by,
            profile=getattr(args, "profile", None),
        )
    elif args.command == "optimize":
        cmd_optimize(
            use_mock=args.mock,
            days=args.days,
            train_ratio=args.train_ratio,
        )
    elif args.command == "walk-forward":
        cmd_walk_forward(
            use_mock=args.mock,
            days=args.days,
            strategy=getattr(args, "strategy", None),
            train_bars=args.train_bars,
            test_bars=args.test_bars,
            step=getattr(args, "step", None),
            profile=getattr(args, "profile", None),
        )
    elif args.command == "sensitivity":
        cmd_sensitivity(
            use_mock=args.mock,
            days=getattr(args, "days", None),
            strategy=getattr(args, "strategy", None),
            param=args.param,
            values_csv=args.values,
            profile=getattr(args, "profile", None),
        )
    elif args.command == "regime-report":
        cmd_regime_report(
            use_mock=args.mock,
            days=getattr(args, "days", None),
        )
    elif args.command == "stress-scenario":
        cmd_stress_scenario(
            use_mock=args.mock,
            days=getattr(args, "days", None),
            strategy=getattr(args, "strategy", None),
            shock_pct=args.shock,
            profile=getattr(args, "profile", None),
        )
    elif args.command == "sync":
        cmd_sync_ohlcv()
    elif args.command == "news-sync":
        cmd_news_sync()
    elif args.command == "news-list":
        cmd_news_list(
            hours=args.hours,
            limit=args.limit,
            category=getattr(args, "category", None),
        )
    elif args.command == "live":
        cmd_live_poll(
            use_mock=args.mock,
            once=args.once,
            strategy=args.strategy,
            symbols_csv=args.symbols,
        )
    elif args.command == "paper-live":
        cmd_paper_live(
            use_mock=args.mock,
            once=args.once,
            strategy=args.strategy,
            symbols_csv=args.symbols,
        )
    elif args.command == "web":
        cmd_web(
            host=args.host,
            port=args.port,
            refresh_sec=getattr(args, "refresh_sec", 8),
            debug=args.debug,
        )
    elif args.command == "backtest-all":
        cmd_backtest_all(
            use_mock=args.mock,
            days=args.days,
            strategy=args.strategy,
            profile=getattr(args, "profile", None),
        )
    elif args.command == "chart":
        cmd_chart(
            use_mock=args.mock,
            days=args.days,
            strategy=args.strategy,
            symbol=args.symbol,
            out_dir=args.output_dir,
            profile=getattr(args, "profile", None),
        )
    elif args.command == "monte-carlo":
        cmd_monte_carlo(
            runs=args.runs,
            days=args.days,
            seed_offset=args.seed_offset,
            profile=getattr(args, "profile", None),
        )
    elif args.command == "status":
        cmd_status()
    elif args.command == "strategies":
        cmd_list_strategies()
    elif args.command == "client-guide":
        cmd_client_guide()
    elif args.command == "product-brief":
        cmd_product_brief(
            use_mock=args.mock,
            days=args.days,
            strategy=args.strategy,
            profile=getattr(args, "profile", None),
            as_json=args.json,
            compact_json=getattr(args, "compact_json", False),
            strategies_csv=getattr(args, "strategies", None),
            walk_forward=getattr(args, "walk_forward", False),
            train_bars=getattr(args, "train_bars", 500),
            test_bars=getattr(args, "test_bars", 200),
            step=getattr(args, "step", None),
            pdf_path=getattr(args, "pdf", None),
        )
    elif args.command == "institutional":
        cmd_institutional()
    elif args.command == "audit-log":
        cmd_audit_log(limit=args.limit)
    elif args.command == "portfolio-opt":
        cmd_portfolio_opt(
            method=args.method,
            mock=args.mock,
            limit=args.limit,
        )
    elif args.command == "factors-xsec":
        cmd_factors_xsec(limit=args.limit, symbols_csv=getattr(args, "symbols", None))
    elif args.command == "router-dry-run":
        cmd_router_dry_run(
            symbol=args.symbol,
            side=args.side,
            notional=args.notional,
            mid=args.mid,
            role=getattr(args, "role", None),
        )
    elif args.command == "oms-submit":
        cmd_oms_submit(
            symbol=args.symbol,
            side=args.side,
            notional=args.notional,
            mid=args.mid,
            force=args.force,
            approval_id=getattr(args, "approval_id", None),
            gross=getattr(args, "gross", 0.0),
            equity=getattr(args, "equity", 100000.0),
            sym_nv=getattr(args, "symbol_notional", 0.0),
        )
    elif args.command == "desk-pipeline":
        cmd_desk_pipeline(
            symbol=args.symbol,
            side=args.side,
            notional=args.notional,
            mid=args.mid,
            force=args.force,
            approval_id=getattr(args, "approval_id", None),
            gross=getattr(args, "gross", 0.0),
            equity=getattr(args, "equity", 100000.0),
            sym_nv=getattr(args, "symbol_notional", 0.0),
            no_ems=args.no_ems,
        )
    elif args.command == "exposure-report":
        cmd_exposure_report(
            price_map=getattr(args, "price_map", None),
            mock=args.mock,
        )
    elif args.command == "mo-rules-check":
        cmd_mo_rules_check(
            notional=args.notional,
            symbol=args.symbol,
            gross=args.gross,
            sym_nv=getattr(args, "symbol_notional", 0.0),
        )
    elif args.command == "approval-submit":
        cmd_approval_submit(
            requester=args.requester,
            action=args.action,
            payload=args.payload,
        )
    elif args.command == "approval-list":
        cmd_approval_list(pending_only=args.pending)
    elif args.command == "approval-resolve":
        if args.approve == args.reject:
            logger.error("请只指定其一: --approve 或 --reject")
            sys.exit(1)
        cmd_approval_resolve(
            req_id=args.req_id,
            approve=bool(args.approve),
            decided_by=args.by,
            note=args.note,
        )
    elif args.command == "accounts-show":
        cmd_accounts_show()
    elif args.command == "accounts-seed":
        cmd_accounts_seed(account=args.account, amount=args.amount)
    elif args.command == "accounts-transfer":
        cmd_accounts_transfer(
            frm=args.from_acct,
            to=args.to_acct,
            amount=args.amount,
            note=args.note,
        )
    elif args.command == "tax-export":
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        cmd_tax_export(year=args.year, out_path=args.out)
    elif args.command == "factor-desk":
        cmd_factor_desk(mock=args.mock)
    elif args.command == "alt-data-status":
        cmd_alt_data_status()
    elif args.command == "ops-readiness":
        cmd_ops_readiness()
    elif args.command == "approval-expire":
        cmd_approval_expire(hours=args.hours)
    elif args.command == "oms-orders":
        cmd_oms_orders_list(limit=args.limit, status=getattr(args, "status", None))
    elif args.command == "security-check":
        cmd_security_check()
    elif args.command == "reconcile":
        cmd_reconcile()
    elif args.command == "regulatory-export":
        cmd_regulatory_export(
            out_path=args.out,
            limit=args.limit,
            hash_actors=bool(args.hash_actors),
        )
    elif args.command == "db-backup":
        cmd_db_backup(dest_dir=getattr(args, "dest_dir", None))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
