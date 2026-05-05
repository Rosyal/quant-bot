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
    TRADE_AMOUNT_PCT,
    BACKTEST_DAYS,
    STRATEGY,
    MIN_CANDLES_FOR_BACKTEST,
    RSIMACD_TRADE_AMOUNT_PCT,
    RISK_ENABLED,
    RISK_MAX_DRAWDOWN_PCT,
    RISK_FORCE_FLAT_ON_DRAWDOWN,
    RISK_MAX_POSITION_PCT,
)
from exchange.paper import PaperExchange
from strategy import get_signal_fn
from risk.manager import RiskManager
from backtest.metrics import compute_performance_metrics

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
        return RSIMACD_TRADE_AMOUNT_PCT
    return TRADE_AMOUNT_PCT


def run_backtest(
    candles: list[dict],
    *,
    quiet: bool = False,
    strategy: str | None = None,
    config_overrides: dict[str, Any] | None = None,
    include_equity_curve: bool = False,
) -> dict:
    """
    :param config_overrides: 临时覆盖 config 模块属性 (用于网格搜索), 回测结束自动恢复
    """
    with _config_overrides(config_overrides):
        return _run_backtest_impl(
            candles,
            quiet=quiet,
            strategy=strategy,
            include_equity_curve=include_equity_curve,
        )


def _run_backtest_impl(
    candles: list[dict],
    *,
    quiet: bool,
    strategy: str | None,
    include_equity_curve: bool,
) -> dict:
    if len(candles) < MIN_CANDLES_FOR_BACKTEST:
        if not quiet:
            logger.error(
                f"K线数据不足: {len(candles)} 条, 至少需要 {MIN_CANDLES_FOR_BACKTEST} 条"
            )
        return {}

    strat = (strategy or STRATEGY).strip().lower()
    pos_pct = _position_pct(strat)

    risk: RiskManager | None = None
    if RISK_ENABLED:
        risk = RiskManager(
            initial_equity=INITIAL_BALANCE,
            max_drawdown_pct=RISK_MAX_DRAWDOWN_PCT,
            force_flat_on_breach=RISK_FORCE_FLAT_ON_DRAWDOWN,
            max_position_pct=RISK_MAX_POSITION_PCT,
        )

    if not quiet:
        logger.info(f"开始回测: {len(candles)} 条K线, {SYMBOL} {TIMEFRAME}")
        logger.info(
            f"策略: {strat}, 初始资金: {INITIAL_BALANCE} USDT, "
            f"目标单笔比例: {pos_pct*100:.0f}% (经风控封顶 {RISK_MAX_POSITION_PCT*100:.0f}%)"
        )
        if RISK_ENABLED:
            logger.info(
                f"风控: 最大回撤熔断 {RISK_MAX_DRAWDOWN_PCT*100:.1f}%, "
                f"触发后{'强制平仓+禁止开仓' if RISK_FORCE_FLAT_ON_DRAWDOWN else '仅禁止开仓'}"
            )

    exchange = PaperExchange(INITIAL_BALANCE)
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
    result["risk_enabled"] = RISK_ENABLED
    result["risk_halted"] = risk.halted if risk else False
    result["risk_liquidations"] = risk_liquidations
    result["risk_max_position_pct"] = RISK_MAX_POSITION_PCT

    m = compute_performance_metrics(
        equity_curve,
        ts_start=candles[0]["timestamp"],
        ts_end=candles[-1]["timestamp"],
        timeframe=TIMEFRAME,
        total_return_pct=result["profit_pct"],
    )
    result["metrics"] = m
    if include_equity_curve:
        result["equity_curve"] = equity_curve

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

    def _fmt(x: float) -> str:
        if isinstance(x, float) and math.isnan(x):
            return "   n/a"
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
