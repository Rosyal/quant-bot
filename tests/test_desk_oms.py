"""OMS / 中台 / 账本 / Barra-lite 冒烟"""
from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np

from db.database import Database
from middle_office.rules import MiddleOfficeRuleEngine, RuleContext
from oms.ems import MultiChannelEMS, channel_paper_stub, channel_sim_latency_stub
from oms.types import OrderRequest, OrderSide, OrderType
from factors.risk_model import portfolio_volatility, single_market_factor_assumption


class TestEMS(unittest.TestCase):
    def test_failover_to_paper(self):
        ems = MultiChannelEMS(
            [
                ("sim", channel_sim_latency_stub),
                (
                    "paper",
                    lambda o: channel_paper_stub(o, 100.0),
                ),
            ]
        )
        rep = ems.submit(
            OrderRequest(
                "t1",
                "BTC/USDT",
                OrderSide.BUY,
                OrderType.MARKET,
                notional_usdt=50.0,
            )
        )
        self.assertEqual(rep.status, "filled")
        self.assertEqual(rep.channel, "paper")
        self.assertIsNotNone(rep.avg_px)


class TestRuleEngine(unittest.TestCase):
    def test_engine_runs(self):
        eng = MiddleOfficeRuleEngine()
        ctx = RuleContext(100.0, "BTC/USDT", 10000.0, 50000.0, {})
        outs = eng.evaluate(ctx)
        self.assertTrue(len(outs) >= 1)


class TestAccountTransfer(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_transfer(self):
        db = Database(self.path)
        try:
            cur = db.conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO account_balances (account_id, balance_usdt) VALUES ('MAIN', 1000)"
            )
            cur.execute(
                "INSERT OR REPLACE INTO account_balances (account_id, balance_usdt) VALUES ('SUB', 0)"
            )
            db.conn.commit()
            r = db.execute_transfer("MAIN", "SUB", 100.0, note="test")
            self.assertTrue(r["ok"])
            self.assertAlmostEqual(db.get_account_balance("MAIN"), 900.0)
            self.assertAlmostEqual(db.get_account_balance("SUB"), 100.0)
        finally:
            db.close()


class TestBarraLite(unittest.TestCase):
    def test_port_vol(self):
        cov = single_market_factor_assumption(
            np.array([1.0, 1.0]),
            0.0002,
            np.array([0.0001, 0.0001]),
        )
        v = portfolio_volatility(np.array([0.5, 0.5]), cov)
        self.assertGreater(v, 0)


if __name__ == "__main__":
    unittest.main()
