"""
绩效指标: 夏普、索提诺、最大回撤、卡玛、年化 (基于权益曲线)
"""
from __future__ import annotations

import math
from statistics import mean


def _periods_per_year(timeframe: str) -> float:
    tf = (timeframe or "1h").strip().lower()
    table = {
        "1m": 365.25 * 24 * 60,
        "5m": 365.25 * 24 * 12,
        "15m": 365.25 * 24 * 4,
        "1h": 365.25 * 24,
        "4h": 365.25 * 6,
        "1d": 365.25,
    }
    return table.get(tf, 365.25 * 24)


def max_drawdown(equity: list[float]) -> float:
    """最大回撤 (正数, 如 0.15 表示 15%)"""
    if not equity:
        return 0.0
    peak = equity[0]
    mdd = 0.0
    for x in equity:
        peak = max(peak, x)
        if peak > 0:
            mdd = max(mdd, (peak - x) / peak)
    return mdd


def _simple_returns(equity: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(equity)):
        p = equity[i - 1]
        if p and p > 0:
            out.append(equity[i] / p - 1.0)
    return out


def sharpe_ratio(returns: list[float], periods_per_year: float, rf_annual: float = 0.0) -> float:
    """年化夏普; rf_annual 为无风险年化利率"""
    if len(returns) < 3:
        return float("nan")
    rf_p = (1.0 + rf_annual) ** (1.0 / periods_per_year) - 1.0
    ex = [r - rf_p for r in returns]
    mu = mean(ex)
    var = sum((x - mu) ** 2 for x in ex) / (len(ex) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd < 1e-12:
        return float("nan")
    return (mu / sd) * math.sqrt(periods_per_year)


def sortino_ratio(
    returns: list[float],
    periods_per_year: float,
    mar: float = 0.0,
) -> float:
    """年化索提诺 (下行波动以全样本均值为参照的简化 MAR)"""
    if len(returns) < 3:
        return float("nan")
    mu = mean(returns)
    downside_sq = [min(0.0, r - mar) ** 2 for r in returns]
    ds = mean(downside_sq) if downside_sq else 0.0
    dsd = math.sqrt(ds) if ds > 0 else 0.0
    if dsd < 1e-12:
        return float("nan")
    return (mu / dsd) * math.sqrt(periods_per_year)


def cagr(total_return_pct: float, years: float) -> float:
    """由总收益率与年数推算几何年化 (小数, 如 0.12=12%)"""
    if years <= 0 or total_return_pct <= -100:
        return float("nan")
    r = 1.0 + total_return_pct / 100.0
    if r <= 0:
        return float("nan")
    return r ** (1.0 / years) - 1.0


def calmar_ratio(cagr_decimal: float, max_dd: float) -> float:
    if max_dd < 1e-9 or math.isnan(cagr_decimal):
        return float("nan")
    return cagr_decimal / max_dd


def compute_performance_metrics(
    equity: list[float],
    *,
    ts_start: int,
    ts_end: int,
    timeframe: str,
    total_return_pct: float,
) -> dict[str, float]:
    ppy = _periods_per_year(timeframe)
    years = (ts_end - ts_start) / (365.25 * 24 * 3600)
    mdd = max_drawdown(equity)
    rets = _simple_returns(equity)
    sharpe = sharpe_ratio(rets, ppy)
    sortino = sortino_ratio(rets, ppy)
    cagr_dec = cagr(total_return_pct, years) if years > 0 else float("nan")
    calmar = calmar_ratio(cagr_dec, mdd)

    return {
        "max_drawdown_pct": mdd * 100.0,
        "sharpe": sharpe,
        "sortino": sortino,
        "cagr_pct": cagr_dec * 100.0 if not math.isnan(cagr_dec) else float("nan"),
        "calmar": calmar,
        "years": years,
        "periods_per_year": ppy,
    }
