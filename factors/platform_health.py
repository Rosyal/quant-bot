"""
因子与另类数据平台 — 健康检查与注册表 (对内 API / ops-readiness).
"""
from __future__ import annotations

import importlib
from typing import Any

import config as cfg
from alternative_data.sentiment_csv import sentiment_stub_status


def factor_module_names() -> tuple[str, ...]:
    return (
        "factors.cross_section",
        "factors.risk_model",
        "factors.style_factors",
    )


def platform_health() -> dict[str, Any]:
    sentiment_path = str(getattr(cfg, "ALT_DATA_SENTIMENT_CSV", "") or "")
    alt = sentiment_stub_status(sentiment_path)
    mods: list[dict[str, Any]] = []
    for name in factor_module_names():
        try:
            importlib.import_module(name)
            mods.append({"module": name, "import_ok": True})
        except Exception as e:  # noqa: BLE001
            mods.append({"module": name, "import_ok": False, "error": str(e)})
    return {
        "alternative_data": alt,
        "factor_modules": mods,
        "note": "另类数据与因子为研究扩展点; 不构成投资建议。",
    }
