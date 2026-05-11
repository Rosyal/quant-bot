"""
扩展技术指标 — 统一以 **candles: list[dict]** 为输入（含 high/low/close；OBV 需 volume 或回退为 1）。

函数顺序: **ADX** → **Williams %R** → **OBV** → **Stochastic**（随机指标接受整段 `candles`，**不是**三个独立 high/low/close 序列）。
"""
from __future__ import annotations


def _true_ranges(candles: list[dict]) -> list[float]:
    tr: list[float] = []
    for i, c in enumerate(candles):
        h, l = float(c["high"]), float(c["low"])
        if i == 0:
            tr.append(h - l)
        else:
            pc = float(candles[i - 1]["close"])
            tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return tr


def _wilder_cumulative(series: list[float], period: int) -> list[float | None]:
    """Wilder 平滑: 首值 = 前 period 项和; 其后 S[i]=S[i-1]-S[i-1]/p+series[i]。"""
    n = len(series)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    out[period - 1] = sum(series[:period])
    for i in range(period, n):
        prev = out[i - 1]
        assert prev is not None
        out[i] = prev - (prev / period) + series[i]
    return out


def adx(
    candles: list[dict],
    period: int = 14,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """
    ADX 与 +DI / -DI。
    返回 (adx, plus_di, minus_di)，与 candles 等长。
    """
    n = len(candles)
    nan3 = ([None] * n, [None] * n, [None] * n)
    if n < period + 1:
        return nan3

    tr = _true_ranges(candles)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up = float(candles[i]["high"]) - float(candles[i - 1]["high"])
        down = float(candles[i - 1]["low"]) - float(candles[i]["low"])
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0

    tr_s = _wilder_cumulative(tr, period)
    pdm_s = _wilder_cumulative(plus_dm, period)
    mdm_s = _wilder_cumulative(minus_dm, period)

    pdi_out: list[float | None] = [None] * n
    mdi_out: list[float | None] = [None] * n
    dx_series: list[float] = []
    dx_idx: list[int] = []

    for i in range(n):
        ts, psm, msm = tr_s[i], pdm_s[i], mdm_s[i]
        if ts is None or psm is None or msm is None or ts < 1e-12:
            continue
        pdi = 100.0 * psm / ts
        mdi = 100.0 * msm / ts
        pdi_out[i] = pdi
        mdi_out[i] = mdi
        denom = pdi + mdi
        if denom < 1e-12:
            continue
        dx_series.append(100.0 * abs(pdi - mdi) / denom)
        dx_idx.append(i)

    adx_out: list[float | None] = [None] * n
    if len(dx_series) < period:
        return adx_out, pdi_out, mdi_out

    sm = _wilder_cumulative(dx_series, period)
    for j, bar_i in enumerate(dx_idx):
        adx_out[bar_i] = sm[j]

    return adx_out, pdi_out, mdi_out


def _rolling_min_max(
    candles: list[dict], period: int
) -> tuple[list[float | None], list[float | None]]:
    n = len(candles)
    lo: list[float | None] = [None] * n
    hi: list[float | None] = [None] * n
    for i in range(n):
        if i < period - 1:
            continue
        lows = [float(candles[j]["low"]) for j in range(i - period + 1, i + 1)]
        highs = [float(candles[j]["high"]) for j in range(i - period + 1, i + 1)]
        lo[i] = min(lows)
        hi[i] = max(highs)
    return lo, hi


def williams_r(candles: list[dict], period: int = 14) -> list[float | None]:
    """Williams %R，约 [-100, 0]。"""
    n = len(candles)
    out: list[float | None] = [None] * n
    lo_w, hi_w = _rolling_min_max(candles, period)
    for i in range(n):
        if lo_w[i] is None or hi_w[i] is None:
            continue
        hh, ll = hi_w[i], lo_w[i]  # type: ignore[assignment]
        c = float(candles[i]["close"])
        span = hh - ll
        out[i] = -50.0 if span < 1e-12 else -100.0 * (hh - c) / span
    return out


def obv(candles: list[dict]) -> list[float]:
    """OBV；无 `volume` 时按 1.0 计。"""
    if not candles:
        return []
    out = [0.0] * len(candles)
    prev_close = float(candles[0]["close"])
    for i in range(1, len(candles)):
        c = float(candles[i]["close"])
        vol = float(candles[i].get("volume", 1.0) or 1.0)
        if c > prev_close:
            out[i] = out[i - 1] + vol
        elif c < prev_close:
            out[i] = out[i - 1] - vol
        else:
            out[i] = out[i - 1]
        prev_close = c
    return out


def stochastic(
    candles: list[dict],
    k_period: int = 14,
    slowing: int = 3,
    d_period: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    """
    随机指标 %K / %D（慢随机：FastK → slowing 均化得 %K → d_period 均化得 %D）。

    **参数**: `candles` — 每项需含 `high` / `low` / `close`。
    """
    n = len(candles)
    fast_k: list[float | None] = [None] * n
    lo_w, hi_w = _rolling_min_max(candles, k_period)
    for i in range(n):
        if lo_w[i] is None or hi_w[i] is None:
            continue
        hh, ll = hi_w[i], lo_w[i]
        c = float(candles[i]["close"])
        span = hh - ll
        fast_k[i] = 50.0 if span < 1e-12 else 100.0 * (c - ll) / span

    pct_k: list[float | None] = [None] * n
    for i in range(n):
        if i < k_period - 1 + slowing - 1:
            continue
        chunk = [fast_k[j] for j in range(i - slowing + 1, i + 1)]
        if any(x is None for x in chunk):
            continue
        pct_k[i] = sum(chunk) / slowing  # type: ignore[arg-type]

    pct_d: list[float | None] = [None] * n
    start_d = k_period + slowing + d_period - 3
    for i in range(start_d, n):
        ks = [pct_k[j] for j in range(i - d_period + 1, i + 1)]
        if any(x is None for x in ks):
            continue
        pct_d[i] = sum(ks) / d_period  # type: ignore[arg-type]

    return pct_k, pct_d
