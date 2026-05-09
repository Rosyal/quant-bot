"""
上线前环境与密钥粗检 (非渗透测试).

检测项: 常见占位符、过短密钥、Webhook 是否疑似误提交等。
"""
from __future__ import annotations

import os
import re
from typing import Any

_WEAK = ("changeme", "password", "123456", "secret", "test", "your_key")


def _looks_weak(s: str) -> bool:
    t = s.strip().lower()
    if len(t) < 8:
        return True
    return any(w in t for w in _WEAK)


def run_security_precheck() -> dict[str, Any]:
    issues: list[str] = []
    ok: list[str] = []

    audit_k = os.environ.get("QUANT_BOT_AUDIT_API_KEY", "").strip()
    brief_k = os.environ.get("QUANT_BOT_BRIEF_API_KEY", "").strip()
    if audit_k and _looks_weak(audit_k):
        issues.append("QUANT_BOT_AUDIT_API_KEY 过短或疑似弱口令")
    elif audit_k:
        ok.append("已配置 QUANT_BOT_AUDIT_API_KEY (长度合理)")

    if brief_k and _looks_weak(brief_k):
        issues.append("QUANT_BOT_BRIEF_API_KEY 过短或疑似弱口令")
    elif brief_k:
        ok.append("已配置 QUANT_BOT_BRIEF_API_KEY")

    for name in ("FEISHU_WEBHOOK_URL", "WECOM_WEBHOOK_URL", "GENERIC_WEBHOOK_URL"):
        v = os.environ.get(name, "").strip()
        if not v:
            continue
        if "your_" in v.lower() or "example.com" in v.lower():
            issues.append(f"{name} 疑似占位符")

    smtp_p = os.environ.get("SMTP_PASSWORD", "").strip()
    if smtp_p and len(smtp_p) < 6:
        issues.append("SMTP_PASSWORD 过短")

    # 仓库内 config 不应出现硬编码真实密钥 (粗检常见模式)
    try:
        import config as cfg

        for attr in ("FEISHU_WEBHOOK_URL", "SMTP_PASSWORD"):
            val = str(getattr(cfg, attr, "") or "")
            if re.search(r"sk-[a-zA-Z0-9]{10,}", val):
                issues.append(f"config.{attr} 疑似含 API 密钥形态, 应改用环境变量")
    except Exception:
        pass

    return {
        "issues": issues,
        "ok_hints": ok,
        "recommendations": [
            "生产环境使用专用密钥管理服务 (KMS/Vault)",
            "定期轮换 Webhook URL 与 API Key",
            "对 quant_bot.db 做加密存储与访问审计 (操作系统层)",
        ],
        "passed": len(issues) == 0,
    }
