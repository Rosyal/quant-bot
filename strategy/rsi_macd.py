"""
RSI + MACD 趋势策略

- 入场: MACD 金叉 + RSI 处于回调区(避免追高) + 价格在均线上方
- 出场: 固定止盈、ATR 止损、MACD 死叉或 RSI 超买(均需满足最小浮盈)

偏趋势跟踪, 在强趋势中通常比纯均值回归更易做出总收益; 通过 RSI 区间与 min_exit 约束胜率。
"""
from __future__ import annotations

from utils.logger import get_logger
from config import (
    RSIMACD_FAST,
    RSIMACD_SLOW,
    RSIMACD_SIGNAL,
    RSIMACD_RSI_PERIOD,
    RSIMACD_RSI_LOW,
    RSIMACD_RSI_HIGH,
    RSIMACD_RSI_MOM_MAX,
    RSIMACD_RSI_SELL,
    RSIMACD_MA_TREND,
    RSIMACD_MA_SOFT,
    RSIMACD_ATR_PERIOD,
    RSIMACD_STOP_ATR_MULT,
    RSIMACD_MIN_EXIT_GAIN,
    RSIMACD_TP_PCT,
)
from strategy.indicators import sma, rsi, macd, atr

logger = get_logger("strategy.rsi_macd")


def generate_signals(candles: list[dict]) -> list[dict]:
    closes = [c["close"] for c in candles]
    ma_t = sma(closes, RSIMACD_MA_TREND)
    rsi_vals = rsi(closes, RSIMACD_RSI_PERIOD)
    m_line, s_line, hist = macd(closes, RSIMACD_FAST, RSIMACD_SLOW, RSIMACD_SIGNAL)
    atr_vals = atr(candles, RSIMACD_ATR_PERIOD)

    signals: list[dict] = []
    in_long = False
    entry_price = 0.0
    prev_m: float | None = None
    prev_s: float | None = None

    for i, candle in enumerate(candles):
        c = candle["close"]
        mt = ma_t[i]
        r = rsi_vals[i]
        m = m_line[i]
        s = s_line[i]
        h0 = hist[i]
        at = atr_vals[i]

        row = {
            "timestamp": candle["timestamp"],
            "signal": "hold",
            "price": c,
            "rsi": round(r, 2) if r is not None else None,
        }

        if mt is None or r is None or m is None or s is None or at is None or at <= 0:
            signals.append(row)
            prev_m, prev_s = m, s
            continue

        golden = (
            prev_m is not None
            and prev_s is not None
            and prev_m <= prev_s
            and m > s
        )
        death = (
            prev_m is not None
            and prev_s is not None
            and prev_m >= prev_s
            and m < s
        )

        pullback = RSIMACD_RSI_LOW <= r <= RSIMACD_RSI_HIGH
        above_trend = c > mt * RSIMACD_MA_SOFT

        # 柱线走强(不要求已在零轴上方, 适配更多行情)
        hist_up = False
        if i >= 1 and h0 is not None:
            hm1 = hist[i - 1]
            if hm1 is not None:
                hist_up = h0 > hm1

        macd_momentum = m > s and hist_up

        sig = "hold"

        if in_long:
            stop = entry_price - RSIMACD_STOP_ATR_MULT * at
            gain_ok = c >= entry_price * (1.0 + RSIMACD_MIN_EXIT_GAIN)
            hit_tp = c >= entry_price * (1.0 + RSIMACD_TP_PCT)
            stopped = c <= stop

            if stopped:
                sig = "sell"
                in_long = False
                logger.info(
                    f"RSI/MACD 止损 @ {c:.2f} (入场 {entry_price:.2f}, ATR={at:.2f})"
                )
            elif hit_tp or (death and gain_ok) or (r >= RSIMACD_RSI_SELL and gain_ok):
                sig = "sell"
                in_long = False
                logger.info(f"RSI/MACD 离场 @ {c:.2f} RSI={r:.1f} MACD死叉={death}")
        else:
            gold_ok = golden and pullback and above_trend
            mom_ok = (
                macd_momentum
                and above_trend
                and RSIMACD_RSI_LOW <= r <= RSIMACD_RSI_MOM_MAX
            )
            enter = gold_ok or mom_ok
            if enter:
                sig = "buy"
                in_long = True
                entry_price = c
                tag = "金叉" if gold_ok else "动能"
                logger.info(
                    f"RSI/MACD 入场({tag}) @ {c:.2f} RSI={r:.1f} MA{RSIMACD_MA_TREND}"
                )

        signals.append({**row, "signal": sig})
        prev_m, prev_s = m, s

    return signals
