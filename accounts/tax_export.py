"""
税务辅助导出 — 按年汇总已实现盈亏 (数据库 sell 记录的 profit 字段)。

非税务申报文件; 实际纳税需会计师与本地法规。
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from typing import Any


def _year_from_ts(ts: int) -> int:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).year


def export_realized_pnl_by_year_csv(
    trades: list[dict[str, Any]],
    out_path: str,
    *,
    year: int | None = None,
) -> dict[str, Any]:
    """卖出且含 profit 的记录按年汇总写入 CSV。"""
    by_year: dict[int, dict[str, float]] = {}
    for t in trades:
        if (t.get("side") or "").lower() != "sell":
            continue
        p = t.get("profit")
        if p is None:
            continue
        y = _year_from_ts(int(t["timestamp"]))
        if year is not None and y != year:
            continue
        agg = by_year.setdefault(y, {"n": 0, "pnl": 0.0, "fees": 0.0})
        agg["n"] += 1
        agg["pnl"] += float(p)
        agg["fees"] += float(t.get("fee") or 0)

    rows = sorted(by_year.items(), key=lambda x: x[0])
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "n_sells", "realized_pnl_usdt", "fees_usdt"])
        for y, agg in rows:
            w.writerow([y, int(agg["n"]), f"{agg['pnl']:.4f}", f"{agg['fees']:.4f}"])
    return {"years_written": len(rows), "path": out_path}
