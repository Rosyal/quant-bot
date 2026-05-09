"""RSS 2.0 / Atom 轻量抓取 (标准库, 无 feedparser 依赖)"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from utils.logger import get_logger

logger = get_logger("news.rss")

_USER_AGENT = "QuantBot-NewsPool/1.0 (+https://github.com)"


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _child_text(el: ET.Element, *names: str) -> str:
    for ch in el:
        t = _strip_ns(ch.tag)
        if t in names:
            return (ch.text or "").strip()
    return ""


def _child_links(el: ET.Element) -> str:
    for ch in el:
        t = _strip_ns(ch.tag)
        if t == "link":
            href = ch.attrib.get("href") or ch.text or ""
            if href.strip():
                return href.strip()
    return ""


def _parse_rfc822_like(s: str) -> int | None:
    if not s:
        return None
    s = s.strip()
    if "T" in s and len(s) >= 10:
        try:
            from datetime import datetime

            iso = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            return int(dt.timestamp())
        except (TypeError, ValueError, OSError, OverflowError):
            pass
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(s)
        if dt:
            return int(dt.timestamp())
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def fetch_feed_items(
    feed_url: str,
    *,
    timeout: float = 20.0,
    max_items: int = 30,
) -> list[dict[str, Any]]:
    req = urllib.request.Request(
        feed_url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.URLError as e:
        logger.error(f"RSS 拉取失败 {feed_url}: {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        logger.error(f"RSS 解析失败 {feed_url}: {e}")
        return []

    tag = _strip_ns(root.tag)
    items: list[dict[str, Any]] = []

    if tag == "rss":
        channel = None
        for ch in root:
            if _strip_ns(ch.tag) == "channel":
                channel = ch
                break
        if channel is None:
            return []
        for ch in channel:
            if _strip_ns(ch.tag) != "item":
                continue
            title = _child_text(ch, "title")
            link = _child_text(ch, "link") or _child_links(ch)
            summary = _child_text(ch, "description", "summary", "content")
            summary = re.sub(r"<[^>]+>", "", summary)[:2000]
            pub = _child_text(ch, "pubDate", "published", "updated")
            ts = _parse_rfc822_like(pub) or int(time.time())
            if title:
                items.append(
                    {
                        "title": title[:500],
                        "link": link[:2000],
                        "summary": summary,
                        "published_at": ts,
                    }
                )
    elif tag == "feed":
        for ch in root:
            if _strip_ns(ch.tag) != "entry":
                continue
            title = _child_text(ch, "title")
            link = _child_links(ch) or _child_text(ch, "id")
            summary = _child_text(ch, "summary", "content")
            if not summary:
                for sub in ch:
                    if _strip_ns(sub.tag) == "content":
                        summary = (sub.text or "").strip()
                        break
            summary = re.sub(r"<[^>]+>", "", summary)[:2000]
            pub = _child_text(ch, "updated", "published")
            ts = _parse_rfc822_like(pub) or int(time.time())
            if title:
                items.append(
                    {
                        "title": title[:500],
                        "link": link[:2000],
                        "summary": summary,
                        "published_at": ts,
                    }
                )

    return items[:max_items]


__all__ = ["fetch_feed_items"]
