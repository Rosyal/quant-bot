"""模拟撮合、延迟画像、净头寸与清算快照"""
from __future__ import annotations

import os
import tempfile
import unittest

from db.database import Database
from oms.ems import make_matching_channel
from oms.latency_profile import modelled_exchange_latency_ns
from oms.matching_engine import simulate_exchange_match
from oms.netting import apply_spot_fill_to_net, snapshot_clearing_batch
from oms.types import OrderRequest, OrderSide, OrderType


class TestMatching(unittest.TestCase):
    def test_multi_leg_when_large_notional(self):
        order = OrderRequest(
            client_order_id="t1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            notional_usdt=900_000.0,
            account_id="MAIN",
        )
        rep = simulate_exchange_match(order, 50_000.0, latency_profile="colo")
        self.assertIn(rep.status, ("filled", "partial"))
        self.assertGreater(len(rep.exec_legs), 1)
        self.assertIsNotNone(rep.avg_px)
        self.assertGreater(rep.filled_qty or 0, 0)
        self.assertIn("modelled_exchange_latency_ns", rep.detail)

    def test_latency_profile_ranges(self):
        for _ in range(20):
            ns = modelled_exchange_latency_ns("colo")
            self.assertLess(ns, 500_000)
        for _ in range(10):
            ns = modelled_exchange_latency_ns("retail")
            self.assertGreater(ns, 500_000)


class TestNettingDb(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_persist_and_net_position(self):
        db = Database(self.path)
        try:
            ch = make_matching_channel(50_000.0, db)
            order = OrderRequest(
                client_order_id="t2",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                notional_usdt=5_000.0,
                account_id="ACC1",
            )
            rep = ch(order)
            self.assertIn(rep.status, ("filled", "partial"))
            rows = db.list_oms_executions(limit=5)
            self.assertGreaterEqual(len(rows), 1)
            pos = db.get_net_position("ACC1", "BTC/USDT")
            self.assertIsNotNone(pos)
            self.assertGreater(float(pos["qty"]), 0)
            bid = snapshot_clearing_batch(db, "test-window")
            self.assertGreater(bid, 0)
        finally:
            db.close()

    def test_sell_reduces_position(self):
        db = Database(self.path)
        try:
            apply_spot_fill_to_net(
                db,
                account_id="A",
                symbol="ETH/USDT",
                side="buy",
                filled_qty=2.0,
                avg_px=3000.0,
                fee_usdt=6.0,
            )
            apply_spot_fill_to_net(
                db,
                account_id="A",
                symbol="ETH/USDT",
                side="sell",
                filled_qty=0.5,
                avg_px=3100.0,
                fee_usdt=1.55,
            )
            pos = db.get_net_position("A", "ETH/USDT")
            self.assertAlmostEqual(float(pos["qty"]), 1.5, places=6)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
