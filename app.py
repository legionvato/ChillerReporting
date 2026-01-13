import json, os, io
from datetime import date
import streamlit as st
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from openpyxl import Workbook

# ────────────────────────────────────────────────
# Config & constants
# ────────────────────────────────────────────────
st.set_page_config(page_title="Trane Chiller Report", layout="wide")
CHECKLIST_PATH = os.path.join("docs", "checklists", "trane_chiller_v1.json")
FOOTER = "Treimax Georgia Maintenance / Service Reporting Tool"
STATUS = ["", "OK", "Not OK", "N/A"]

# ────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────
def load_checklist():
    if not os.path.exists(CHECKLIST_PATH):
        return {"sections": []}, "Checklist file missing"
    try:
        with open(CHECKLIST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data, f"Checklist loaded"
    except Exception as e:
        return {"sections": []}, f"Checklist error: {e}"

def filter_item(it):
    lid = (it.get("id") or "").lower()
    lbl = (it.get("label") or "").lower()
    return not (lid == "safety_loto" or "loto" in lbl or "ppe" in lbl)

def normalize_checklist(data):
    return [
        {"title": s.get("title") or s.get("name") or "Section",
         "items": [it for it in s.get("items", []) if filter_item(it)]}
        for s in data.get("sections", [])
    ]

def get_summary(report):
    counts = {"OK":0, "Not OK":0, "N/A":0, "":0}
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
        l = (iid + lbl).lower()
        if st == "Not OK" and any(k in l for k in ["final", "returned to normal", "unit returned"]):
            final_bad = True
            break

    overall = "CRITICAL" if final_bad else "ATTENTION" if counts["Not OK"] else "OK"
    return {"counts": counts, "issues": issues, "overall": overall}

def validate(report):
    id2label = {it["id"]: it["label"] for sec in report["sections"] for it in sec["items"]}
    return [
        f'Notes required: {id2label.get(iid, iid)}'
        for iid, v in report.get("results", {}).items()
        if v.get("status") == "Not OK" and not (v.get("notes") or "").strip()
    ]

# ────────────────────────────────────────────────
# PDF (compact version)
# ────────────────────────────────────────────────
class MiniPDF:
    def __init__(self, title):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.w, self.h = A4
        self.x0, self.y0 = 16*mm, 16*mm
        self.x1 = self.w - 16*mm
        self.maxw = self.x1 - self.x0
        self.y = self.h - 30*mm
        self.title = title
        self._header()

    def _header(self):
        self.c.setFillColor(colors.whitesmoke)
        self.c.rect(self.x0, self.h-30*mm, self.maxw, 14*mm, fill=1, stroke=0)
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica-Bold", 13)
        self.c.drawString(self.x0+4*mm, self.h-25.5*mm, self.title)

    def _footer(self):
        self.c.setStrokeColor(colors.lightgrey)
        self.c.line(self.x0, 20*mm, self.x1, 20*mm)
        self.c.setFont("Helvetica", 8)
        self.c.setFillColor(colors.grey)
        self.c.drawCentredString((self.x0+self.x1)/2, 13*mm, FOOTER)
        self.c.drawRightString(self.x1, 13*mm, f"Page {self.c.getPageNumber()}")

    def newpage(self):
        self._footer()
        self.c.showPage()
        self._header()
        self.y = self.h - 30*mm

    def space(self, h):
        if self.y - h < 36*mm:
            self.newpage()

    def text(self, txt, size=10, bold=False, indent=0, color=colors.black):
        self.space(14)
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.setFillColor(color)
        self.c.drawString(self.x0 + indent, self.y, txt)
        self.y -= size * 1.2

    def badge(self, status, xright, ybase):
        if not status: status = "—"
        colors_map = {
            "OK": ("#EAF4EA","#7A9A7A","#2F5F2F"),
            "Not OK": ("#F7EAEA","#A05A5A","#7A1F1F"),
            "N/A": ("#F0F0F0","#9A9A9A","#5A5A5A")
        }
        fill, stroke, textc = colors_map.get(status, (colors.white, colors.gray, colors.black))
        self.c.saveState()
        self.c.setFont("Helvetica-Bold", 9)
        w = self.c.stringWidth(status, "Helvetica-Bold", 9) + 6*mm
        h = 6.5*mm
        x = xright - w
        y = ybase - 2*mm
        self.c.setFillColor(fill)
        self.c.setStrokeColor(stroke)
        self.c.roundRect(x, y, w, h, 2.2*mm, fill=1, stroke=1)
        self.c.setFillColor(textc)
        self.c.drawString(x + 3*mm, y + 1.6*mm, status)
        self.c.restoreState()

    def item(self, label, status):
        self.space(18)
        ystart = self.y
        self.c.setFont("Helvetica", 10)
        maxw = self.maxw - 32*mm
        lines = []
        words = label.split()
        line = []
        while words:
            line.append(words.pop(0))
            if self.c.stringWidth(" ".join(line), "Helvetica", 10) > maxw:
                lines.append(" ".join(line[:-1]))
                line = line[-1:]
        if line: lines.append(" ".join(line))

        for i, ln in enumerate(lines):
            self.c.drawString(self.x0, self.y, f"  {ln}" if i else f"- {ln}")
            if i == 0: self.badge(status, self.x1, self.y)
            self.y -= 12

    def photo(self, photos, keep_label=None):
        if not photos: return
        for b in photos:
            img = Image.open(io.BytesIO(b)).convert("RGB")
            iw, ih = img.size
            scale = min(self.maxw / iw, 75*mm / ih)
            tw, th = iw*scale, ih*scale
            self.space(th + 10*mm)
            self.c.drawImage(ImageReader(io.BytesIO(b)), self.x0, self.y-th, tw, th, mask="auto")
            self.y -= th + 5*mm

    def save(self):
        self._footer()
        self.c.save()
        return self.buf.getvalue()

def pdf_bytes(report):
    pdf = MiniPDF("Trane Chiller Maintenance Report")
    h = report["header"]
    sm = get_summary(report)

    pdf.text("Report Details", 12, True)
    for k in ["date","project","serial_number","model","technician"]:
        pdf.text(f"{k.replace('_',' ').title()}: {h.get(k,'—')}", indent=2*mm)

    pdf.text("Service Summary", 11, True)
    pdf.text(f"Overall: {sm['overall']}")
    pdf.text(f"Counts → OK:{sm['counts']['OK']}  Not OK:{sm['counts']['Not OK']}  N/A:{sm['counts']['N/A']}")
    pdf.text(f"Not OK: {', '.join(sm['issues'][:5]) or 'None'}")

    pdf.text("Checklist", 12, True)
    for sec in report["sections"]:
        pdf.text(sec["title"], 11, True, color=colors.darkgray)
        for it in sec["items"]:
            iid = it["id"]
            st = report["results"].get(iid, {}).get("status","—")
            pdf.item(it["label"], st)
            notes = report["results"].get(iid, {}).get("notes","").strip()
            if notes:
                pdf.text(f"Notes: {notes}", 9, indent=8*mm, color=colors.gray)
            pdf.photo(report["photos_by_item"].get(iid, []))

    for title, field in [("Findings / Issues", "findings"), ("Recommendations", "recommendations")]:
        pdf.text(title, 11, True)
        lines = [l.strip() for l in report.get(field,"").splitlines() if l.strip()]
        if not lines:
            pdf.text("• None")
        else:
            for l in lines: pdf.text(f"• {l}")

    return pdf.save()

# ────────────────────────────────────────────────
# DOCX & XLSX (kept similar — can be shortened further if needed)
# ────────────────────────────────────────────────
def docx_bytes(report):  # ← can be shortened similarly to PDF if desired
    # (implementation remains almost same — omitted for brevity here)
    # You can apply similar compaction: shorter names, less defensive gets
    doc = Document()
    # ... rest same as original ...
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

def xlsx_bytes(report):
    wb = Workbook()
    ws = wb.active
    ws.append(["Trane Chiller Maintenance Report"])
    # ... rest same ...
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

# ────────────────────────────────────────────────
# Streamlit UI (mostly unchanged — can inline some parts)
# ────────────────────────────────────────────────
st.title("Trane Chiller Maintenance Report")

checklist, msg = load_checklist()
sections = normalize_checklist(checklist)
st.caption(msg)

tab_create, tab_preview = st.tabs(["Create", "Preview & Export"])

if "results" not in st.session_state:
    st.session_state.results = {}
if "photos" not in st.session_state:
    st.session_state.photos = {}

with tab_create:
    # Report header
    c1, c2 = st.columns(2)
    with c1:
        dt = st.date_input("Date", date.today())
        proj = st.text_input("Project")
        sn = st.text_input("Serial Number")
    with c2:
        model = st.text_input("Model")
        tech = st.text_input("Technician")

    st.divider()
    st.subheader("Checklist")

    for sec in sections:
        with st.expander(sec["title"], True):
            for item in sec["items"]:
                iid = item["id"]
                st.session_state.results.setdefault(iid, {"status":"", "notes":""})
                st.session_state.photos.setdefault(iid, [])

                colA, colB = st.columns([2,3])
                with colA:
                    status = st.selectbox(
                        item["label"], STATUS,
                        index=STATUS.index(st.session_state.results[iid]["status"])
                        if st.session_state.results[iid]["status"] in STATUS else 0,
                        key=f"st_{iid}"
                    )
                with colB:
                    notes = st.text_input(
                        "Notes (required if Not OK)" if status == "Not OK" else "Notes",
                        st.session_state.results[iid]["notes"],
                        key=f"nt_{iid}",
                        placeholder="Describe issue..." if status == "Not OK" else ""
                    )
                st.session_state.results[iid].update(status=status, notes=notes)

                with st.expander("Photos"):
                    ups = st.file_uploader("...", ["jpg","jpeg","png"], True, key=f"ph_{iid}")
                    if ups:
                        st.session_state.photos[iid].extend(f.getvalue() for f in ups)
                    if st.session_state.photos[iid]:
                        cols = st.columns(3)
                        for i, b in enumerate(st.session_state.photos[iid]):
                            cols[i%3].image(b, use_container_width=True)
                        if st.button("Clear", key=f"cl_{iid}"):
                            st.session_state.photos[iid].clear()
                            st.rerun()

                st.divider()

    findings = st.text_area("Findings / Issues", height=110, key="find")
    recomm = st.text_area("Recommendations / Actions", height=110, key="rec")

    st.session_state.report = {
        "header": {"date":str(dt), "project":proj, "serial_number":sn, "model":model, "technician":tech},
        "sections": sections,
        "results": st.session_state.results,
        "photos_by_item": st.session_state.photos,
        "findings": findings,
        "recommendations": recomm
    }

with tab_preview:
    report = st.session_state.get("report")
    if not report:
        st.info("Fill report first")
        st.stop()

    errors = validate(report)
    if errors:
        st.error("Cannot export — fix:")
        for e in errors: st.write(f"• {e}")

    # Preview (same as original — can be compacted if desired)

    # Export
    pdf_data = pdf_bytes(report)
    # docx_data = docx_bytes(report)
    # xlsx_data = xlsx_bytes(report)

    c1, c2, c3 = st.columns(3)
    c1.download_button("PDF", pdf_data, f"trane_report_{report['header']['date']}.pdf", "application/pdf", disabled=bool(errors))
    # c2.download_button("Word", docx_data, ..., disabled=bool(errors))
    # c3.download_button("Excel", xlsx_data, ..., disabled=bool(errors))
