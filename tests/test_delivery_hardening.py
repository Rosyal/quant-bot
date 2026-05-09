"""交付硬化: 对账启发式、密钥粗检、Web 安全响应头。"""
from __future__ import annotations

import unittest
from collections import Counter

from flask import Response


class TestReconciliationFlags(unittest.TestCase):
    def test_filled_without_executions_warns(self):
        from compliance.reconciliation import _flags

        st = Counter({"filled": 3})
        flags = _flags(st, 0, 3)
        self.assertTrue(any("执行" in f for f in flags))

    def test_no_exec_warning_when_executions_exist(self):
        from compliance.reconciliation import _flags

        st = Counter({"filled": 2})
        flags = _flags(st, 2, 2)
        self.assertFalse(any("执行" in f for f in flags))


class TestEnvHardening(unittest.TestCase):
    def test_looks_weak(self):
        from security.env_hardening import _looks_weak

        self.assertTrue(_looks_weak("12345"))
        self.assertTrue(_looks_weak("password"))
        self.assertFalse(_looks_weak("a" * 20))


class TestWebSecurityHeaders(unittest.TestCase):
    def test_apply_headers_when_enabled(self):
        import config as cfg
        from web.app import _apply_security_headers

        prev = cfg.WEB_SECURITY_HEADERS_ENABLED
        try:
            cfg.WEB_SECURITY_HEADERS_ENABLED = True
            r = _apply_security_headers(Response("ok", mimetype="text/plain"))
            self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertIn("Content-Security-Policy", r.headers)
        finally:
            cfg.WEB_SECURITY_HEADERS_ENABLED = prev

    def test_skip_headers_when_disabled(self):
        import config as cfg
        from web.app import _apply_security_headers

        prev = cfg.WEB_SECURITY_HEADERS_ENABLED
        try:
            cfg.WEB_SECURITY_HEADERS_ENABLED = False
            r = _apply_security_headers(Response("ok", mimetype="text/plain"))
            self.assertIsNone(r.headers.get("X-Content-Type-Options"))
        finally:
            cfg.WEB_SECURITY_HEADERS_ENABLED = prev


if __name__ == "__main__":
    unittest.main()
