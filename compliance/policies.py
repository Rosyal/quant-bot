"""
交易前策略校验 (可配置)

- 单笔名义上限
- UTC 交易时段窗口 (半开区间小时)

不构成法律合规意见; 正式环境需律师/合规团队与交易所规则。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def utc_hour_now() -> int:
    return datetime.now(timezone.utc).hour


@dataclass
class PolicyResult:
    allowed: bool
    reason: str


@dataclass
class TradingPolicy:
    max_order_usdt: float
    # None = 不限制; (9, 17) 表示 UTC 9<=h<17; 跨日如 (22, 6) 表示 h>=22 或 h<6
    allowed_hours_utc: tuple[int, int] | None = None

    def check_market_order(self, notional_usdt: float) -> PolicyResult:
        if notional_usdt <= 0:
            return PolicyResult(False, "名义须为正")
        if notional_usdt > self.max_order_usdt:
            return PolicyResult(
                False,
                f"超过单笔上限 {self.max_order_usdt:.2f} USDT",
            )
        if self.allowed_hours_utc is not None:
            a, b = self.allowed_hours_utc
            h = utc_hour_now()
            if a <= b:
                if not (a <= h < b):
                    return PolicyResult(
                        False,
                        f"非允许交易时段 UTC [{a},{b}) 当前 h={h}",
                    )
            else:
                if not (h >= a or h < b):
                    return PolicyResult(
                        False,
                        f"非允许交易时段 UTC 跨日 {a}-{b} 当前 h={h}",
                    )
        return PolicyResult(True, "ok")
