"""耦合分窗工具测试"""
from __future__ import annotations

import unittest

from config import MIN_CANDLES_FOR_BACKTEST
from runtime.coupled_test import split_walk_forward


class TestSplitWalkForward(unittest.TestCase):
    def _candles(self, n: int) -> list[dict]:
        return [
            {
                "timestamp": i * 3600,
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
            }
            for i in range(n)
        ]

    def test_short_series_returns_empty(self):
        segs, eff = split_walk_forward(self._candles(MIN_CANDLES_FOR_BACKTEST - 1), 5)
        self.assertEqual(segs, [])
        self.assertEqual(eff, 0)

    def test_segments_cover_full_length(self):
        n = MIN_CANDLES_FOR_BACKTEST * 12
        candles = self._candles(n)
        segs, eff = split_walk_forward(candles, 10)
        self.assertGreater(eff, 0)
        self.assertEqual(sum(len(s) for s in segs), n)
        for s in segs:
            self.assertGreaterEqual(len(s), MIN_CANDLES_FOR_BACKTEST)

    def test_requested_runs_clamped(self):
        n = MIN_CANDLES_FOR_BACKTEST * 3 + 5
        candles = self._candles(n)
        segs, eff = split_walk_forward(candles, 100)
        self.assertLessEqual(eff, 3)


if __name__ == "__main__":
    unittest.main()
