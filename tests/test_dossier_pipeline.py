"""证据包 pipeline（mock，不触网）"""
from __future__ import annotations

import unittest

from deliverables.governance import governance_triad
from deliverables.runner import build_dossier_pipeline
from deliverables.wf_chapter import build_walk_forward_chapter


class TestDossier(unittest.TestCase):
    def test_governance_triad_keys(self):
        g = governance_triad()
        self.assertIn("tool_layer", g)
        self.assertIn("evidence_layer", g)
        self.assertIn("decision_layer", g)

    def test_pipeline_multi_strategy_mock(self):
        d = build_dossier_pipeline(
            use_mock=True,
            days=45,
            strategy="ma_cross",
            profile=None,
            strategies_csv="rsi_macd",
            walk_forward=False,
            train_bars=200,
            test_bars=100,
            step=None,
        )
        self.assertNotIn("error", d)
        self.assertEqual(d.get("schema"), "quant_bot_product_dossier_v1")
        self.assertIn("governance_triad", d)
        mbs = d.get("multi_strategy_briefs") or []
        self.assertEqual(len(mbs), 2)

    def test_pipeline_walk_forward_chapter_mock(self):
        d = build_dossier_pipeline(
            use_mock=True,
            days=60,
            strategy="ma_cross",
            profile=None,
            strategies_csv=None,
            walk_forward=True,
            train_bars=200,
            test_bars=100,
            step=100,
        )
        self.assertNotIn("error", d)
        wf = d.get("walk_forward_out_of_sample_chapter")
        self.assertIsNotNone(wf)
        self.assertNotIn("error", wf or {})

    def test_wf_chapter_error_pass_through(self):
        ch = build_walk_forward_chapter({"error": "too_short"})
        self.assertEqual(ch.get("error"), "too_short")


if __name__ == "__main__":
    unittest.main()
