"""机构化脚手架冒烟: 冲击、组合、路由、权限"""
from __future__ import annotations

import unittest

import numpy as np

from compliance.policies import TradingPolicy
from execution.order_book_impact import SimpleLimitOrderBook, effective_price_sqrt_impact
from portfolio.optimizer import optimize_from_price_panel, risk_parity_weights
from routing.execution_router import ExecutionRouter
from security.permissions import PermissionDenied, assert_can


class TestImpact(unittest.TestCase):
    def test_sqrt_impact_monotone(self):
        p1 = effective_price_sqrt_impact("buy", 100.0, 1_000.0, 1_000_000.0, gamma=0.5)
        p2 = effective_price_sqrt_impact("buy", 100.0, 100_000.0, 1_000_000.0, gamma=0.5)
        self.assertGreater(p2, p1)

    def test_lob_vwap_buy_ge_mid(self):
        book = SimpleLimitOrderBook(mid=50_000.0, depth_scale_usd=200_000.0)
        vwap, filled = book.vwap_market_buy(50_000.0)
        self.assertGreater(filled, 0)
        self.assertGreaterEqual(vwap, book.mid * 0.999)


class TestPortfolio(unittest.TestCase):
    def test_risk_parity_sums_one(self):
        rng = np.random.default_rng(1)
        x = rng.standard_normal((200, 4))
        cov = np.cov(x, rowvar=False) + np.eye(4) * 1e-6
        w = risk_parity_weights(cov)
        self.assertAlmostEqual(float(w.sum()), 1.0, places=5)
        self.assertTrue(np.all(w >= 0))

    def test_optimize_smoke(self):
        rng = np.random.default_rng(2)
        closes = 100 * np.cumprod(1 + rng.normal(0, 0.01, (150, 3)), axis=0)
        w, _ = optimize_from_price_panel(closes, method="minvar")
        self.assertEqual(w.shape, (3,))
        self.assertAlmostEqual(float(w.sum()), 1.0, places=5)


class TestPolicyRouter(unittest.TestCase):
    def test_policy_blocks_large(self):
        p = TradingPolicy(max_order_usdt=100.0)
        self.assertFalse(p.check_market_order(200.0).allowed)

    def test_readonly_cannot_route(self):
        db = None
        r = ExecutionRouter(db=db, role="readonly", backend="paper_stub")
        out = r.dry_run_market_order(
            symbol="BTC/USDT",
            side="buy",
            notional_usdt=100.0,
            mid=1.0,
        )
        self.assertFalse(out.ok)

    def test_trader_ok_stub(self):
        r = ExecutionRouter(db=None, role="trader", backend="paper_stub")
        out = r.dry_run_market_order(
            symbol="BTC/USDT",
            side="buy",
            notional_usdt=100.0,
            mid=50_000.0,
        )
        self.assertTrue(out.ok)
        self.assertIsNotNone(out.effective_price)
        assert out.effective_price is not None
        self.assertGreater(out.effective_price, 50_000.0)


class TestPermissions(unittest.TestCase):
    def test_admin_can_route(self):
        assert_can("admin", "route_order")

    def test_readonly_route_raises(self):
        with self.assertRaises(PermissionDenied):
            assert_can("readonly", "route_order")


if __name__ == "__main__":
    unittest.main()
