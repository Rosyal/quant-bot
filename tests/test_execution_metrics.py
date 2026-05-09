"""成交模型 (滑点) 与扩展绩效指标"""
from __future__ import annotations

import unittest

from exchange.paper import PaperExchange
from backtest.metrics import buy_hold_equity_curve, ulcer_index


class TestPaperSlippage(unittest.TestCase):
    def test_buy_price_worse_than_reference(self):
        ex = PaperExchange(10000.0, fee_rate=0.0, slippage_bps=100.0)  # 1%
        ref = 100.0
        t = ex.buy("BTC/USDT", ref, 1000.0)
        self.assertIsNotNone(t)
        assert t is not None
        self.assertGreater(t["price"], ref)

    def test_sell_price_worse_than_reference(self):
        ex = PaperExchange(10000.0, fee_rate=0.0, slippage_bps=100.0)
        ex.coin_balance = 1.0
        ex.coin_symbol = "BTC"
        ref = 100.0
        t = ex.sell("BTC/USDT", ref)
        self.assertIsNotNone(t)
        assert t is not None
        self.assertLess(t["price"], ref)


class TestBuyHoldCurve(unittest.TestCase):
    def test_length_matches_candles(self):
        candles = [
            {"close": 100.0, "timestamp": i} for i in range(120)
        ]
        curve = buy_hold_equity_curve(
            candles, 10000.0, fee_rate=0.001, slippage_bps=0.0
        )
        self.assertEqual(len(curve), 120)
        self.assertGreater(curve[-1], 0)

    def test_ulcer_non_negative(self):
        eq = [100.0, 105.0, 102.0, 110.0, 95.0]
        u = ulcer_index(eq)
        self.assertGreaterEqual(u, 0.0)


if __name__ == "__main__":
    unittest.main()
