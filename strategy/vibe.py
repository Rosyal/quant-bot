"""
VIBE 复合策略 (参考业界常见的多因子共振思路)

- V — Volatility: ATR/收盘价 过滤极端静默/极端剧烈行情
- I — Indicators: RSI 超卖/超买 + 均线趋势过滤
- B — Bands: 布林带下沿低吸、中轨/上沿止盈
- E — Entry: 仅在趋势多头背景下做均值回归入场

说明: 「高胜率」往往伴随盈亏比下降或样本过拟合; 实盘与回测可能差异很大。
"""
from __future__ import annotations

from utils.logger import get_logger
from config import (
    VIBE_MA_FAST,
    VIBE_MA_SLOW,
    VIBE_MA_TREND,
    VIBE_RSI_PERIOD,
    VIBE_RSI_BUY,
    VIBE_RSI_SELL,
    VIBE_BB_PERIOD,
    VIBE_BB_STD,
    VIBE_ATR_PERIOD,
    VIBE_ATR_MIN_PCT,
    VIBE_ATR_MAX_PCT,
    VIBE_STOP_ATR_MULT,
    VIBE_BB_LOWER_SLACK,
    VIBE_MIN_EXIT_GAIN,
    VIBE_TP_PCT,
    VIBE_TREND_MA_SOFT,
    VIBE_TREND_RELAX_RSI,
    VIBE_TREND_MA_BUFFER,
)
from strategy.indicators import sma, rsi, bollinger_bands, atr

logger = get_logger("strategy.vibe")


def generate_signals(candles: list[dict]) -> list[dict]:
    closes = [c["close"] for c in candles]
    ma_f = sma(closes, VIBE_MA_FAST)
    ma_s = sma(closes, VIBE_MA_SLOW)
    ma_t = sma(closes, VIBE_MA_TREND)
    rsi_vals = rsi(closes, VIBE_RSI_PERIOD)
    mid, upper, lower = bollinger_bands(closes, VIBE_BB_PERIOD, VIBE_BB_STD)
    atr_vals = atr(candles, VIBE_ATR_PERIOD)

    signals: list[dict] = []
    in_long = False
    entry_price = 0.0

    for i, candle in enumerate(candles):
        c = candle["close"]
        mf, ms, mt = ma_f[i], ma_s[i], ma_t[i]
        r = rsi_vals[i]
        mbb, up, lo = mid[i], upper[i], lower[i]
        at = atr_vals[i]

        base = {
            "timestamp": candle["timestamp"],
            "signal": "hold",
            "price": c,
            "rsi": round(r, 2) if r is not None else None,
        }

        if mf is None or ms is None or mt is None or r is None:
            signals.append(base)
            continue
        if mbb is None or up is None or lo is None or at is None or at <= 0:
            signals.append(base)
            continue

        vol_pct = at / c if c else 0.0
        trend_normal = c >= mt * VIBE_TREND_MA_SOFT
        trend_relaxed = r <= VIBE_TREND_RELAX_RSI and c >= mt * VIBE_TREND_MA_BUFFER
        trend_ok = mf > ms and (trend_normal or trend_relaxed)
        vol_ok = VIBE_ATR_MIN_PCT <= vol_pct <= VIBE_ATR_MAX_PCT

        sig = "hold"

        if in_long:
            stop = entry_price - VIBE_STOP_ATR_MULT * at
            gain_ok = c >= entry_price * (1.0 + VIBE_MIN_EXIT_GAIN)
            hit_tp = c >= entry_price * (1.0 + VIBE_TP_PCT)
            take_mid = c >= mbb and gain_ok
            take_rsi = r >= VIBE_RSI_SELL and c > lo and gain_ok
            take_upper = c >= up * 0.999 and gain_ok
            stopped = c <= stop

            if stopped:
                sig = "sell"
                in_long = False
                logger.info(
                    f"VIBE 止损 @ {c:.2f} (入场 {entry_price:.2f}, ATR={at:.2f})"
                )
            elif hit_tp or take_upper or take_rsi or take_mid:
                sig = "sell"
                in_long = False
                logger.info(f"VIBE 止盈/离场 @ {c:.2f} RSI={r:.1f}")
        else:
            touch_lower = c <= lo * VIBE_BB_LOWER_SLACK
            dip = r <= VIBE_RSI_BUY
            if trend_ok and vol_ok and dip and touch_lower:
                sig = "buy"
                in_long = True
                entry_price = c
                logger.info(
                    f"VIBE 入场 @ {c:.2f} RSI={r:.1f} 下轨={lo:.2f} "
                    f"趋势 MA{VIBE_MA_FAST}>{VIBE_MA_SLOW}"
                )

        row = {**base, "signal": sig}
        signals.append(row)

    return signals
