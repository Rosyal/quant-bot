"""Walk-forward 冒烟"""
from __future__ import annotations

import unittest

from backtest.walk_forward import run_walk_forward
from data_fetcher import generate_mock_data


class TestWalkForward(unittest.TestCase):
    def test_runs_multiple_folds(self):
        candles = generate_mock_data(900, seed=7, silent=True)
        wf = run_walk_forward(
            candles,
            strategy="ma_cross",
            train_bars=200,
            test_bars=100,
            step=100,
        )
        self.assertNotIn("error", wf or {})
        self.assertGreaterEqual(len(wf.get("folds", [])), 2)


if __name__ == "__main__":
    unittest.main()
