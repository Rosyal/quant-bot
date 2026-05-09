"""
回测引擎
用历史数据验证策略表现; 集成账户风控与绩效指标。
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import config as cfg
from utils.logger import get_logger
from config import (
    SYMBOL,
    TIMEFRAME,
    INITIAL_BALANCE,
    BACKTEST_DAYS,
    STRATEGY,
    MIN_CANDLES_FOR_BACKTEST,
)
from exchange.paper import PaperExchange
from strategy import get_signal_fn
from risk.manager import RiskManager
from backtest.advanced_metrics import compute_advanced_metrics
from backtest.metrics import (
    buy_hold_equity_curve,
    compute_performance_metrics,
)
from backtest.tca import compute_tca_summary
from research.kelly import kelly_from_sell_trades

logger = get_logger("backtest")


@contextmanager
def _config_overrides(overrides: dict[str, Any] | None):
    if not overrides:
        yield
        return
    backup: dict[str, Any] = {}
    try:
        for k, v in overrides.items():
            if hasattr(cfg, k):
                backup[k] = getattr(cfg, k)
                setattr(cfg, k, v)
        yield
    finally:
        for k, v in backup.items():
            setattr(cfg, k, v)


def _position_pct(strategy_key: str) -> float:
    if strategy_key == "rsi_macd":
        return cfg.RSIMACD_TRADE_AMOUNT_PCT
    return cfg.TRADE_AMOUNT_PCT


def run_backtest(
    candles: list[dict],
    *,
    quiet: bool = False,
    strategy: str | None = None,
    config_overrides: dict[str, Any] | None = None,
    include_equity_curve: bool = False,
    include_trades: bool = False,
    precomputed_signals: list[dict] | None = None,
) -> dict:
    """
    :param config_overrides: 临时覆盖 config 模块属性 (用于网格搜索), 回测结束自动恢复
    :param precomputed_signals: 与 candles 等长的信号序列; 若提供则不再调用策略 generate_signals
    """
    with _config_overrides(config_overrides):
        return _run_backtest_impl(
            candles,
            quiet=quiet,
            strategy=strategy,
            include_equity_curve=include_equity_curve,
            include_trades=include_trades,
            precomputed_signals=precomputed_signals,
        )


def _run_backtest_impl(
    candles: list[dict],
    *,
    quiet: bool,
    strategy: str | None,
    include_equity_curve: bool,
    include_trades: bool = False,
    precomputed_signals: list[dict] | None = None,
) -> dict:
    if len(candles) < MIN_CANDLES_FOR_BACKTEST:
        if not quiet:
            logger.error(
                f"K线数据不足: {len(candles)} 条, 至少需要 {MIN_CANDLES_FOR_BACKTEST} 条"
            )
        return {}

    strat = (strategy or STRATEGY).strip().lower()
    if precomputed_signals is not None:
        if len(precomputed_signals) != len(candles):
            if not quiet:
                logger.error(
                    f"预计算信号条数 {len(precomputed_signals)} 与 K 线 {len(candles)} 不一致"
                )
            return {}
        if not strat:
            strat = "precomputed"

    pos_pct = _position_pct(strat)

    risk: RiskManager | None = None
    if cfg.RISK_ENABLED:
        risk = RiskManager(
            initial_equity=INITIAL_BALANCE,
            max_drawdown_pct=cfg.RISK_MAX_DRAWDOWN_PCT,
            force_flat_on_breach=cfg.RISK_FORCE_FLAT_ON_DRAWDOWN,
            max_position_pct=cfg.RISK_MAX_POSITION_PCT,
        )

    if not quiet:
        logger.info(f"开始回测: {len(candles)} 条K线, {SYMBOL} {TIMEFRAME}")
        logger.info(
            f"策略: {strat}, 初始资金: {INITIAL_BALANCE} USDT, "
            f"目标单笔比例: {pos_pct*100:.0f}% (经风控封顶 {cfg.RISK_MAX_POSITION_PCT*100:.0f}%)"
        )
        if cfg.RISK_ENABLED:
            logger.info(
                f"风控: 最大回撤熔断 {cfg.RISK_MAX_DRAWDOWN_PCT*100:.1f}%, "
                f"触发后{'强制平仓+禁止开仓' if cfg.RISK_FORCE_FLAT_ON_DRAWDOWN else '仅禁止开仓'}"
            )

    exchange = PaperExchange(INITIAL_BALANCE, fee_rate=cfg.FEE_RATE, slippage_bps=cfg.SLIPPAGE_BPS)
    if precomputed_signals is not None:
        signals = precomputed_signals
    else:
        signals = get_signal_fn(strat)(candles)

    buy_price = 0.0
    equity_curve: list[float] = []
    risk_liquidations = 0

    for i, signal in enumerate(signals):
        close_px = candles[i]["close"]
        price = signal["price"]
        bal = exchange.get_balance(close_px)
        equity = bal["total_value"]
        equity_curve.append(equity)

        if risk:
            must_flat = risk.update(equity)
            if must_flat and exchange.coin_balance > 0:
                trade = exchange.sell(SYMBOL, close_px)
                if trade:
                    trade["strategy"] = strat
                    trade["risk_stop"] = True
                    if buy_price > 0:
                        profit = trade["total"] - (trade["amount"] * buy_price)
                        profit_pct = (profit / (trade["amount"] * buy_price)) * 100
                        trade["profit"] = profit
                        trade["profit_pct"] = profit_pct
                    buy_price = 0.0
                    risk_liquidations += 1
                    if not quiet:
                        logger.warning(f"风控强制平仓 @ {close_px:.2f}")

        sig = signal["signal"]
        if sig == "buy" and exchange.coin_balance == 0:
            if risk and not risk.allow_new_buy():
                continue
            eff_pct = pos_pct
            if risk:
                eff_pct = risk.cap_position_pct(pos_pct)
            amount = exchange.usdt_balance * eff_pct
            trade = exchange.buy(SYMBOL, price, amount)
            if trade:
                trade["strategy"] = strat
                buy_price = price

        elif sig == "sell" and exchange.coin_balance > 0:
            trade = exchange.sell(SYMBOL, price)
            if trade:
                trade["strategy"] = strat
                if buy_price > 0:
                    profit = trade["total"] - (trade["amount"] * buy_price)
                    profit_pct = (profit / (trade["amount"] * buy_price)) * 100
                    trade["profit"] = profit
                    trade["profit_pct"] = profit_pct
                    if not quiet:
                        logger.info(
                            f"平仓盈亏: {profit:+.2f} USDT ({profit_pct:+.2f}%)"
                        )
                buy_price = 0.0

    last_price = candles[-1]["close"]
    result = exchange.get_balance(last_price)

    result["backtest_days"] = BACKTEST_DAYS
    result["candles_used"] = len(candles)
    result["first_date"] = datetime.fromtimestamp(candles[0]["timestamp"]).strftime("%Y-%m-%d")
    result["last_date"] = datetime.fromtimestamp(candles[-1]["timestamp"]).strftime("%Y-%m-%d")
    result["total_trades"] = len(exchange.trades)
    result["buy_count"] = sum(1 for t in exchange.trades if t["side"] == "buy")
    result["sell_count"] = sum(1 for t in exchange.trades if t["side"] == "sell")

    sell_trades = [
        t for t in exchange.trades if t["side"] == "sell" and t.get("profit") is not None
    ]
    if sell_trades:
        wins = sum(1 for t in sell_trades if t["profit"] > 0)
        result["win_rate"] = (wins / len(sell_trades)) * 100
        result["avg_profit"] = sum(t["profit"] for t in sell_trades) / len(sell_trades)
        result["max_profit"] = max(t["profit"] for t in sell_trades)
        result["max_loss"] = min(t["profit"] for t in sell_trades)
        gross_profit = sum(t["profit"] for t in sell_trades if t["profit"] > 0)
        gross_loss = sum(t["profit"] for t in sell_trades if t["profit"] < 0)
        result["profit_factor"] = (
            gross_profit / abs(gross_loss) if gross_loss < 0 else float("inf")
        )
    else:
        result["win_rate"] = 0
        result["avg_profit"] = 0
        result["max_profit"] = 0
        result["max_loss"] = 0
        result["profit_factor"] = 0.0

    result["strategy"] = strat
    result["position_pct"] = pos_pct
    result["risk_enabled"] = cfg.RISK_ENABLED
    result["risk_halted"] = risk.halted if risk else False
    result["risk_liquidations"] = risk_liquidations
    result["risk_max_position_pct"] = cfg.RISK_MAX_POSITION_PCT

    rf = float(getattr(cfg, "BACKTEST_RISK_FREE_ANNUAL", 0.0))
    m = compute_performance_metrics(
        equity_curve,
        ts_start=candles[0]["timestamp"],
        ts_end=candles[-1]["timestamp"],
        timeframe=TIMEFRAME,
        total_return_pct=result["profit_pct"],
        rf_annual=rf,
    )
    result["metrics"] = m
    ppy = float(m.get("periods_per_year") or 365.25 * 24)

    sell_profits = [
        float(t["profit"])
        for t in sell_trades
        if t.get("profit") is not None
    ]
    bh_curve = buy_hold_equity_curve(
        candles,
        INITIAL_BALANCE,
        fee_rate=cfg.FEE_RATE,
        slippage_bps=cfg.SLIPPAGE_BPS,
    )
    if bh_curve:
        bh_final = bh_curve[-1]
        bh_profit_pct = (bh_final - INITIAL_BALANCE) / INITIAL_BALANCE * 100.0
        result["benchmark_profit_pct"] = bh_profit_pct
        result["benchmark_final_value"] = bh_final
        bm = compute_performance_metrics(
            bh_curve,
            ts_start=candles[0]["timestamp"],
            ts_end=candles[-1]["timestamp"],
            timeframe=TIMEFRAME,
            total_return_pct=bh_profit_pct,
            rf_annual=rf,
        )
        result["benchmark_metrics"] = bm
        result["alpha_profit_pct"] = result["profit_pct"] - bh_profit_pct
    else:
        result["benchmark_profit_pct"] = float("nan")
        result["benchmark_metrics"] = {}
        result["alpha_profit_pct"] = float("nan")

    result["total_fees_paid"] = sum(float(t.get("fee") or 0) for t in exchange.trades)
    result["slippage_bps_used"] = float(cfg.SLIPPAGE_BPS)
    result["fee_rate_used"] = float(cfg.FEE_RATE)

    bh_for_adv = bh_curve if (bh_curve and len(bh_curve) == len(equity_curve)) else None
    result["advanced"] = compute_advanced_metrics(
        equity_curve,
        benchmark_equity=bh_for_adv,
        sell_trade_profits=sell_profits,
        periods_per_year=ppy,
    )
    result["tca"] = compute_tca_summary(
        exchange.trades,
        INITIAL_BALANCE,
        len(candles),
        periods_per_year=ppy,
    )
    result["kelly_hint"] = kelly_from_sell_trades(sell_profits)

    if include_trades:
        result["trades"] = [dict(t) for t in exchange.trades]

    if include_equity_curve:
        result["equity_curve"] = equity_curve
        if bh_curve:
            result["benchmark_equity_curve"] = bh_curve

    return result


def print_backtest_report(result: dict):
    """打印回测报告"""
    if not result:
        print("回测失败, 无结果")
        return

    m = result.get("metrics") or {}
    sharpe = m.get("sharpe", float("nan"))
    sortino = m.get("sortino", float("nan"))
    calmar = m.get("calmar", float("nan"))
    cagr_pct = m.get("cagr_pct", float("nan"))
    mdd = m.get("max_drawdown_pct", float("nan"))
    ulcer = m.get("ulcer_index", float("nan"))
    omega = m.get("omega", float("nan"))
    ir = (result.get("advanced") or {}).get("information_ratio_vs_bh", float("nan"))
    ddur = (result.get("advanced") or {}).get("max_drawdown_duration_bars", float("nan"))
    pct_uw = (result.get("advanced") or {}).get("pct_bars_under_peak", float("nan"))
    mcl = (result.get("advanced") or {}).get("max_consecutive_losses", float("nan"))
    tca = result.get("tca") or {}
    kelly = result.get("kelly_hint") or {}
    kf = kelly.get("kelly_fraction", float("nan"))
    bh_pct = result.get("benchmark_profit_pct", float("nan"))
    alpha_pct = result.get("alpha_profit_pct", float("nan"))

    def _fmt(x: float) -> str:
        if isinstance(x, float) and math.isnan(x):
            return "   n/a"
        if isinstance(x, float) and math.isinf(x):
            return "     inf"
        return f"{x:>8.2f}"

    lines = [
        "",
        "=" * 55,
        "           回 测 报 告",
        "=" * 55,
        f"  策略:         {result.get('strategy', STRATEGY)}",
        f"  交易对:       {SYMBOL} ({TIMEFRAME})",
        f"  回测区间:     {result['first_date']} ~ {result['last_date']}",
        f"  K线数量:      {result['candles_used']}",
        "-" * 55,
        f"  初始资金:     {result['initial_balance']:>12.2f} USDT",
        f"  最终资产:     {result['total_value']:>12.2f} USDT",
        f"  总盈亏:       {result['profit']:>+12.2f} USDT ({result['profit_pct']:+.2f}%)",
        "-" * 55,
        f"  夏普比率:     {_fmt(sharpe)}",
        f"  索提诺比率:   {_fmt(sortino)}",
        f"  最大回撤:     {_fmt(mdd)} %",
        f"  年化收益:     {_fmt(cagr_pct)} %",
        f"  卡玛比率:     {_fmt(calmar)}",
        f"  Ulcer 指数:   {_fmt(ulcer)}",
        f"  Omega:        {_fmt(omega)}",
        f"  信息比率(vs B&H): {_fmt(ir)}",
        f"  最长回撤期(K线): {_fmt(ddur)}",
        f"  低于峰值K线占比: {_fmt(pct_uw)} %",
        f"  最大连亏笔数:   {_fmt(mcl)}",
        "-" * 55,
        f"  买入持有收益: {_fmt(bh_pct)} %",
        f"  超额(alpha):  {_fmt(alpha_pct)} %  (策略 - 买入持有)",
        f"  累计手续费:   {result.get('total_fees_paid', 0):>12.4f} USDT",
        f"  成交模型:     手续费 {result.get('fee_rate_used', 0)*100:.3f}% + 滑点 {result.get('slippage_bps_used', 0):.1f} bps",
        "-" * 55,
        f"  TCA 成交名义:   {tca.get('gross_traded_notional_usd', 0):>12.2f} USDT",
        f"  费用/成交 bps: {tca.get('fee_bps_on_gross_traded', 0):>12.2f}",
        f"  换手代理/年:   {tca.get('turnover_per_year_proxy', 0):>12.2f}",
        f"  Kelly(半凯利上限25%): {_fmt(kf)}",
        "-" * 55,
        f"  风控启用:     {'是' if result.get('risk_enabled') else '否'}",
        f"  熔断后禁止开仓: {'是' if result.get('risk_halted') else '否'}",
        f"  风控强制平仓次数: {result.get('risk_liquidations', 0)}",
        f"  单笔仓位上限: {result.get('risk_max_position_pct', 0)*100:.0f}%",
        "-" * 55,
        f"  买入次数:     {result['buy_count']:>12d}",
        f"  卖出次数:     {result['sell_count']:>12d}",
        f"  胜率:         {result['win_rate']:>11.1f}%",
        f"  盈亏比(PF):   {result['profit_factor']:>12.2f}",
        f"  平均盈亏:     {result['avg_profit']:>+12.2f} USDT",
        f"  最大单笔盈利: {result['max_profit']:>+12.2f} USDT",
        f"  最大单笔亏损: {result['max_loss']:>+12.2f} USDT",
        "=" * 55,
        "",
    ]
    print("\n".join(lines))
