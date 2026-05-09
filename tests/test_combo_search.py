"""组合搜索与预计算信号回测"""
from __future__ import annotations

import unittest

from backtest.engine import run_backtest
from data_fetcher import generate_mock_data
from runtime.combo_search import _parse_pool, run_combo_search


class TestComboSearch(unittest.TestCase):
    def test_parse_pool_rejects_ensemble(self):
        p = _parse_pool("ma_cross,ensemble,rsi_macd")
        self.assertNotIn("ensemble", p)
        self.assertIn("ma_cross", p)
        self.assertIn("rsi_macd", p)

    def test_run_combo_search_smoke(self):
        candles = generate_mock_data(90, seed=7, silent=True)
        r = run_combo_search(
            candles,
            pool_csv="ma_cross,ema_cross,macd",
            min_size=2,
            max_size=3,
            min_votes=2,
            max_votes=None,
            max_eval=50,
            seed=1,
            sort_by="composite",
            config_overrides=None,
        )
        self.assertIn("rows", r)
        self.assertGreater(len(r["rows"]), 0)


class TestPrecomputedSignals(unittest.TestCase):
    def test_length_mismatch_returns_empty(self):
        candles = generate_mock_data(100, seed=1, silent=True)
        bad = [{"timestamp": c["timestamp"], "signal": "hold", "price": c["close"]} for c in candles[:5]]
        r = run_backtest(
            candles,
            quiet=True,
            strategy="custom_test",
            precomputed_signals=bad,
        )
        self.assertEqual(r, {})


if __name__ == "__main__":
    unittest.main()
