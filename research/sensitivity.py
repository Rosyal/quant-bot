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


def run_parameter_sensitivity_grid(
    candles: list[dict],
    *,
    strategy: str,
    param1: str,
    values1: list,
    param2: str,
    values2: list,
    base_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    双参数网格扫描，供热力图使用。
    返回 ``z[i][j]`` 对应 ``values1[i]`` × ``values2[j]`` 的 Sharpe（及 profit_pct）。
    """
    z_sharpe: list[list[float | None]] = []
    z_profit: list[list[float | None]] = []
    for v1 in values1:
        row_s: list[float | None] = []
        row_p: list[float | None] = []
        for v2 in values2:
            ov = {**(base_overrides or {}), param1: v1, param2: v2}
            r = run_backtest(
                candles,
                quiet=True,
                strategy=strategy,
                config_overrides=ov,
            )
            if not r:
                row_s.append(None)
                row_p.append(None)
                continue
            m = r.get("metrics") or {}
            sh = m.get("sharpe")
            row_s.append(float(sh) if sh == sh else None)  # type: ignore[arg-type]
            pp = r.get("profit_pct")
            row_p.append(float(pp) if pp is not None else None)
        z_sharpe.append(row_s)
        z_profit.append(row_p)
    return {
        "strategy": strategy,
        "param1": param1,
        "param2": param2,
        "values1": list(values1),
        "values2": list(values2),
        "z_sharpe": z_sharpe,
        "z_profit_pct": z_profit,
    }
