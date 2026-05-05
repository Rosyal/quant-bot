"""
Webhook 通知: 飞书机器人 / 通用 HTTP JSON
无 URL 时仅打日志, 不抛错。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from utils.logger import get_logger

logger = get_logger("notify")


def _post_json(url: str, payload: dict[str, Any], timeout: float = 10.0) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except urllib.error.URLError as e:
        logger.error(f"Webhook 请求失败: {e}")
        return False


def feishu_text(webhook_url: str, text: str) -> bool:
    """飞书自定义机器人 text 消息"""
    body = {"msg_type": "text", "content": {"text": text}}
    return _post_json(webhook_url, body)


def wecom_group_bot_text(webhook_url: str, text: str) -> bool:
    """企业微信群机器人 text（官方文档 msgtype=text）"""
    body = {"msgtype": "text", "text": {"content": text}}
    return _post_json(webhook_url, body)


def generic_json_webhook(url: str, payload: dict[str, Any]) -> bool:
    return _post_json(url, payload)


def notify_text(
    text: str,
    *,
    feishu_url: str = "",
    wecom_url: str = "",
    generic_url: str = "",
    generic_payload_builder=None,
) -> None:
    """
    :param wecom_url: 企业微信群机器人 Webhook 完整 URL; 空则尝试 config.get_wecom_webhook_url()
    :param generic_payload_builder: 可选 callable(str) -> dict, 用于钉钉等自定义体
    """
    text = text.strip()
    if not text:
        return

    wcom = wecom_url.strip()
    if not wcom:
        try:
            from config import get_wecom_webhook_url

            wcom = get_wecom_webhook_url()
        except Exception:
            wcom = ""

    if feishu_url:
        if feishu_text(feishu_url, text):
            logger.info("已发送飞书通知")

    if wcom:
        if wecom_group_bot_text(wcom, text):
            logger.info("已发送企业微信(群机器人)通知")

    if generic_url:
        if generic_payload_builder:
            payload = generic_payload_builder(text)
        else:
            payload = {"text": text, "msg_type": "text"}
        if generic_json_webhook(generic_url, payload):
            logger.info("已发送通用 Webhook")

    if not feishu_url and not wcom and not generic_url:
        logger.info(f"[通知未配置 Webhook] {text}")
