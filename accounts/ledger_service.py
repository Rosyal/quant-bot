from __future__ import annotations

import time
from typing import Any

from db.database import Database


class LedgerService:
    """多账户 USDT 账本 (与策略成交独立; 用于资金划拨演示)"""

    def __init__(self, db: Database):
        self.db = db

    def ensure_account(self, account_id: str) -> None:
        self.db.ensure_account_balance(account_id, 0.0)

    def balance(self, account_id: str) -> float:
        return self.db.get_account_balance(account_id)

    def transfer(
        self,
        from_id: str,
        to_id: str,
        amount_usdt: float,
        *,
        note: str = "",
        ref: str = "",
    ) -> dict[str, Any]:
        return self.db.execute_transfer(from_id, to_id, amount_usdt, note=note, ref=ref)

    def list_transfers(self, limit: int = 50) -> list[dict]:
        return self.db.list_fund_transfers(limit)
