"""
账户级风控 (回测/模拟盘通用)

- 权益峰值跟踪 + 最大回撤熔断: 触发后禁止新开仓, 可选强制平仓
- 与策略内 ATR 止损互补: 这里是「组合/账户」层保护
"""
from __future__ import annotations


class RiskManager:
    def __init__(
        self,
        initial_equity: float,
        max_drawdown_pct: float,
        force_flat_on_breach: bool,
        max_position_pct: float,
    ):
        self.initial = initial_equity
        self.peak = max(initial_equity, 1e-9)
        self.max_dd = max_drawdown_pct
        self.force_flat = force_flat_on_breach
        self.max_position_pct = max(0.0, min(1.0, max_position_pct))
        self.halted = False
        self.breach_count = 0

    def update(self, equity: float) -> bool:
        """
        用当前权益更新峰值与回撤状态。
        :return: 本根 K 线是否需要立即清仓 (首次触发且允许 force_flat)
        """
        equity = max(equity, 1e-9)
        self.peak = max(self.peak, equity)
        if self.halted:
            return False
        dd = (self.peak - equity) / self.peak if self.peak else 0.0
        if dd >= self.max_dd:
            self.halted = True
            self.breach_count += 1
            return self.force_flat
        return False

    def allow_new_buy(self) -> bool:
        return not self.halted

    def cap_position_pct(self, requested: float) -> float:
        return min(max(0.0, requested), self.max_position_pct)
