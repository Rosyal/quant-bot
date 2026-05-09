"""面向交付的执行摘要、样本诊断、证据包（非投资建议）"""

from deliverables.dossier import build_product_dossier, dossier_to_json, format_dossier_text
from deliverables.executive_brief import build_brief, format_brief_text
from deliverables.runner import build_dossier_pipeline

__all__ = [
    "build_brief",
    "format_brief_text",
    "build_product_dossier",
    "dossier_to_json",
    "format_dossier_text",
    "build_dossier_pipeline",
]
