
from __future__ import annotations
from typing import Any, Dict
import io

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

def _df_to_table(df: pd.DataFrame, col_widths=None):
    data = [list(df.columns)] + df.fillna("").astype(str).values.tolist()
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f0f0f0")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fafafa")]),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    return t

def build_pdf_report(a: Dict[str, Any], b: Dict[str, Any], comparison: pd.DataFrame, opex: pd.DataFrame, title: str="Report") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>Option A:</b> {a.get('_file_name','')}", styles["Normal"]))
    story.append(Paragraph(f"<b>Option B:</b> {b.get('_file_name','')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Comparison", styles["Heading2"]))
    story.append(_df_to_table(comparison, col_widths=[160, 140, 140, 80]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("OPEX / Payback Summary", styles["Heading2"]))
    story.append(_df_to_table(opex, col_widths=[220, 130, 130]))
    story.append(PageBreak())

    # Optional: include raw extracted text length note (debug)
    story.append(Paragraph("Extraction notes", styles["Heading2"]))
    story.append(Paragraph("Values are extracted from datasheets automatically and may require verification. If you edited any fields in the app, those edits are reflected here.", styles["Normal"]))
    story.append(Spacer(1, 10))

    doc.build(story)
    return buf.getvalue()
