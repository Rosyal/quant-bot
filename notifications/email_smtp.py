"""SMTP 邮件通知 (纯标准库)"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

from utils.logger import get_logger

logger = get_logger("notify.email")


def send_smtp_email(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    mail_from: str,
    mail_to: str,
    subject: str,
    body: str,
    use_tls: bool = True,
) -> bool:
    if not host or not mail_to:
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Quant Bot", mail_from)) if mail_from else user
    msg["To"] = mail_to
    try:
        if use_tls:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls()
                if user:
                    s.login(user, password)
                s.sendmail(mail_from or user, [mail_to], msg.as_string())
        else:
            with smtplib.SMTP_SSL(host, port, timeout=20) as s:
                if user:
                    s.login(user, password)
                s.sendmail(mail_from or user, [mail_to], msg.as_string())
        logger.info("邮件已发送")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False
