"""
CLI / HTTP 共用的 dossier 构建入口（避免 web↔main 循环依赖）。
"""
from __future__ import annotations

from typing import Any

from deliverables.dossier import build_product_dossier


def parse_strategies_csv(csv: str | None) -> list[str]:
    if not csv or not str(csv).strip():
        return []
    return [x.strip().lower() for x in str(csv).split(",") if x.strip()]


def build_dossier_pipeline(
    *,
    use_mock: bool,
    days: int | None,
    strategy: str | None,
    profile: str | None,
    strategies_csv: str | None,
    walk_forward: bool,
    train_bars: int,
    test_bars: int,
    step: int | None,
) -> dict[str, Any]:
    from main import _profile_overrides_and_strategy

    from config import BACKTEST_DAYS, STRATEGY, SYMBOL, TIMEFRAME
    from data_fetcher import fetch_ohlcv, generate_mock_data

    ov, strat = _profile_overrides_and_strategy(profile, strategy)
    primary = (strat if strat is not None else strategy or STRATEGY).strip().lower()
    d = days if days is not None else BACKTEST_DAYS
    if use_mock:
        candles = generate_mock_data(d)
    else:
        candles = fetch_ohlcv(SYMBOL, TIMEFRAME, d)
    if not candles:
        return {"error": "no_candles", "message": "无法获取 K 线"}

    extras = parse_strategies_csv(strategies_csv)
    wf_params = None
    if walk_forward:
        wf_params = {"train_bars": train_bars, "test_bars": test_bars, "step": step}

    return build_product_dossier(
        candles,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        primary_strategy=primary,
        config_overrides=ov,
        extra_strategies=extras,
        walk_forward_params=wf_params,
    )
