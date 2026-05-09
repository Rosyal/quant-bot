"""单参数敏感性扫描 (固定 K 线, 多次回测)"""
from __future__ import annotations

from typing import Any

from backtest.engine import run_backtest


def run_parameter_sensitivity(
    candles: list[dict],
    *,
    strategy: str,
    param_name: str,
    values: list[Any],
    base_overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    base = dict(base_overrides or ())
    rows: list[dict[str, Any]] = []
    for v in values:
        ov = {**base, param_name: v}
        r = run_backtest(
            candles,
            quiet=True,
            strategy=strategy,
            config_overrides=ov,
        )
        if not r:
            rows.append(
                {
                    "param_value": v,
                    "profit_pct": None,
                    "sharpe": None,
                    "max_dd_pct": None,
                }
            )
            continue
        m = r.get("metrics") or {}
        rows.append(
            {
                "param_value": v,
                "profit_pct": r.get("profit_pct"),
                "sharpe": m.get("sharpe"),
                "max_dd_pct": m.get("max_drawdown_pct"),
            }
        )
    return rows
