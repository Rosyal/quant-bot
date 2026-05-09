"""
将消息池摘要附加到交易/信号通知末尾 (辅助阅读, 非下单依据)。
"""
from __future__ import annotations

import config as cfg
from db.database import Database
from news.pool import format_digest_text
from utils.logger import get_logger

logger = get_logger("news.assist")


def append_news_digest_to_message(message: str, *, paper: bool = False) -> str:
    if paper:
        if not getattr(cfg, "NEWS_ASSIST_APPEND_PAPER", False):
            return message
    else:
        if not getattr(cfg, "NEWS_ASSIST_APPEND_LIVE", False):
            return message

    try:
        db = Database()
        try:
            digest = format_digest_text(db)
        finally:
            db.close()
    except OSError as e:
        logger.warning(f"消息池摘要读取失败: {e}")
        return message

    if not digest.strip():
        return message

    return (
        f"{message.rstrip()}\n\n"
        f"--- 消息池摘要 (关键词分类, 仅供参考) ---\n"
        f"{digest}\n"
        f"(非投资建议)"
    )


__all__ = ["append_news_digest_to_message"]
