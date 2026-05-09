from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarginStatus:
    equity_usdt: float
    gross_notional_usd: float
    initial_margin_req: float
    maintenance_margin_req: float
    buffer_usdt: float  # equity - maintenance
    breached: bool


def margin_status(
    equity_usdt: float,
    gross_notional_usd: float,
    *,
    initial_rate: float,
    maintenance_rate: float,
) -> MarginStatus:
    """
    简化期货式保证金: IM = 名义 * 初始率, MM = 名义 * 维持率。
    """
    im = max(0.0, gross_notional_usd) * initial_rate
    mm = max(0.0, gross_notional_usd) * maintenance_rate
    buf = equity_usdt - mm
    return MarginStatus(
        equity_usdt=equity_usdt,
        gross_notional_usd=gross_notional_usd,
        initial_margin_req=im,
        maintenance_margin_req=mm,
        buffer_usdt=buf,
        breached=equity_usdt < mm and gross_notional_usd > 0,
    )
