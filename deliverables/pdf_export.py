"""
将 product dossier 导出为单页 PDF（需 fpdf2；中文依赖本机 .ttf/.ttc 或 QUANT_BOT_PDF_FONT）。
"""
from __future__ import annotations

import os
from typing import Any

from deliverables.executive_brief import format_brief_text
from deliverables.governance import governance_triad


def _font_candidates() -> list[str]:
    out: list[str] = []
    env = os.environ.get("QUANT_BOT_PDF_FONT", "").strip()
    if env:
        out.append(env)
    windir = os.environ.get("WINDIR", r"C:\Windows")
    out.extend(
        [
            os.path.join(windir, "Fonts", "simhei.ttf"),
            os.path.join(windir, "Fonts", "msyh.ttc"),
            os.path.join(windir, "Fonts", "simsun.ttc"),
        ]
    )
    return [p for p in out if p and os.path.isfile(p)]


def _dossier_text_lines(dossier: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append("Quant Bot — Product Dossier (not investment advice)")
    lines.append(f"schema: {dossier.get('schema')}  ts: {dossier.get('generated_at_unix')}")
    lines.append("")

    gt = dossier.get("governance_triad") or governance_triad()
    for key in ("tool_layer", "evidence_layer", "decision_layer"):
        b = gt.get(key) or {}
        lines.append(f"=== {b.get('title', key)} ===")
        lines.append(b.get("summary", ""))
        for c in b.get("capabilities") or []:
            lines.append(f"  - {c}")
        lines.append("")

    lines.append("=== Full-sample brief (primary) ===")
    fb = dossier.get("full_sample_brief") or {}
    lines.extend(format_brief_text(fb).splitlines())

    wf = dossier.get("walk_forward_out_of_sample_chapter")
    if wf and not wf.get("error"):
        lines.append("")
        lines.append("=== Walk-forward OOS chapter ===")
        lines.append(str(wf.get("aggregate")))
        lines.append(wf.get("disclaimer", ""))

    mbs = dossier.get("multi_strategy_briefs") or []
    if len(mbs) > 1:
        lines.append("")
        lines.append("=== Multi-strategy snapshot ===")
        for item in mbs:
            hs = (item.get("brief") or {}).get("historical_sample_summary") or {}
            lines.append(
                f"{item.get('strategy')}: ret%={hs.get('total_return_pct')} "
                f"sharpe={hs.get('sharpe')} trades={hs.get('total_trades')}"
            )
    return lines


def _lines_to_pdf(lines: list[str]) -> Any:
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise RuntimeError("请安装: pip install fpdf2") from e

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    font_set = False
    for fp in _font_candidates():
        try:
            pdf.add_font("zh", "", fp)
            pdf.set_font("zh", size=9)
            font_set = True
            break
        except (OSError, ValueError, RuntimeError):
            continue
    if not font_set:
        pdf.set_font("Helvetica", size=8)

    for para in lines:
        try:
            pdf.multi_cell(0, 4.5, para)
        except Exception:
            safe = para.encode("latin-1", errors="replace").decode("latin-1")
            pdf.multi_cell(0, 4.5, safe)
    return pdf


def render_dossier_pdf_bytes(dossier: dict[str, Any]) -> bytes:
    pdf = _lines_to_pdf(_dossier_text_lines(dossier))
    out = pdf.output(dest="S")
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)


def write_dossier_pdf(path: str, dossier: dict[str, Any]) -> None:
    data = render_dossier_pdf_bytes(dossier)
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
