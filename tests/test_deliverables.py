"""交付摘要与样本诊断"""
from __future__ import annotations

import unittest

from deliverables.edge_diagnostics import diagnose_backtest_sample
from deliverables.executive_brief import build_brief, format_brief_text


class TestDeliverables(unittest.TestCase):
    def test_diagnose_empty_trades(self):
        r = {
            "total_trades": 4,
            "sell_count": 1,
            "profit_pct": 1.0,
            "alpha_profit_pct": -2.0,
            "metrics": {"sharpe": -0.5, "max_drawdown_pct": -10.0},
        }
        d = diagnose_backtest_sample(r)
        self.assertEqual(d["tier"], "insufficient_data")
        self.assertTrue(any("极少" in x or "过少" in x for x in d["flags"]))

    def test_brief_contains_disclaimer(self):
        r = {
            "strategy": "rsi_macd",
            "first_date": "2024-01-01",
            "last_date": "2024-06-01",
            "candles_used": 400,
            "profit_pct": 5.0,
            "total_value": 10500.0,
            "total_trades": 30,
            "sell_count": 12,
            "win_rate": 55.0,
            "alpha_profit_pct": 1.0,
            "benchmark_profit_pct": 4.0,
            "metrics": {"sharpe": 0.9, "max_drawdown_pct": -12.0, "sortino": 1.1},
            "kelly_hint": 0.05,
            "tca": {"fee_bps_on_gross_traded": 12.0},
            "advanced": {"information_ratio_vs_bh": 0.2},
        }
        b = build_brief(r, symbol="BTC/USDT", timeframe="1h")
        text = format_brief_text(b)
        self.assertIn("非投资", text)
        self.assertIn("product_capabilities", b)
        self.assertIn("historical_sample_summary", b)


if __name__ == "__main__":
    unittest.main()
