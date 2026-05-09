"""消息池: 分类、去重哈希、入库幂等"""
from __future__ import annotations

import os
import tempfile
import unittest

from db.database import Database
from news.classifier import classify_news_text
from news.pool import make_content_hash


class TestNewsClassifier(unittest.TestCase):
    def test_regulation_keyword(self):
        r = classify_news_text("SEC charges firm", "")
        self.assertEqual(r["category"], "regulation")

    def test_security_hack(self):
        r = classify_news_text("Exchange hack drains wallets", "")
        self.assertEqual(r["category"], "security")

    def test_sentiment_bullish(self):
        r = classify_news_text("Bitcoin rally to record high", "")
        self.assertEqual(r["sentiment"], "bullish")
        self.assertGreater(r["sentiment_score"], 0)

    def test_sentiment_bearish(self):
        r = classify_news_text("Market crash and liquidation wave", "")
        self.assertEqual(r["sentiment"], "bearish")
        self.assertLess(r["sentiment_score"], 0)

    def test_general_fallback(self):
        r = classify_news_text("Weekly digest", "no strong keywords")
        self.assertEqual(r["category"], "general")


class TestNewsPoolHash(unittest.TestCase):
    def test_content_hash_stable(self):
        a = make_content_hash("https://x/y", "Title A")
        b = make_content_hash("https://x/y", "Title A")
        self.assertEqual(a, b)

    def test_content_hash_different_title(self):
        a = make_content_hash("https://x/y", "A")
        b = make_content_hash("https://x/y", "B")
        self.assertNotEqual(a, b)


class TestNewsInsertDedup(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.path)

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_insert_ignore_duplicate(self):
        now = 1_700_000_000
        row = {
            "content_hash": "abc_hash",
            "feed_url": "https://feed",
            "title": "T",
            "link": "https://l",
            "summary": "s",
            "published_at": now,
            "fetched_at": now,
            "category": "general",
            "sentiment": "neutral",
            "sentiment_score": 0,
            "tags_json": "[]",
        }
        self.assertTrue(self.db.insert_news_item(row))
        self.assertFalse(self.db.insert_news_item(row))
        rows = self.db.list_news_items(limit=10)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
