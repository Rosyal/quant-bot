"""
情绪/另类数据 — CSV 批量加载 (示例列: symbol,sentiment_score,asof_ts)

对接 Wind/社交媒体 API 时替换为 fetch 实现即可。
"""
from __future__ import annotations

import csv
import os
from typing import Any


def load_symbol_sentiment_map(path: str) -> dict[str, dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return {}
    out: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            sym = (row.get("symbol") or "").strip()
            if not sym:
                continue
            try:
                score = float(row.get("sentiment_score") or row.get("score") or 0)
            except ValueError:
                score = 0.0
            out[sym] = {
                "sentiment_score": score,
                "asof_ts": row.get("asof_ts") or row.get("ts") or "",
                "source": row.get("source") or "csv",
            }
    return out


def sentiment_stub_status(path: str) -> dict[str, Any]:
    m = load_symbol_sentiment_map(path)
    return {"path": path, "symbols_loaded": len(m), "has_file": bool(path and os.path.isfile(path))}
