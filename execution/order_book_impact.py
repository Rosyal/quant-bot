"""
订单簿与市场冲击 (仿真)

- 简化限价梯度 + VWAP 吃单
- 平方根冲击近似: 冲击(bps) ∝ γ * sqrt(参与率), 参与率 = 名义 / 参考深度

真实低延迟系统需托管机房、逐笔 L2、撮合规则与风控前置; 此处仅供研究与回测压力场景。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def effective_price_sqrt_impact(
    side: str,
    mid: float,
    notional_usd: float,
    depth_reference_usd: float,
    *,
    gamma: float = 0.55,
) -> float:
    """
    用参考深度估计瞬时冲击后的成交价 (单边)。

    :param side: buy | sell
    :param depth_reference_usd: 约等于「典型可成交深度」名义 (美元)
    :param gamma: 冲击强度, 越大越保守
    """
    if mid <= 0 or notional_usd <= 0:
        raise ValueError("mid 与 notional_usd 须为正")
    depth = max(float(depth_reference_usd), 1.0)
    participation = notional_usd / depth
    impact_bps = gamma * 10_000.0 * math.sqrt(participation)
    adj = impact_bps / 10_000.0
    s = side.strip().lower()
    if s == "buy":
        return mid * (1.0 + adj)
    if s == "sell":
        return max(mid * (1.0 - adj), 1e-12)
    raise ValueError("side 须为 buy 或 sell")


def vwap_from_ladder(
    side: str,
    levels: list[tuple[float, float]],
    target_notional_usd: float,
) -> tuple[float, float]:
    """
    沿 (价格, 该档美元流动性) 吃到 target_notional_usd, 返回 (vwap 价格, 已吃美元名义)。

    levels: 买单用 asks 从低到高; 卖单用 bids 从高到低 (价格仍递增列出即可, 由调用方排序)。
    """
    _ = side
    if target_notional_usd <= 0:
        return 0.0, 0.0
    rem = target_notional_usd
    coin = 0.0
    gross_usd = 0.0
    for px, depth_usd in levels:
        if rem <= 0 or px <= 0 or depth_usd <= 0:
            break
        take_usd = min(rem, depth_usd)
        coin += take_usd / px
        gross_usd += take_usd
        rem -= take_usd
    if coin <= 0:
        return 0.0, 0.0
    return gross_usd / coin, gross_usd


@dataclass
class SimpleLimitOrderBook:
    """
    极简中央限价簿快照: 围绕 mid 生成指数衰减深度的买卖各 N 档。
    用于演示「吃单深度 → VWAP」, 非真实撮合序。
    """

    mid: float
    depth_scale_usd: float = 500_000.0
    half_spread_bps: float = 2.0
    levels_each_side: int = 8
    tick_bps: float = 3.0
    _bid_levels: list[tuple[float, float]] = field(default_factory=list, repr=False)
    _ask_levels: list[tuple[float, float]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        hs = self.half_spread_bps / 10_000.0
        best_bid = self.mid * (1.0 - hs)
        best_ask = self.mid * (1.0 + hs)
        self._bid_levels = []
        self._ask_levels = []
        decay = 0.72
        for i in range(self.levels_each_side):
            tb = self.tick_bps / 10_000.0
            bp = best_bid * (1.0 - i * tb)
            ap = best_ask * (1.0 + i * tb)
            d = self.depth_scale_usd * (decay**i)
            self._bid_levels.append((bp, d))
            self._ask_levels.append((ap, d))

    def ask_levels(self) -> list[tuple[float, float]]:
        """卖档 (低→高), 吃买单。"""
        return list(self._ask_levels)

    def bid_levels_high_to_low(self) -> list[tuple[float, float]]:
        """买档 (高→低), 吃卖单。"""
        return list(reversed(self._bid_levels))

    def vwap_market_buy(self, notional_usd: float) -> tuple[float, float]:
        return vwap_from_ladder("buy", self._ask_levels, notional_usd)

    def vwap_market_sell(self, notional_usd: float) -> tuple[float, float]:
        return vwap_from_ladder("sell", self.bid_levels_high_to_low(), notional_usd)
