"""
通知模块 — 支持 Telegram / 飞书 / Server酱
"""
import json
import urllib.request
import urllib.error
from utils.logger import get_logger
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FEISHU_WEBHOOK_URL, SERVERCHAN_SENDKEY

logger = get_logger("notification.notifier")


class Notifier:
    """多渠道通知"""

    def __init__(self):
        self.telegram_token = TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = TELEGRAM_CHAT_ID
        self.feishu_webhook = FEISHU_WEBHOOK_URL
        self.serverchan_key = SERVERCHAN_SENDKEY

    def send(self, title: str, message: str):
        """发送通知到所有已配置的渠道"""
        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(title, message)
        if self.feishu_webhook:
            self._send_feishu(title, message)
        if self.serverchan_key:
            self._send_serverchan(title, message)

    def _send_telegram(self, title: str, message: str):
        try:
            text = f"*{title}*\n{message}"
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = json.dumps({"chat_id": self.telegram_chat_id, "text": text, "parse_mode": "Markdown"}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            logger.info("Telegram 通知已发送")
        except Exception as e:
            logger.warning(f"Telegram 通知失败: {e}")

    def _send_feishu(self, title: str, message: str):
        try:
            data = json.dumps({"msg_type": "interactive", "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": message}],
            }}).encode()
            req = urllib.request.Request(self.feishu_webhook, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            logger.info("飞书通知已发送")
        except Exception as e:
            logger.warning(f"飞书通知失败: {e}")

    def _send_serverchan(self, title: str, message: str):
        try:
            url = f"https://sctapi.ftqq.com/{self.serverchan_key}.send"
            data = json.dumps({"title": title, "desp": message}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            logger.info("Server酱通知已发送")
        except Exception as e:
            logger.warning(f"Server酱通知失败: {e}")
