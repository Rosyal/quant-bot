"""
消息池: 拉取 RSS → 分类 → 入库 (SQLite news_items)
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

import config as cfg
from db.database import Database
from news.classifier import classify_news_text
from news.rss_fetch import fetch_feed_items
from utils.logger import get_logger

logger = get_logger("news.pool")


def make_content_hash(link: str, title: str) -> str:
    key = f"{link or ''}\n{title or ''}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def sync_news_pool(db: Database | None = None) -> dict[str, Any]:
    """从 config.NEWS_RSS_FEEDS 同步; 返回统计。"""
    feeds = tuple(getattr(cfg, "NEWS_RSS_FEEDS", ()) or ())
    if not feeds:
        logger.warning("NEWS_RSS_FEEDS 为空, 跳过同步 (可在 config.py 配置)")
        return {"inserted": 0, "fetched": 0, "feeds": 0}

    timeout = float(getattr(cfg, "NEWS_FETCH_TIMEOUT_SEC", 20))
    per_feed = int(getattr(cfg, "NEWS_MAX_ITEMS_PER_FEED", 25))
    close_db = False
    if db is None:
        db = Database()
        close_db = True

    inserted = 0
    fetched = 0
    now = int(time.time())
    try:
        for url in feeds:
            u = (url or "").strip()
            if not u:
                continue
            items = fetch_feed_items(u, timeout=timeout, max_items=per_feed)
            fetched += len(items)
            for it in items:
                title = it.get("title") or ""
                link = it.get("link") or ""
                summary = it.get("summary") or ""
                pub = int(it.get("published_at") or now)
                ch = make_content_hash(link, title)
                cls = classify_news_text(title, summary)
                row = {
                    "content_hash": ch,
                    "feed_url": u,
                    "title": title,
                    "link": link,
                    "summary": summary[:4000],
                    "published_at": pub,
                    "fetched_at": now,
                    "category": cls["category"],
                    "sentiment": cls["sentiment"],
                    "sentiment_score": cls["sentiment_score"],
                    "tags_json": cls["tags_json"],
                }
                if db.insert_news_item(row):
                    inserted += 1
        logger.info(f"消息池同步完成: 抓取约 {fetched} 条, 新入库 {inserted} 条")
        return {"inserted": inserted, "fetched": fetched, "feeds": len(feeds)}
    finally:
        if close_db:
            db.close()


def format_digest_text(
    db: Database,
    *,
    hours: int | None = None,
    max_items: int | None = None,
) -> str:
    """供通知/看板附带的纯文本摘要。"""
    h = hours if hours is not None else int(getattr(cfg, "NEWS_DIGEST_HOURS", 48))
    m = max_items if max_items is not None else int(getattr(cfg, "NEWS_DIGEST_MAX_ITEMS", 4))
    since = int(time.time()) - max(1, h) * 3600
    rows = db.list_news_items(limit=max(1, m), since_ts=since)
    if not rows:
        return ""
    lines = []
    for r in rows:
        title = (r.get("title") or "")[:100]
        cat = r.get("category") or "?"
        sent = r.get("sentiment") or "?"
        lines.append(f"· [{cat}/{sent}] {title}")
    return "\n".join(lines)


__all__ = ["sync_news_pool", "format_digest_text", "make_content_hash"]
