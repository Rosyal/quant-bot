"""
交易成本分析 (TCA) — 粗粒度

市面平台常见: 成交额、费用占成交名义 bps、估算换手。精确 TCA 需逐笔与盘口。
"""
from __future__ import annotations

from typing import Any


def compute_tca_summary(
    trades: list[dict[str, Any]],
    initial_balance: float,
    n_bars: int,
    *,
    periods_per_year: float,
) -> dict[str, float]:
    buy_notional = 0.0
    sell_gross = 0.0
    fees = 0.0
    for t in trades:
        fees += float(t.get("fee") or 0)
        if t.get("side") == "buy":
            buy_notional += float(t.get("total") or 0)
        elif t.get("side") == "sell":
            sell_gross += float(t.get("amount") or 0) * float(t.get("price") or 0)

    gross_traded = buy_notional + sell_gross
    fee_bps_on_gross = (fees / gross_traded * 10_000.0) if gross_traded > 0 else 0.0
    years = max(n_bars / max(periods_per_year, 1e-9), 1e-9)
    # 简化年化换手: 单边总名义 / 初始资金 / 年数
    turnover_ann = (gross_traded / max(initial_balance, 1e-9)) / years

    return {
        "buy_notional_usd": buy_notional,
        "sell_gross_notional_usd": sell_gross,
        "gross_traded_notional_usd": gross_traded,
        "fees_paid_usd": fees,
        "fee_bps_on_gross_traded": fee_bps_on_gross,
        "turnover_per_year_proxy": turnover_ann,
    }
