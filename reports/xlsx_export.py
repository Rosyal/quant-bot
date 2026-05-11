"""回测摘要导出 Excel（可选依赖 openpyxl）。"""
from __future__ import annotations

from typing import Any


def write_backtest_summary_xlsx(path: str, result: dict[str, Any]) -> None:
    """将单次回测关键字段写入 .xlsx。"""
    try:
        from openpyxl import Workbook
    except ImportError as e:
        raise RuntimeError("请先安装: pip install openpyxl") from e

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "backtest"
    m = result.get("metrics") or {}
    adv = result.get("advanced") or {}
    tca = result.get("tca") or {}
    pairs = [
        ("strategy", result.get("strategy")),
        ("profit_pct", result.get("profit_pct")),
        ("sharpe", m.get("sharpe")),
        ("max_drawdown_pct", m.get("max_drawdown_pct")),
        ("benchmark_profit_pct", result.get("benchmark_profit_pct")),
        ("alpha_profit_pct", result.get("alpha_profit_pct")),
        ("total_fees_paid", result.get("total_fees_paid")),
        ("information_ratio_vs_bh", adv.get("information_ratio_vs_bh")),
        ("tca_fee_bps", tca.get("fee_bps_on_gross_traded")),
        ("tca_turnover_proxy", tca.get("turnover_per_year_proxy")),
    ]
    ws.append(["field", "value"])
    for k, v in pairs:
        ws.append([k, v])
    wb.save(path)
