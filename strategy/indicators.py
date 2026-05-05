"""
技术指标 (纯 Python, 无 pandas 依赖)
用于多策略复用
"""
from __future__ import annotations


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i < period - 1:
            out.append(None)
        else:
            out.append(sum(values[i - period + 1 : i + 1]) / period)
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    """指数移动平均"""
    if not values or period < 1:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    out: list[float | None] = [None] * len(values)
    # 首值用 SMA
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Wilder RSI"""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out

    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        gains[i] = max(d, 0.0)
        losses[i] = max(-d, 0.0)

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def bollinger_bands(
    closes: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """中轨(SMA)、上轨、下轨"""
    mid = sma(closes, period)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        m = mid[i]
        if m is None:
            continue
        start = i - period + 1
        window = closes[start : i + 1]
        mean = m
        var = sum((x - mean) ** 2 for x in window) / period
        sd = var**0.5
        upper[i] = mean + num_std * sd
        lower[i] = mean - num_std * sd
    return mid, upper, lower


def atr(candles: list[dict], period: int = 14) -> list[float | None]:
    """平均真实波幅 (Wilder 平滑)"""
    n = len(candles)
    out: list[float | None] = [None] * n
    if n < 2:
        return out

    tr: list[float] = []
    for i in range(n):
        h, l = candles[i]["high"], candles[i]["low"]
        if i == 0:
            tr.append(h - l)
        else:
            pc = candles[i - 1]["close"]
            tr.append(max(h - l, abs(h - pc), abs(l - pc)))

    if n < period:
        return out

    first = sum(tr[:period]) / period
    out[period - 1] = first
    prev = first
    for i in range(period, n):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def macd(
    closes: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD 线、信号线、柱状图 (线 - 信号)"""
    n = len(closes)
    if n == 0:
        return [], [], []

    ef = ema(closes, fast_period)
    es = ema(closes, slow_period)
    line: list[float | None] = [None] * n
    for i in range(n):
        if ef[i] is not None and es[i] is not None:
            line[i] = ef[i] - es[i]

    first = next((i for i in range(n) if line[i] is not None), None)
    if first is None:
        return line, [None] * n, [None] * n

    macd_seq = [line[i] for i in range(first, n)]
    sig_seq = ema(macd_seq, signal_period)
    signal: list[float | None] = [None] * n
    hist: list[float | None] = [None] * n
    for j in range(len(macd_seq)):
        idx = first + j
        signal[idx] = sig_seq[j]
        if sig_seq[j] is not None:
            hist[idx] = macd_seq[j] - sig_seq[j]
    return line, signal, hist
