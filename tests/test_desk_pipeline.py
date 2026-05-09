"""全链路编排"""
from __future__ import annotations

import os
import tempfile
import unittest

from db.database import Database
from desk.pipeline import PipelineContext, run_order_pipeline


class TestFullChain(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_pipeline_force_small(self):
        db = Database(self.path)
        try:
            ctx = PipelineContext(
                symbol="BTC/USDT",
                side="buy",
                notional_usdt=100.0,
                mid=50000.0,
                role="trader",
                force=True,
            )
            pr = run_order_pipeline(ctx, db, run_ems=False, log_summary_audit=True)
            self.assertTrue(pr.ok)
            self.assertTrue(any(s.get("stage") == "execution_router" for s in pr.stages))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
