"""
纸面实盘模拟: 定时拉取 K 线 → 策略信号 → 模拟买卖 → 持久化权益曲线

与 `live` 区别: 本会真实改动本地 PaperPortfolio (不下交易所单)。
"""
from __future__ import annotations

import time

import config as cfg
from config import (
    SYMBOLS,
    TIMEFRAME,
    STRATEGY,
    PAPER_LIVE_INTERVAL_SEC,
    PAPER_LIVE_LOOKBACK_BARS,
    PAPER_TRADE_AMOUNT_PCT,
)
from db.database import Database
from data_fetcher import fetch_ohlcv_latest, generate_mock_data
from exchange.paper_portfolio import PaperPortfolio
from notifications.channels import notify_all_from_config
from news.assist import append_news_digest_to_message
from strategy import get_signal_fn
from utils.logger import get_logger

logger = get_logger("paper_live")


def _state_key(symbol: str, strategy: str) -> str:
    return f"{symbol}|{strategy}"


def _gross_exposure_and_symbol_nv(
    positions: dict[str, float],
    last_prices: dict[str, float],
    symbol: str,
) -> tuple[float, float]:
    notionals: dict[str, float] = {}
    for sym, qty in positions.items():
        q = float(qty)
        if q <= 0:
            continue
        px = last_prices.get(sym)
        if px:
            notionals[sym] = q * px
    gross = sum(abs(v) for v in notionals.values())
    return gross, float(notionals.get(symbol, 0.0))


def run_paper_live(
    *,
    use_mock: bool = False,
    once: bool = False,
    strategy: str | None = None,
    symbols: list[str] | None = None,
) -> None:
    strat = (strategy or STRATEGY).strip().lower()
    syms = list(symbols) if symbols else list(SYMBOLS)
    sig_fn = get_signal_fn(strat)
    pf = PaperPortfolio()
    chain_db: Database | None = None
    if getattr(cfg, "FULL_CHAIN_PAPER_LIVE", False):
        chain_db = Database()
        logger.info("已启用 FULL_CHAIN_PAPER_LIVE: 买入前走 desk 全链路 (规则+路由+EMS+审计)")

    logger.info(
        f"纸面实盘启动: 品种={syms}, 周期={TIMEFRAME}, 策略={strat}, "
        f"间隔={PAPER_LIVE_INTERVAL_SEC}s, mock={use_mock}"
    )

    try:
        while True:
            last_prices: dict[str, float] = {}
            candles_by_symbol: dict[str, list] = {}
            for symbol in syms:
                if use_mock:
                    candles = generate_mock_data(
                        45,
                        seed=(
                            abs(hash(symbol))
                            + int(time.time()) // max(1, PAPER_LIVE_INTERVAL_SEC)
                        )
                        % 100000,
                        silent=True,
                    )
                else:
                    candles = fetch_ohlcv_latest(
                        symbol, TIMEFRAME, limit=PAPER_LIVE_LOOKBACK_BARS
                    )
                if len(candles) < 10:
                    logger.warning(f"{symbol} K 线不足, 跳过")
                    continue
                price = float(candles[-1]["close"])
                last_prices[symbol] = price
                candles_by_symbol[symbol] = candles

            for symbol, candles in candles_by_symbol.items():
                price = last_prices[symbol]

                signals = sig_fn(candles)
                last = signals[-1]
                sig = last.get("signal", "hold")
                key = _state_key(symbol, strat)
                prev = pf.last_signals.get(key)

                if sig == "buy" and sig != prev:
                    if pf.position_qty(symbol) <= 0:
                        eq = pf.total_equity(last_prices)
                        spend = eq * PAPER_TRADE_AMOUNT_PCT
                        if chain_db is not None:
                            from desk.pipeline import (
                                PipelineContext,
                                run_order_pipeline,
                            )
                            from security.permissions import default_role_from_env

                            gross, sym_nv = _gross_exposure_and_symbol_nv(
                                pf.positions, last_prices, symbol
                            )
                            bypass = getattr(
                                cfg, "FULL_CHAIN_PAPER_BYPASS_APPROVAL", True
                            )
                            pr = run_order_pipeline(
                                PipelineContext(
                                    symbol=symbol,
                                    side="buy",
                                    notional_usdt=spend,
                                    mid=price,
                                    actor="paper_live",
                                    role=default_role_from_env(),
                                    force=bypass,
                                    gross_exposure_usd=gross,
                                    equity_usdt=eq,
                                    symbol_notional_usd=sym_nv,
                                ),
                                chain_db,
                            )
                            if not pr.ok:
                                logger.warning(
                                    f"全链路拦截买入 {symbol}: {pr.message}"
                                )
                                continue
                        tr = pf.buy(symbol, price, spend, strat)
                        if tr:
                            eq2 = pf.total_equity(last_prices)
                            msg = (
                                f"[纸面买入] {symbol} {TIMEFRAME}\n"
                                f"策略: {strat}\n"
                                f"价: {price:.4f} 名义≈{spend:.2f} USDT\n"
                                f"权益≈{eq2:.2f}"
                            )
                            msg = append_news_digest_to_message(msg, paper=True)
                            notify_all_from_config(
                                msg, title="Quant 纸面实盘"
                            )
                    pf.last_signals[key] = "buy"
                elif sig == "sell" and sig != prev:
                    if pf.position_qty(symbol) > 0:
                        tr = pf.sell_all(symbol, price, strat)
                        if tr:
                            eq2 = pf.total_equity(last_prices)
                            msg = (
                                f"[纸面卖出] {symbol} {TIMEFRAME}\n"
                                f"策略: {strat}\n"
                                f"价: {price:.4f}\n"
                                f"权益≈{eq2:.2f}"
                            )
                            msg = append_news_digest_to_message(msg, paper=True)
                            notify_all_from_config(
                                msg, title="Quant 纸面实盘"
                            )
                    pf.last_signals[key] = "sell"
                elif sig == "hold" and prev in ("buy", "sell"):
                    pf.last_signals[key] = "hold"

            ts = int(time.time())
            if last_prices:
                pf.record_equity(ts, last_prices)
            pf.save()

            if once:
                break
            time.sleep(PAPER_LIVE_INTERVAL_SEC)
    finally:
        if chain_db is not None:
            chain_db.close()
