"""
实盘信号轮询 (REST 拉取, 无需 ccxt.pro)

定时拉取最近 N 根 K 线 → 生成信号 → 与上次状态对比 → Webhook 推送。
不下单, 仅告警 (下单归后续实盘模块)。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

from config import (
    SYMBOLS,
    TIMEFRAME,
    STRATEGY,
    LIVE_POLL_INTERVAL_SEC,
    LIVE_LOOKBACK_BARS,
    LIVE_STATE_PATH,
    FEISHU_WEBHOOK_URL,
    GENERIC_WEBHOOK_URL,
)
from data_fetcher import fetch_ohlcv_ccxt_latest, generate_mock_data
from strategy import get_signal_fn
from notifications.webhook import notify_text
from utils.logger import get_logger

logger = get_logger("live")


def _load_state() -> dict:
    if not os.path.isfile(LIVE_STATE_PATH):
        return {}
    try:
        with open(LIVE_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(LIVE_STATE_PATH) or ".", exist_ok=True)
    with open(LIVE_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=0)


def _state_key(symbol: str, strategy: str) -> str:
    return f"{symbol}|{strategy}"


def run_live_polling(
    *,
    use_mock: bool = False,
    once: bool = False,
    strategy: str | None = None,
    symbols: list[str] | None = None,
) -> None:
    strat = (strategy or STRATEGY).strip().lower()
    syms = list(symbols) if symbols else list(SYMBOLS)
    sig_fn = get_signal_fn(strat)
    state = _load_state()

    logger.info(
        f"Live 轮询启动: 品种={syms}, 周期={TIMEFRAME}, 策略={strat}, "
        f"间隔={LIVE_POLL_INTERVAL_SEC}s, mock={use_mock}"
    )

    while True:
        for symbol in syms:
            if use_mock:
                candles = generate_mock_data(
                    45,
                    seed=(int(time.time()) // LIVE_POLL_INTERVAL_SEC) % 100000,
                    silent=True,
                )
            else:
                candles = fetch_ohlcv_ccxt_latest(
                    symbol, TIMEFRAME, limit=LIVE_LOOKBACK_BARS
                )
            if len(candles) < 10:
                logger.warning(f"{symbol} K 线不足, 跳过")
                continue

            signals = sig_fn(candles)
            last = signals[-1]
            sig = last.get("signal", "hold")
            price = last.get("price", candles[-1]["close"])
            key = _state_key(symbol, strat)
            prev = state.get(key)

            if sig in ("buy", "sell") and sig != prev:
                ts = datetime.utcfromtimestamp(candles[-1]["timestamp"]).strftime(
                    "%Y-%m-%d %H:%M UTC"
                )
                msg = (
                    f"[量化信号] {symbol} {TIMEFRAME}\n"
                    f"策略: {strat}\n"
                    f"信号: {sig.upper()}\n"
                    f"收盘价: {price:.4f}\n"
                    f"K线时间: {ts}\n"
                    f"(仅提示, 未自动下单)"
                )
                notify_text(
                    msg,
                    feishu_url=FEISHU_WEBHOOK_URL,
                    generic_url=GENERIC_WEBHOOK_URL,
                )
                state[key] = sig
                logger.info(f"{symbol} 新信号: {sig} @ {price}")
            elif sig == "hold" and prev in ("buy", "sell"):
                state[key] = "hold"

        _save_state(state)

        if once:
            break
        time.sleep(LIVE_POLL_INTERVAL_SEC)
