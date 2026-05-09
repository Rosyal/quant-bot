"""
工具层 / 证据层 / 决策层 — 产品治理框架（写入 JSON/PDF/CRM，非监管定义）。
"""
from __future__ import annotations

from typing import Any


def governance_triad() -> dict[str, Any]:
    return {
        "tool_layer": {
            "title": "工具层",
            "summary": "本仓库提供回测、样本外（walk-forward）、纸面模拟、TCA、Web/PWA 看板等，用于提高验证效率。",
            "capabilities": [
                "统一回测与多策略对比",
                "Walk-forward 分段样本外",
                "纸面连续跑与状态持久化",
                "交易成本粗粒度 TCA",
                "看板与可选机构化仿真扩展点",
            ],
        },
        "evidence_layer": {
            "title": "证据层",
            "summary": "通过 product-brief、walk-forward 汇总、纸面轨迹与（可选）审计日志形成可展示的证据链；不自动等于盈利。",
            "capabilities": [
                "product-brief / product-dossier 结构化输出（JSON/PDF）",
                "多样本外折的统计汇总（walk-forward aggregate）",
                "纸面 JSON 状态与 Web 看板对齐",
                "CRM/官网可通过受控 API 拉取同一 JSON",
            ],
        },
        "decision_layer": {
            "title": "决策层",
            "summary": "是否实盘、仓位、适当性与合规表述必须由人与持牌/内部流程决定；软件不生成投顾结论。",
            "capabilities": [
                "交付物须附带 CLIENT.md 类披露",
                "禁止保本、稳赚等违法宣传",
                "实盘接入须单独接券商/交易所 API 与风控",
            ],
        },
    }
