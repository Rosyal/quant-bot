"""受密钥保护的产品证据包 API"""
from __future__ import annotations

import os
import unittest


class TestWebProductBrief(unittest.TestCase):
    def test_forbidden_without_key(self):
        from web.app import app

        with app.test_client() as c:
            r = c.get("/api/product-brief?mock=1&days=20")
            self.assertEqual(r.status_code, 403)

    def test_ok_with_key(self):
        from web.app import app

        os.environ["QUANT_BOT_BRIEF_API_KEY"] = "test-brief-secret"
        try:
            with app.test_client() as c:
                r = c.get(
                    "/api/product-brief?key=test-brief-secret&mock=1&days=25"
                )
                self.assertEqual(r.status_code, 200)
                self.assertIn(b"quant_bot_product_dossier_v1", r.data)
        finally:
            os.environ.pop("QUANT_BOT_BRIEF_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
