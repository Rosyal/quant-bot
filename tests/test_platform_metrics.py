"""市面平台常见补充指标: 扩展绩效、TCA、regime、压力、Kelly、敏感性"""
from __future__ import annotations

import unittest

import numpy as np

from backtest.advanced_metrics import (
    compute_advanced_metrics,
    max_consecutive_losing_trades,
    max_drawdown_episode_length_bars,
)
from backtest.tca import compute_tca_summary
from data_fetcher import generate_mock_data
from research.kelly import fractional_kelly_two_outcome, kelly_from_sell_trades
from research.regime import regime_summary
from research.sensitivity import run_parameter_sensitivity
from research.stress import apply_equity_shock_from_bar


class TestAdvancedMetrics(unittest.TestCase):
    def test_drawdown_duration(self):
        eq = [100.0, 110.0, 105.0, 100.0, 108.0]
        self.assertGreaterEqual(max_drawdown_episode_length_bars(eq), 1)

    def test_max_consecutive_losses(self):
        self.assertEqual(max_consecutive_losing_trades([1, -1, -2, 3, -1, -1]), 2)

    def test_ir_finite(self):
        rng = np.random.default_rng(0)
        n = 200
        b = 10000 * np.cumprod(1 + rng.normal(0, 0.01, n))
        s = b * (1 + rng.normal(0, 0.005, n))
        adv = compute_advanced_metrics(
            list(s),
            benchmark_equity=list(b),
            sell_trade_profits=[-1, 2, -1],
            periods_per_year=365.25 * 24,
        )
        self.assertIn("information_ratio_vs_bh", adv)


class TestTCA(unittest.TestCase):
    def test_fee_bps(self):
        trades = [
            {"side": "buy", "total": 1000.0, "fee": 1.0, "amount": 0.02, "price": 50000.0},
            {
                "side": "sell",
                "total": 990.0,
                "fee": 1.0,
                "amount": 0.02,
                "price": 51000.0,
            },
        ]
        tca = compute_tca_summary(trades, 10000.0, 100, periods_per_year=24 * 365.25)
        self.assertGreater(tca["gross_traded_notional_usd"], 0)
        self.assertGreater(tca["fee_bps_on_gross_traded"], 0)


class TestRegimeStressKelly(unittest.TestCase):
    def test_regime_pct(self):
        rng = np.random.default_rng(3)
        c = 100 * np.cumprod(1 + rng.normal(0, 0.02, 300))
        s = regime_summary(list(c), window=20, quantile=0.7)
        self.assertGreater(s["high_vol_pct"], 0)
        self.assertLessEqual(s["high_vol_pct"], 100)

    def test_stress_shortens_equity(self):
        eq = [100.0, 120.0, 90.0, 95.0]
        shocked, _ = apply_equity_shock_from_bar(eq, -0.2)
        self.assertLess(shocked[-1], eq[-1])

    def test_kelly_positive(self):
        k = fractional_kelly_two_outcome(0.55, 100, 80, fraction=0.5, cap=0.3)
        self.assertGreater(k, 0)

    def test_kelly_from_trades(self):
        r = kelly_from_sell_trades([10, -5, 8, -4, -3])
        self.assertIn("kelly_fraction", r)


class TestSensitivitySmoke(unittest.TestCase):
    def test_ma_cross_slow_period(self):
        candles = generate_mock_data(200, seed=99, silent=True)
        rows = run_parameter_sensitivity(
            candles,
            strategy="ma_cross",
            param_name="SLOW_PERIOD",
            values=[28, 32, 36],
        )
        self.assertEqual(len(rows), 3)
        self.assertIn("profit_pct", rows[0])


if __name__ == "__main__":
    unittest.main()
