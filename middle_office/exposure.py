from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExposureSnapshot:
    """净敞口快照 (可与纸面 JSON / 外部 OMS 对齐)"""

    cash_usdt: float
    positions_qty: dict[str, float] = field(default_factory=dict)
    mark_prices: dict[str, float] = field(default_factory=dict)
    account_id: str = "MAIN"
    meta: dict[str, Any] = field(default_factory=dict)


def notionals_from_positions(snap: ExposureSnapshot) -> dict[str, float]:
    """各标的美元名义 (多头为正); 无标记价则跳过。"""
    out: dict[str, float] = {}
    for sym, qty in snap.positions_qty.items():
        if qty == 0:
            continue
        px = snap.mark_prices.get(sym)
        if px and px > 0:
            out[sym] = qty * px
    return out


def gross_exposure_usd(notional_by_symbol: dict[str, float]) -> float:
    return sum(abs(v) for v in notional_by_symbol.values())


def load_exposure_from_paper_state(
    state: dict[str, Any],
    mark_prices: dict[str, float],
) -> ExposureSnapshot:
    pos = {k: float(v) for k, v in (state.get("positions") or {}).items() if float(v) != 0}
    return ExposureSnapshot(
        cash_usdt=float(state.get("usdt", 0)),
        positions_qty=pos,
        mark_prices=dict(mark_prices),
    )
