"""策略信号冒烟测试: 长度对齐、字段合法、无异常"""
from __future__ import annotations

import unittest

from data_fetcher import generate_mock_data
from strategy import STRATEGY_REGISTRY


class TestStrategySignals(unittest.TestCase):
    def setUp(self):
        self.candles = generate_mock_data(120, seed=12345, silent=True)
        self.assertGreaterEqual(len(self.candles), 100)

    def test_all_registered_strategies(self):
        for name, fn in STRATEGY_REGISTRY.items():
            with self.subTest(strategy=name):
                sigs = fn(self.candles)
                self.assertEqual(
                    len(sigs),
                    len(self.candles),
                    f"{name}: 信号条数应等于 K 线条数",
                )
                for i, row in enumerate(sigs):
                    self.assertIn("signal", row, f"{name} row {i}")
                    self.assertIn(
                        row["signal"],
                        ("hold", "buy", "sell"),
                        f"{name} row {i} invalid signal",
                    )
                    self.assertIn("price", row)
                    self.assertIn("timestamp", row)


if __name__ == "__main__":
    unittest.main()
