import json
import os
import io
from datetime import date
import streamlit as st
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

# Config
st.set_page_config(page_title="Trane Chiller Maintenance Report", layout="wide")
CHECKLIST_PATH = os.path.join("docs", "checklists", "trane_chiller_v1.json")
FOOTER_TEXT = "Treimax Georgia Maintenance / Service Reporting Tool"
STATUS_OPTIONS = ["", "OK", "Not OK", "N/A"]

# ─── Helpers ────────────────────────────────────────────────────────────────
def safe_text(x: str) -> str:
    return (x or "").strip()

def load_checklist(path: str):
    if not os.path.exists(path):
        return {"sections": []}, "Checklist file not found"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, "Checklist loaded"
    except Exception as e:
        return {"sections": []}, f"Checklist error: {e}"

def is_removed_item(item: dict) -> bool:
    iid = (item.get("id") or "").lower()
    lbl = (item.get("label") or "").lower()
    return iid == "safety_loto" or "loto" in lbl or "ppe" in lbl

def normalize_sections(checklist: dict) -> list:
    return [
        {
            "title": s.get("title") or s.get("name") or "Section",
            "items": [it for it in s.get("items", []) if not is_removed_item(it)]
        }
        for s in checklist.get("sections", [])
    ]

def compute_summary(report: dict) -> dict:
    counts = {"OK": 0, "Not OK": 0, "N/A": 0, "": 0}
    issues = []
    id2label = {it["id"]: it["label"] for sec in report["sections"] for it in sec["items"]}
    final_bad = False

    for iid, val in report.get("results", {}).items():
        st = val.get("status", "")
        counts[st if st in counts else ""] += 1
        if st == "Not OK":
            issues.append(id2label.get(iid, iid))

    for iid, lbl in id2label.items():
        st = report["results"].get(iid, {}).get("status", "")
        if st == "Not OK" and any(k in (iid + lbl).lower() for k in ["final", "returned to normal", "unit returned"]):
            final_bad = True
            break

    overall = "CRITICAL" if final_bad else "ATTENTION" if counts["Not OK"] else "OK"
    return {"counts": counts, "issues": issues, "overall": overall}

def validate_report(report: dict) -> list:
    id2label = {it["id"]: it["label"] for sec in report["sections"] for it in sec["items"]}
    return [
        f'Notes required: {id2label.get(iid, iid)}'
        for iid, v in report.get("results", {}).items()
        if v.get("status") == "Not OK" and not safe_text(v.get("notes", ""))
    ]

# ─── PDF Writer ─────────────────────────────────────────────────────────────
class PDFWriter:
    def __init__(self, c: canvas.Canvas, title: str):
        self.c = c
        self.title = title
        self.w, self.h = A4
        self.ml = self.mr = 16 * mm
        self.mt = self.mb = 16 * mm
        self.x0 = self.ml
        self.x1 = self.w - self.mr
        self.maxw = self.x1 - self.x0
        self.y = self.h - self.mt - 14 * mm - 2 * mm
        self._header()

    def _header(self):
        self.c.saveState()
        self.c.setFillColor(colors.whitesmoke)
        self.c.rect(self.x0, self.h - self.mt - 14 * mm, self.maxw, 14 * mm, fill=1, stroke=0)
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica-Bold", 13)
        self.c.drawString(self.x0 + 4 * mm, self.h - self.mt - 9.5 * mm, self.title)
        self.c.restoreState()

    def _footer(self):
        self.c.saveState()
        self.c.setStrokeColor(colors.lightgrey)
        self.c.line(self.x0, self.mb + 10 * mm, self.x1, self.mb + 10 * mm)
        self.c.setFillColor(colors.grey)
        self.c.setFont("Helvetica", 8)
        self.c.drawCentredString((self.x0 + self.x1) / 2, self.mb + 3.5 * mm, FOOTER_TEXT)
        self.c.drawRightString(self.x1, self.mb + 3.5 * mm, f"Page {self.c.getPageNumber()}")
        self.c.restoreState()

    def new_page(self):
        self._footer()
        self.c.showPage()
        self._header()
        self.y = self.h - self.mt - 14 * mm - 2 * mm

    def ensure_space(self, h: float):
        if self.y - h < self.mb + 18 * mm:
            self.new_page()

    def text(self, txt: str, size=10, bold=False, color=colors.black, leading=12):
        self.ensure_space(leading)
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.setFillColor(color)
        self.c.drawString(self.x0, self.y, txt)
        self.y -= leading * 0.9

    def wrapped_text(self, txt: str, size=10, bold=False, color=colors.black, leading=12, indent=0):
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.setFillColor(color)
        maxw = self.maxw - indent
        words = (txt or "").split()
        lines = []
        line = []
        while words:
            test = line + [words[0]]
            w = self.c.stringWidth(" ".join(test), self.c._fontname, size)
            if w <= maxw:
                line.append(words.pop(0))
            else:
                if line:
                    lines.append(" ".join(line))
                line = [words.pop(0)] if words else []
        if line:
            lines.append(" ".join(line))

        for ln in lines:
            self.ensure_space(leading)
            self.c.drawString(self.x0 + indent, self.y, ln)
            self.y -= leading * 0.9

    def section_title(self, title: str):
        h = 9 * mm
        self.ensure_space(h + 6 * mm)
        y = self.y - h + 2 * mm
        self.c.setFillColor(colors.HexColor("#F2F2F2"))
        self.c.rect(self.x0, y, self.maxw, h, fill=1, stroke=0)
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawString(self.x0 + 4 * mm, y + 2.8 * mm, title)
        self.y = y - 4 * mm

    def status_badge(self, status: str, right_x: float, baseline_y: float):
        status = status or "—"
        cmap = {
            "OK":    ("#E8F5E9", "#81C784", "#2E7D32"),
            "Not OK": ("#FFEBEE", "#E57373", "#C62828"),
            "N/A":   ("#F5F5F5", "#BDBDBD", "#616161")
        }
        fill, stroke, textc = cmap.get(status, (colors.white, colors.grey, colors.black))

        self.c.saveState()
        self.c.setFont("Helvetica-Bold", 9)
        tw = self.c.stringWidth(status, "Helvetica-Bold", 9)
        bw = tw + 6 * mm
        bh = 7 * mm
        x = right_x - bw
        y = baseline_y - 2 * mm
        self.c.setFillColor(fill)
        self.c.setStrokeColor(stroke)
        self.c.setLineWidth(0.7)
        self.c.roundRect(x, y, bw, bh, 2.5 * mm, fill=1, stroke=1)
        self.c.setFillColor(textc)
        self.c.drawString(x + 3 * mm, y + 1.9 * mm, status)
        self.c.restoreState()

    def checklist_item(self, label: str, status: str):
        self.c.setFont("Helvetica", 10)
        max_text_w = self.maxw - 38 * mm

        words = label.split()
        lines = []
        current = []
        while words:
            test = current + [words[0]]
            w = self.c.stringWidth(" ".join(test), "Helvetica", 10)
            if w <= max_text_w:
                current.append(words.pop(0))
            else:
                if current:
                    lines.append(" ".join(current))
                current = [words.pop(0)] if words else []

        if current:
            lines.append(" ".join(current))

        height_needed = len(lines) * 12 + 6 * mm
        self.ensure_space(height_needed)

        y_start = self.y
        for i, line in enumerate(lines):
            prefix = "- " if i == 0 else "  "
            self.c.drawString(self.x0, self.y, prefix + line)
            if i == 0:
                self.status_badge(status, self.x1, self.y)
            self.y -= 11.5

        self.y -= 2 * mm

    def photos_block(self, photos: list[bytes], item_label: str = None):
        if not photos:
            return

        max_photo_w = self.maxw
        max_photo_h = 68 * mm
        gap = 6 * mm

        for idx, b in enumerate(photos):
            img = Image.open(io.BytesIO(b)).convert("RGB")
            iw, ih = img.size
            scale = min(max_photo_w / iw, max_photo_h / ih)
            tw, th = iw * scale, ih * scale

            needed = th + gap + 8 * mm
            if self.y - needed < self.mb + 20 * mm:
                self.new_page()
                if idx > 0 and item_label:
                    self.wrapped_text(f"Photos for \"{item_label}\" (continued)", size=9, color=colors.grey, leading=11)

            y_bottom = self.y - th
            self.c.saveState()
            self.c.setStrokeColor(colors.lightgrey)
            self.c.setLineWidth(0.6)
            self.c.rect(self.x0, y_bottom, tw, th, stroke=1)
            img_buf = io.BytesIO()
            img.save(img_buf, format="JPEG", quality=82)
            img_buf.seek(0)
            self.c.drawImage(ImageReader(img_buf), self.x0, y_bottom, tw, th, mask="auto")
            self.c.restoreState()

            self.y = y_bottom - gap

    def finalize(self):
        self._footer()
        self.c.save()

def build_pdf_bytes(report: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pdf = PDFWriter(c, "Trane Chiller Maintenance Report")

    h = report["header"]
    sm = compute_summary(report)

    pdf.text("Report Details", 12, True)
    pdf.text(f"Date:          {h.get('date', '—')}")
    pdf.text(f"Project:       {h.get('project', '—')}")
    pdf.text(f"Serial Number: {h.get('serial_number', '—')}")
    pdf.text(f"Model:         {h.get('model', '—')}")
    pdf.text(f"Technician:    {h.get('technician', '—')}")

    pdf.y -= 8 * mm
    pdf.section_title("Service Summary")
    pdf.text(f"Overall: {sm['overall']}", bold=True)
    pdf.text(f"OK: {sm['counts']['OK']}    Not OK: {sm['counts']['Not OK']}    N/A: {sm['counts']['N/A']}")
    pdf.text(f"Not OK items: {', '.join(sm['issues'][:5]) or 'None'}")

    pdf.y -= 6 * mm
    pdf.section_title("Checklist")

    for sec in report["sections"]:
        pdf.section_title(sec["title"])
        for item in sec["items"]:
            iid = item["id"]
            lbl = item["label"]
            st = report["results"].get(iid, {}).get("status", "—")
            notes = safe_text(report["results"].get(iid, {}).get("notes", ""))
            photos = report.get("photos_by_item", {}).get(iid, [])

            pdf.checklist_item(lbl, st)

            if notes:
                pdf.wrapped_text(f"Notes: {notes}", size=9, color=colors.darkgray, indent=6 * mm, leading=11)

            if photos:
                pdf.photos_block(photos, lbl)

    for title, key in [("Findings / Issues", "findings"), ("Recommendations / Actions", "recommendations")]:
        pdf.section_title(title)
        lines = [ln.strip() for ln in report.get(key, "").splitlines() if ln.strip()]
        if not lines:
            pdf.text("• None")
        else:
            for ln in lines:
                pdf.wrapped_text(f"• {ln}", leading=13)

    pdf.finalize()
    return buf.getvalue()

# ─── Keep your existing DOCX / XLSX functions here ──────────────────────────
# (they were not causing the crash – you can leave them unchanged or paste them back)

# ─── Streamlit UI part remains the same as your last working version ────────
# Just make sure build_pdf_bytes uses the new PDFWriter class

# ... rest of your Streamlit code (tab1, tab2, download buttons etc.) ...
