"""
横截面因子库 (轻量)

- 动量: N 根收益累乘
- 波动: 收益标准差
- 横截面 z-score 排名 (去截面均值/标准差)

数据对齐: 仅保留各品种共有时间戳。非因子投资承诺。
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from db.database import Database


def align_closes_on_timestamps(
    series: dict[str, list[dict]],
) -> tuple[list[int], dict[str, np.ndarray]]:
    """
    series[symbol] = get_ohlcv 结果 (时间升序)。
    返回共有 timestamp 列表与每个品种对齐后的 close 向量 (与 ts 同长)。
    """
    if not series:
        return [], {}
    sets = []
    by_ts: dict[str, dict[int, float]] = {}
    for sym, rows in series.items():
        d = {int(r["timestamp"]): float(r["close"]) for r in rows}
        by_ts[sym] = d
        sets.append(set(d.keys()))
    common = sorted(set.intersection(*sets)) if sets else []
    out: dict[str, np.ndarray] = {}
    for sym in series:
        out[sym] = np.array([by_ts[sym][t] for t in common], dtype=float)
    return common, out


def momentum_raw(closes: np.ndarray, lookback: int) -> float:
    """单序列动量: close[-1]/close[-1-lookback] - 1"""
    if len(closes) <= lookback or lookback < 1:
        return float("nan")
    a = closes[-1 - lookback]
    b = closes[-1]
    if a <= 0:
        return float("nan")
    return b / a - 1.0


def realized_vol(closes: np.ndarray, window: int) -> float:
    if len(closes) <= window + 1:
        return float("nan")
    seg = closes[-window - 1 :]
    r = seg[1:] / seg[:-1] - 1.0
    return float(np.std(r, ddof=1))


def cross_section_zscores(values: dict[str, float]) -> dict[str, float]:
    """横截面 z-score; 无效值或方差过小记为 0"""
    syms = [k for k, v in values.items() if np.isfinite(v)]
    out: dict[str, float] = {k: 0.0 for k in values}
    if len(syms) < 2:
        return out
    x = np.array([values[s] for s in syms], dtype=float)
    mu = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    if sd < 1e-12:
        return out
    for s in syms:
        out[s] = float((values[s] - mu) / sd)
    return out


def load_close_panel_from_db(
    db: Database,
    symbols: Sequence[str],
    timeframe: str,
    limit: int,
) -> tuple[list[int], dict[str, np.ndarray]]:
    raw = {}
    for sym in symbols:
        rows = db.get_ohlcv(sym, timeframe, limit=limit)
        if len(rows) < 10:
            continue
        raw[sym] = rows
    return align_closes_on_timestamps(raw)


def snapshot_factors(
    close_panel: dict[str, np.ndarray],
    *,
    mom_lookback: int = 20,
    vol_window: int = 20,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
    """
    对当前截面最后一根, 计算动量/波动及其 z-score。
    """
    mom: dict[str, float] = {}
    vol: dict[str, float] = {}
    for sym, c in close_panel.items():
        mom[sym] = momentum_raw(c, mom_lookback)
        vol[sym] = realized_vol(c, vol_window)
    z_mom = cross_section_zscores(mom)
    z_vol = cross_section_zscores(vol)
    return mom, vol, z_mom, z_vol
