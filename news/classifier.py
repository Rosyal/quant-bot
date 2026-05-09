"""
基于关键词的消息分类与粗情绪打分 (非 NLP 模型, 可后续接 LLM)。

分类: regulation / security / exchange / macro / market / tech / nft_defi / general
情绪: bullish / bearish / neutral
"""
from __future__ import annotations

import json
import re
from typing import Any

# (关键词子串, 类别) 按优先级从前到后匹配, 命中即定类
_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("sec ", "regulation"),
    ("sec,", "regulation"),
    ("cftc", "regulation"),
    ("regulation", "regulation"),
    ("lawsuit", "regulation"),
    ("监管", "regulation"),
    ("立法", "regulation"),
    ("合规", "regulation"),
    ("hack", "security"),
    ("exploit", "security"),
    ("stolen", "security"),
    ("phishing", "security"),
    ("黑客", "security"),
    ("被盗", "security"),
    ("漏洞", "security"),
    ("listing", "exchange"),
    ("delist", "exchange"),
    ("交易所", "exchange"),
    ("binance", "exchange"),
    ("coinbase", "exchange"),
    ("fed ", "macro"),
    ("fomc", "macro"),
    ("cpi ", "macro"),
    ("inflation", "macro"),
    ("加息", "macro"),
    ("降息", "macro"),
    ("非农", "macro"),
    ("bitcoin etf", "market"),
    ("btc ", "market"),
    ("ethereum", "market"),
    ("eth ", "market"),
    ("比特币", "market"),
    ("以太坊", "market"),
    ("upgrade", "tech"),
    ("fork", "tech"),
    ("layer-2", "tech"),
    ("升级", "tech"),
    ("nft", "nft_defi"),
    ("defi", "nft_defi"),
)

_BULLISH: tuple[str, ...] = (
    "surge",
    "rally",
    "soar",
    "jump",
    "gain",
    "bull",
    "breakout",
    "record high",
    "all-time high",
    "ath",
    "approval",
    "adoption",
    "看涨",
    "上涨",
    "大涨",
    "突破",
    "新高",
    "利好",
)

_BEARISH: tuple[str, ...] = (
    "plunge",
    "crash",
    "tumble",
    "slump",
    "bear",
    "liquidat",
    "ban",
    "crackdown",
    "fraud",
    "scam",
    "看跌",
    "下跌",
    "暴跌",
    "崩盘",
    "利空",
    "禁令",
    "调查",
)


def _norm_text(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\s+", " ", t)
    return t


def classify_news_text(title: str, summary: str = "") -> dict[str, Any]:
    blob = _norm_text(f"{title} {summary}")
    category = "general"
    for kw, cat in _CATEGORY_RULES:
        if kw in blob:
            category = cat
            break

    bull_hits = [w for w in _BULLISH if w in blob]
    bear_hits = [w for w in _BEARISH if w in blob]
    score = len(bull_hits) - len(bear_hits)
    score = max(-5, min(5, score))
    if score > 0:
        sentiment = "bullish"
    elif score < 0:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    tags = list(dict.fromkeys(bull_hits[:4] + bear_hits[:4]))[:8]

    return {
        "category": category,
        "sentiment": sentiment,
        "sentiment_score": score,
        "tags_json": json.dumps(tags, ensure_ascii=False),
    }


__all__ = ["classify_news_text"]
