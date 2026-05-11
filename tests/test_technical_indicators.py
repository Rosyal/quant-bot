"""strategy/technical/base 与 indicators 封装、随机策略。"""
from __future__ import annotations

import unittest

from data_fetcher import generate_mock_data
from research.sensitivity import run_parameter_sensitivity_grid
from strategy.indicators import adx, obv, stochastic, williams_r


def _sample_candles(n: int = 80) -> list[dict]:
    raw = generate_mock_data(5, seed=7, silent=True)
    return raw[:n] if len(raw) >= n else raw


class TestStochasticCandlesInterface(unittest.TestCase):
    """Stochastic 必须接受 candles list[dict]，与三序列旧误用区分。"""

    def test_stochastic_length_matches(self):
        c = _sample_candles(60)
        k, d = stochastic(c)
        self.assertEqual(len(k), len(c))
        self.assertEqual(len(d), len(c))

    def test_williams_and_obv(self):
        c = _sample_candles(50)
        wr = williams_r(c, period=14)
        o = obv(c)
        self.assertEqual(len(wr), len(c))
        self.assertEqual(len(o), len(c))
        self.assertTrue(any(x is not None for x in wr[13:]))

    def test_adx_tuple(self):
        c = _sample_candles(90)
        a, p, m = adx(c, period=14)
        self.assertEqual(len(a), len(c))


class TestSensitivityGrid(unittest.TestCase):
    def test_grid_shape(self):
        c = _sample_candles(100)
        g = run_parameter_sensitivity_grid(
            c,
            strategy="ma_cross",
            param1="FAST_PERIOD",
            values1=[8, 10],
            param2="SLOW_PERIOD",
            values2=[26, 30],
        )
        self.assertEqual(len(g["z_sharpe"]), 2)
        self.assertEqual(len(g["z_sharpe"][0]), 2)


class TestXlsxExport(unittest.TestCase):
    def test_xlsx_writes(self):
        import tempfile
        import os

        try:
            from reports.xlsx_export import write_backtest_summary_xlsx
        except ImportError:
            self.skipTest("openpyxl")
        r = {
            "strategy": "ma_cross",
            "profit_pct": 1.2,
            "metrics": {"sharpe": 0.5, "max_drawdown_pct": -5.0},
            "advanced": {"information_ratio_vs_bh": 0.1},
            "tca": {"fee_bps_on_gross_traded": 10.0, "turnover_per_year_proxy": 2.0},
            "benchmark_profit_pct": 0.5,
            "alpha_profit_pct": 0.7,
            "total_fees_paid": 12.3,
        }
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            write_backtest_summary_xlsx(path, r)
            self.assertTrue(os.path.isfile(path))
            self.assertGreater(os.path.getsize(path), 200)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
