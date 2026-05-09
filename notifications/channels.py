"""
聚合通知: 飞书 / 企微 / 通用 Webhook / Server酱(微信) / SMTP 邮件
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

from notifications.webhook import notify_text
from notifications.email_smtp import send_smtp_email
from utils.logger import get_logger

logger = get_logger("notify.channels")


def serverchan_send(sendkey: str, title: str, body: str) -> bool:
    """Server酱 Turbo: https://sct.ftqq.com/ 推送至微信服务号"""
    if not sendkey.strip():
        return False
    url = f"https://sctapi.ftqq.com/{sendkey.strip()}.send"
    data = urllib.parse.urlencode(
        {"title": title[:100], "desp": body[:32000]}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        logger.info("Server酱 通知已发送")
        return True
    except urllib.error.URLError as e:
        logger.error(f"Server酱 失败: {e}")
        return False


def notify_all(
    body: str,
    *,
    title: str = "Quant Bot",
    feishu_url: str = "",
    generic_url: str = "",
    wecom_url: str = "",
    serverchan_key: str = "",
    email_cfg: dict | None = None,
) -> None:
    """顺序调用各渠道; 配置为空则跳过。"""
    notify_text(
        body,
        feishu_url=feishu_url,
        wecom_url=wecom_url,
        generic_url=generic_url,
    )

    if serverchan_key:
        serverchan_send(serverchan_key, title, body.replace("\n", "<br/>"))

    if email_cfg and email_cfg.get("enabled"):
        send_smtp_email(
            host=email_cfg.get("host", ""),
            port=int(email_cfg.get("port", 587)),
            user=email_cfg.get("user", ""),
            password=email_cfg.get("password", ""),
            mail_from=email_cfg.get("from_addr", ""),
            mail_to=email_cfg.get("to", ""),
            subject=title,
            body=body,
            use_tls=bool(email_cfg.get("use_tls", True)),
        )


def load_notify_config_from_app():
    """延迟导入 config, 避免循环依赖"""
    import config as cfg

    email_cfg = None
    if getattr(cfg, "SMTP_ENABLED", False):
        email_cfg = {
            "enabled": True,
            "host": cfg.SMTP_HOST,
            "port": cfg.SMTP_PORT,
            "user": cfg.SMTP_USER,
            "password": cfg.SMTP_PASSWORD,
            "from_addr": cfg.SMTP_FROM,
            "to": cfg.SMTP_TO,
            "use_tls": cfg.SMTP_USE_TLS,
        }
    return {
        "feishu_url": getattr(cfg, "FEISHU_WEBHOOK_URL", ""),
        "generic_url": getattr(cfg, "GENERIC_WEBHOOK_URL", ""),
        "wecom_url": cfg.get_wecom_webhook_url(),
        "serverchan_key": getattr(cfg, "SERVERCHAN_SENDKEY", ""),
        "email_cfg": email_cfg,
    }


def notify_all_from_config(body: str, title: str = "Quant Bot") -> None:
    c = load_notify_config_from_app()
    notify_all(body, title=title, **c)
