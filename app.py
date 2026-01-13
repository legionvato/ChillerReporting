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

from docx import Document
from docx.shared import Inches

from openpyxl import Workbook


st.set_page_config(page_title="Trane Chiller Maintenance Report", layout="wide")

CHECKLIST_PATH = os.path.join("docs", "checklists", "trane_chiller_v1.json")


def safe_text(x: str) -> str:
    return (x or "").strip()


def load_checklist(path: str) -> tuple[dict, str]:
    if not os.path.exists(path):
        return {"name": "Checklist missing", "version": "0", "sections": []}, f"Checklist file not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, f"Loaded checklist from: {path}"
    except Exception as e:
        return {"name": "Checklist read error", "version": "0", "sections": []}, f"Failed to read checklist: {e}"


def is_removed_item(item: dict) -> bool:
    """
    Remove LOTO/PPE item(s) automatically.
    - by id: safety_loto
    - by label contains: LOTO or PPE
    """
    item_id = (item.get("id") or "").lower()
    label = (item.get("label") or "").lower()
    if item_id == "safety_loto":
        return True
    if "loto" in label or "ppe" in label:
        return True
    return False


def normalize_sections(checklist: dict) -> list[dict]:
    """
    Make checklist robust if JSON structure changes slightly.
    Expected:
      {"sections":[{"title":"...", "items":[{"id":"...", "label":"..."}]}]}
    """
    sections = checklist.get("sections") or []
    out = []
    for s in sections:
        title = s.get("title") or s.get("name") or "Section"
        items = s.get("items") or []
        # filter removed items
        items = [it for it in items if not is_removed_item(it)]
        out.append({"title": title, "items": items})
    return out


def build_pdf_bytes(report: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    left = 16 * mm
    top = h - 16 * mm
    y = top
    line = 6 * mm

    def write(text: str, bold=False, size=10):
        nonlocal y
        if y < 18 * mm:
            c.showPage()
            y = top
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(left, y, text)
        y -= line

    header = report["header"]
    sections = report["sections"]

    # Title
    write("Trane Chiller Maintenance Report", bold=True, size=14)
    y -= 2 * mm

    # Header block
    write("Report Details", bold=True, size=12)
    write(f"Date: {header['date']}")
    write(f"Project: {header['project']}")
    write(f"Serial Number: {header['serial_number']}")
    write(f"Model: {header['model']}")
    write(f"Technician: {header['technician']}")
    y -= 2 * mm

    # Checklist
    write("Checklist", bold=True, size=12)
    for section in sections:
        write(section["title"], bold=True, size=11)
        for item in section["items"]:
            item_id = item["id"]
            label = item["label"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")
            write(f"- {label} — {status or '—'}", size=10)
            if safe_text(notes):
                write(f"  Notes: {notes}", size=10)
        y -= 1 * mm

    # Findings / Reco
    write("Findings / Issues", bold=True, size=12)
    for ln in (report["findings"].strip() or "None").splitlines():
        write(ln, size=10)
    y -= 1 * mm

    write("Recommendations / Actions", bold=True, size=12)
    for ln in (report["recommendations"].strip() or "None").splitlines():
        write(ln, size=10)

    # Photos (NO filenames)
    photos = report.get("photos", [])
    if photos:
        c.showPage()
        y = top
        write("Photos", bold=True, size=12)
        y -= 2 * mm

        max_w = w - 2 * left
        max_h = 95 * mm

        for p in photos:
            if y < 30 * mm:
                c.showPage()
                y = top

            img = Image.open(io.BytesIO(p["bytes"])).convert("RGB")
            iw, ih = img.size
            scale = min(max_w / iw, max_h / ih)
            tw, th = iw * scale, ih * scale

            img_buf = io.BytesIO()
            img.save(img_buf, format="JPEG", quality=85)
            img_buf.seek(0)

            if y - th < 18 * mm:
                c.showPage()
                y = top

            c.drawImage(
                ImageReader(img_buf),
                left,
                y - th,
                width=tw,
                height=th,
                preserveAspectRatio=True,
                mask="auto",
            )
            y -= th + 10 * mm

    c.showPage()
    c.save()
    return buf.getvalue()


def build_docx_bytes(report: dict) -> bytes:
    doc = Document()
    header = report["header"]
    sections = report["sections"]

    doc.add_heading("Trane Chiller Maintenance Report", level=1)

    doc.add_heading("Report Details", level=2)
    doc.add_paragraph(f"Date: {header['date']}")
    doc.add_paragraph(f"Project: {header['project']}")
    doc.add_paragraph(f"Serial Number: {header['serial_number']}")
    doc.add_paragraph(f"Model: {header['model']}")
    doc.add_paragraph(f"Technician: {header['technician']}")

    doc.add_heading("Checklist", level=2)
    for section in sections:
        doc.add_heading(section["title"], level=3)
        for item in section["items"]:
            item_id = item["id"]
            label = item["label"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")
            doc.add_paragraph(f"{label} — {status or '—'}", style="List Bullet")
            if safe_text(notes):
                doc.add_paragraph(f"Notes: {notes}")

    doc.add_heading("Findings / Issues", level=2)
    doc.add_paragraph(report["findings"].strip() or "None")

    doc.add_heading("Recommendations / Actions", level=2)
    doc.add_paragraph(report["recommendations"].strip() or "None")

    # Photos (NO filenames)
    photos = report.get("photos", [])
    if photos:
        doc.add_heading("Photos", level=2)
        for p in photos:
            img = Image.open(io.BytesIO(p["bytes"])).convert("RGB")
            img_buf = io.BytesIO()
            img.save(img_buf, format="JPEG", quality=85)
            img_buf.seek(0)
            doc.add_picture(img_buf, width=Inches(6))

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def build_xlsx_bytes(report: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    header = report["header"]
    sections = report["sections"]

    ws.append(["Trane Chiller Maintenance Report"])
    ws.append([])
    ws.append(["Date", header["date"]])
    ws.append(["Project", header["project"]])
    ws.append(["Serial Number", header["serial_number"]])
    ws.append(["Model", header["model"]])
    ws.append(["Technician", header["technician"]])
    ws.append([])

    ws.append(["Checklist"])
    ws.append(["Section", "Item", "Status", "Notes"])

    for section in sections:
        for item in section["items"]:
            item_id = item["id"]
            label = item["label"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")
            ws.append([section["title"], label, status, notes])

    ws.append([])
    ws.append(["Findings / Issues", report["findings"].strip() or "None"])
    ws.append(["Recommendations / Actions", report["recommendations"].strip() or "None"])

    # No photos in Excel (and no filenames) per your request

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# UI
st.title("Trane Chiller Maintenance Report")

checklist_raw, checklist_msg = load_checklist(CHECKLIST_PATH)
sections = normalize_sections(checklist_raw)
st.caption(checklist_msg)

tab1, tab2 = st.tabs(["Create report", "Preview & export"])

if "results" not in st.session_state:
    st.session_state.results = {}
if "photos" not in st.session_state:
    st.session_state.photos = []

with tab1:
    st.subheader("Report details")
    c1, c2 = st.columns(2)
    with c1:
        report_date = st.date_input("Date", value=date.today())
        project = st.text_input("Project")
        serial_number = st.text_input("Serial Number")
    with c2:
        model = st.text_input("Model")
        technician = st.text_input("Technician")

    st.divider()
    st.subheader("Checklist")
    STATUS_OPTIONS = ["", "OK", "Not OK", "N/A"]

    for section in sections:
        with st.expander(section["title"], expanded=True):
            for item in section["items"]:
                item_id = item["id"]
                label = item["label"]

                if item_id not in st.session_state.results:
                    st.session_state.results[item_id] = {"status": "", "notes": ""}

                colA, colB = st.columns([2, 3])
                with colA:
                    status = st.selectbox(
                        label,
                        options=STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(st.session_state.results[item_id]["status"])
                        if st.session_state.results[item_id]["status"] in STATUS_OPTIONS
                        else 0,
                        key=f"status_{item_id}",
                    )
                with colB:
                    notes = st.text_input(
                        "Notes",
                        value=st.session_state.results[item_id]["notes"],
                        key=f"notes_{item_id}",
                        placeholder="Optional notes",
                    )

                st.session_state.results[item_id]["status"] = status
                st.session_state.results[item_id]["notes"] = notes

    st.divider()
    st.subheader("Job photos")
    uploads = st.file_uploader(
        "Upload photos (jpg/png)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if uploads is not None:
        st.session_state.photos = [{"bytes": f.getvalue()} for f in uploads]

    if st.session_state.photos:
        cols = st.columns(3)
        for i, p in enumerate(st.session_state.photos):
            with cols[i % 3]:
                # No caption/filename
                st.image(p["bytes"], use_container_width=True)

    st.divider()
    findings = st.text_area("Findings / Issues", height=120)
    recommendations = st.text_area("Recommendations / Actions", height=120)

    header = {
        "date": str(report_date),
        "project": safe_text(project),
        "serial_number": safe_text(serial_number),
        "model": safe_text(model),
        "technician": safe_text(technician),
    }

    st.session_state.current_report = {
        "header": header,
        "sections": sections,
        "results": st.session_state.results,
        "findings": findings,
        "recommendations": recommendations,
        "photos": st.session_state.photos,
    }

with tab2:
    report = st.session_state.get("current_report")
    if not report:
        st.info("Fill in the report first, then come back here.")
        st.stop()

    # Clean preview header (no JSON)
    st.subheader("Preview")
    h = report["header"]
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Date:** {h['date']}")
        st.markdown(f"**Project:** {h['project']}")
    with col2:
        st.markdown(f"**Serial Number:** {h['serial_number']}")
        st.markdown(f"**Model:** {h['model']}")
    with col3:
        st.markdown(f"**Technician:** {h['technician']}")

    st.divider()

    for section in report["sections"]:
        st.markdown(f"### {section['title']}")
        for item in section["items"]:
            item_id = item["id"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")
            st.write(f"- {item['label']} — {status or '—'}")
            if safe_text(notes):
                st.caption(f"Notes: {notes}")

    st.markdown("### Findings / Issues")
    st.write(report["findings"].strip() or "None")

    st.markdown("### Recommendations / Actions")
    st.write(report["recommendations"].strip() or "None")

    if report.get("photos"):
        st.markdown("### Photos")
        cols = st.columns(3)
        for i, p in enumerate(report["photos"]):
            with cols[i % 3]:
                st.image(p["bytes"], use_container_width=True)

    st.divider()
    st.subheader("Export (PDF / Word / Excel only)")

    file_base = f"trane_chiller_report_{h['date']}"

    pdf_bytes = build_pdf_bytes(report)
    docx_bytes = build_docx_bytes(report)
    xlsx_bytes = build_xlsx_bytes(report)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"{file_base}.pdf",
            mime="application/pdf",
        )
    with c2:
        st.download_button(
            "Download Word (DOCX)",
            data=docx_bytes,
            file_name=f"{file_base}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    with c3:
        st.download_button(
            "Download Excel (XLSX)",
            data=xlsx_bytes,
            file_name=f"{file_base}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
