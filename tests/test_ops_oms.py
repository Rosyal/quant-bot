"""OMS 表、审批过期、运营自检"""
from __future__ import annotations

import os
import tempfile
import unittest

from compliance.workflow import approval_row_usable_for_order
from db.database import Database


class TestApprovalWorkflow(unittest.TestCase):
    def test_usable_approved(self):
        ok, msg = approval_row_usable_for_order({"status": "approved"})
        self.assertTrue(ok)

    def test_usable_expired(self):
        ok, msg = approval_row_usable_for_order({"status": "expired"})
        self.assertFalse(ok)


class TestOmsTable(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_create_and_list(self):
        db = Database(self.path)
        try:
            db.oms_create_order(
                client_order_id="t-oms-1",
                account_id="MAIN",
                symbol="BTC/USDT",
                side="buy",
                notional_usdt=100.0,
            )
            r = db.oms_get_order_by_client_id("t-oms-1")
            self.assertEqual(r["status"], "new")
            rows = db.list_oms_orders(limit=10)
            self.assertGreaterEqual(len(rows), 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
