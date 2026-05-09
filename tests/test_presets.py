"""预设覆盖字典测试"""
from __future__ import annotations

import unittest

from runtime.presets import default_strategy_for_profile, get_profile_overrides


class TestPresets(unittest.TestCase):
    def test_stability_overrides_keys(self):
        d = get_profile_overrides("stability")
        self.assertIn("TRADE_AMOUNT_PCT", d)
        self.assertIn("RISK_MAX_DRAWDOWN_PCT", d)
        self.assertLessEqual(d["TRADE_AMOUNT_PCT"], 0.15)

    def test_default_strategy(self):
        self.assertEqual(default_strategy_for_profile("stability"), "ensemble_strict")

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            get_profile_overrides("nope")


if __name__ == "__main__":
    unittest.main()
