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


def ulcer_index(equity: list[float]) -> float:
    """
    Ulcer Index (Martin): 对百分比回撤平方均值再开方, 越小越好。
    与最大回撤互补, 惩罚持续浅回撤。
    """
    if not equity:
        return float("nan")
    peak = equity[0]
    acc = 0.0
    n = len(equity)
    for x in equity:
        peak = max(peak, x)
        if peak > 0:
            pct_dd = 100.0 * (peak - x) / peak
            acc += pct_dd * pct_dd
    return math.sqrt(acc / n)


def omega_ratio(returns: list[float], threshold: float = 0.0) -> float:
    """简化 Omega: 高于阈值的超额收益和 / 低于阈值的缺口和。"""
    if len(returns) < 2:
        return float("nan")
    gains = sum(max(0.0, r - threshold) for r in returns)
    losses = sum(max(0.0, threshold - r) for r in returns)
    if losses < 1e-15:
        return float("nan") if gains < 1e-15 else float("inf")
    return gains / losses


def buy_hold_equity_curve(
    candles: list[dict],
    initial_balance: float,
    *,
    fee_rate: float,
    slippage_bps: float,
) -> list[float]:
    """
    买入持有: 首根 K 线收盘全仓买入, 后续按收盘价盯市 (无再平衡)。
    与回测使用相同单边手续费与开仓滑点。
    """
    if not candles or initial_balance <= 0:
        return []
    slip = slippage_bps / 10000.0
    first_close = float(candles[0]["close"])
    exec_px = first_close * (1.0 + slip)
    spend = initial_balance
    fee = spend * fee_rate
    net = spend - fee
    qty = net / exec_px
    return [qty * float(c["close"]) for c in candles]


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
    rf_annual: float = 0.0,
) -> dict[str, float]:
    ppy = _periods_per_year(timeframe)
    years = (ts_end - ts_start) / (365.25 * 24 * 3600)
    mdd = max_drawdown(equity)
    rets = _simple_returns(equity)
    sharpe = sharpe_ratio(rets, ppy, rf_annual=rf_annual)
    sortino = sortino_ratio(rets, ppy)
    cagr_dec = cagr(total_return_pct, years) if years > 0 else float("nan")
    calmar = calmar_ratio(cagr_dec, mdd)
    ulcer = ulcer_index(equity)
    om = omega_ratio(rets, threshold=0.0)

    return {
        "max_drawdown_pct": mdd * 100.0,
        "sharpe": sharpe,
        "sortino": sortino,
        "cagr_pct": cagr_dec * 100.0 if not math.isnan(cagr_dec) else float("nan"),
        "calmar": calmar,
        "ulcer_index": ulcer,
        "omega": om,
        "years": years,
        "periods_per_year": ppy,
    }
