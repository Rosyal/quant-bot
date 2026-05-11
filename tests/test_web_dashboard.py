"""Web 看板 ETag / 缓存"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import config as cfg


class TestWebPortfolioEtag(unittest.TestCase):
    def setUp(self):
        import web.app as wa

        wa._state_cache.update({"path": "", "mtime": None, "data": None})

        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        cfg.PAPER_LIVE_STATE_PATH = self.path
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "usdt": 10000.0,
                    "positions": {},
                    "trades": [],
                    "equity_curve": [],
                    "updated_at": 1710000000,
                },
                f,
            )

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_if_none_match_returns_304(self):
        from web.app import app

        with app.test_client() as c:
            r1 = c.get("/api/portfolio")
            self.assertEqual(r1.status_code, 200)
            tag = r1.headers.get("ETag")
            self.assertTrue(tag)
            r2 = c.get("/api/portfolio", headers={"If-None-Match": tag})
            self.assertEqual(r2.status_code, 304)


class TestSensitivityGridApi(unittest.TestCase):
    def test_sensitivity_grid_forbidden_without_key(self):
        from web.app import app

        with app.test_client() as c:
            r = c.get("/api/sensitivity-grid")
            self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
