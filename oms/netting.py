"""
净额与清算快照 (现货简化)

机构清算含多腿合约、保证金、CCP; 此处实现 **账户×标的净头寸** 滚动与批量快照落库。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from db.database import Database


@dataclass
class NetPositionRow:
    account_id: str
    symbol: str
    qty: float
    avg_px: float
    updated_ts: int


def _next_avg_entry(
    old_qty: float,
    old_avg: float,
    fill_qty: float,
    fill_px: float,
) -> tuple[float, float]:
    if fill_qty <= 0 or fill_px <= 0:
        return old_qty, old_avg
    new_qty = old_qty + fill_qty
    if new_qty <= 0:
        return 0.0, 0.0
    cost = old_qty * old_avg + fill_qty * fill_px
    return new_qty, cost / new_qty


def apply_spot_fill_to_net(
    db: "Database",
    *,
    account_id: str,
    symbol: str,
    side: str,
    filled_qty: float,
    avg_px: float | None,
    fee_usdt: float | None,
) -> dict[str, Any]:
    """
    现货方向更新 net_positions (买增仓 / 卖减仓)。fee 仅记入返回摘要, 不改变 qty (简化)。
    """
    if not avg_px or filled_qty <= 0:
        return {"ok": False, "reason": "无效成交量或价格"}
    s = side.strip().lower()
    row = db.get_net_position(account_id, symbol)
    old_qty = float(row["qty"]) if row else 0.0
    old_avg = float(row["avg_px"]) if row else 0.0

    if s == "buy":
        q = filled_qty
        new_qty, new_avg = _next_avg_entry(old_qty, old_avg, q, avg_px)
    elif s == "sell":
        q = -min(old_qty, filled_qty)
        new_qty = old_qty + q
        new_avg = old_avg if new_qty > 1e-18 else 0.0
    else:
        return {"ok": False, "reason": "side 须为 buy/sell"}

    ts = int(time.time())
    db.upsert_net_position(
        account_id=account_id,
        symbol=symbol,
        qty=new_qty,
        avg_px=new_avg,
        updated_ts=ts,
    )
    return {
        "ok": True,
        "account_id": account_id,
        "symbol": symbol,
        "prev_qty": old_qty,
        "new_qty": new_qty,
        "avg_px": new_avg,
        "fee_usdt": float(fee_usdt or 0.0),
        "ts": ts,
    }


def snapshot_clearing_batch(db: "Database", label: str) -> int:
    """将当前净头寸表打成一条清算批次 (审计/对账用)。"""
    positions = db.list_net_positions()
    payload = {
        "positions": positions,
        "created_ts": int(time.time()),
    }
    return db.insert_clearing_batch(label, json.dumps(payload, ensure_ascii=False))
