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

STATUS_OPTIONS = ["", "OK", "Not OK", "N/A"]


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
    out: list[dict] = []
    for s in sections:
        title = s.get("title") or s.get("name") or "Section"
        items = s.get("items") or []
        items = [it for it in items if not is_removed_item(it)]
        out.append({"title": title, "items": items})
    return out


def _pdf_write(c: canvas.Canvas, left: float, top: float, y: float, text: str, *, bold: bool = False, size: int = 10):
    """Write a single line; returns updated y (with auto page break)."""
    line = 6 * mm
    if y < 18 * mm:
        c.showPage()
        y = top
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(left, y, text)
    return y - line


def _pdf_draw_image(
    c: canvas.Canvas,
    img_bytes: bytes,
    *,
    left: float,
    top: float,
    y: float,
    max_w: float,
    max_h: float,
):
    """Draw image with scaling and page breaks; returns updated y."""
    if y < 30 * mm:
        c.showPage()
        y = top

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    iw, ih = img.size
    scale = min(max_w / iw, max_h / ih)
    tw, th = iw * scale, ih * scale

    # convert to jpeg to keep PDFs smaller
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
    return y - th - 8 * mm


def build_pdf_bytes(report: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    left = 16 * mm
    top = h - 16 * mm
    y = top

    header = report["header"]
    sections = report["sections"]
    photos_by_item = report.get("photos_by_item", {})

    # Title
    y = _pdf_write(c, left, top, y, "Trane Chiller Maintenance Report", bold=True, size=14)
    y -= 2 * mm

    # Header block
    y = _pdf_write(c, left, top, y, "Report Details", bold=True, size=12)
    y = _pdf_write(c, left, top, y, f"Date: {header['date']}")
    y = _pdf_write(c, left, top, y, f"Project: {header['project']}")
    y = _pdf_write(c, left, top, y, f"Serial Number: {header['serial_number']}")
    y = _pdf_write(c, left, top, y, f"Model: {header['model']}")
    y = _pdf_write(c, left, top, y, f"Technician: {header['technician']}")
    y -= 2 * mm

    # Checklist
    y = _pdf_write(c, left, top, y, "Checklist", bold=True, size=12)

    img_max_w = w - 2 * left - 6 * mm
    img_max_h = 70 * mm
    indent = 6 * mm

    for section in sections:
        y = _pdf_write(c, left, top, y, section["title"], bold=True, size=11)
        for item in section["items"]:
            item_id = item["id"]
            label = item["label"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")

            y = _pdf_write(c, left, top, y, f"- {label} — {status or '—'}", size=10)

            if safe_text(notes):
                y = _pdf_write(c, left + indent, top, y, f"Notes: {notes}", size=10)

            # Photos for this item (no filenames / no captions)
            photos = photos_by_item.get(item_id) or []
            for p in photos:
                y = _pdf_draw_image(
                    c,
                    p["bytes"],
                    left=left + indent,
                    top=top,
                    y=y,
                    max_w=img_max_w,
                    max_h=img_max_h,
                )

        y -= 1 * mm

    # Findings / Reco
    y = _pdf_write(c, left, top, y, "Findings / Issues", bold=True, size=12)
    for ln in (report["findings"].strip() or "None").splitlines():
        y = _pdf_write(c, left, top, y, ln, size=10)
    y -= 1 * mm

    y = _pdf_write(c, left, top, y, "Recommendations / Actions", bold=True, size=12)
    for ln in (report["recommendations"].strip() or "None").splitlines():
        y = _pdf_write(c, left, top, y, ln, size=10)

    c.showPage()
    c.save()
    return buf.getvalue()


def build_docx_bytes(report: dict) -> bytes:
    doc = Document()
    header = report["header"]
    sections = report["sections"]
    photos_by_item = report.get("photos_by_item", {})

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

            photos = photos_by_item.get(item_id) or []
            for p in photos:
                img = Image.open(io.BytesIO(p["bytes"])).convert("RGB")
                img_buf = io.BytesIO()
                img.save(img_buf, format="JPEG", quality=85)
                img_buf.seek(0)
                doc.add_picture(img_buf, width=Inches(6))

    doc.add_heading("Findings / Issues", level=2)
    doc.add_paragraph(report["findings"].strip() or "None")

    doc.add_heading("Recommendations / Actions", level=2)
    doc.add_paragraph(report["recommendations"].strip() or "None")

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

    # No photos in Excel for now (keeps file small + clean)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------- UI ----------------
st.title("Trane Chiller Maintenance Report")

checklist_raw, checklist_msg = load_checklist(CHECKLIST_PATH)
sections = normalize_sections(checklist_raw)
st.caption(checklist_msg)

tab1, tab2 = st.tabs(["Create report", "Preview & export"])

if "results" not in st.session_state:
    st.session_state.results = {}

# NEW: per-item photos
if "photos_by_item" not in st.session_state:
    st.session_state.photos_by_item = {}

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

    for section in sections:
        with st.expander(section["title"], expanded=True):
            for item in section["items"]:
                item_id = item["id"]
                label = item["label"]

                if item_id not in st.session_state.results:
                    st.session_state.results[item_id] = {"status": "", "notes": ""}

                # Ensure photos bucket exists
                if item_id not in st.session_state.photos_by_item:
                    st.session_state.photos_by_item[item_id] = []

                colA, colB = st.columns([2, 3])
                with colA:
                    current_status = st.session_state.results[item_id]["status"]
                    status = st.selectbox(
                        label,
                        options=STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0,
                        key=f"status_{item_id}",
                    )

                with colB:
                    notes_required = (status == "Not OK")
                    notes_label = "Notes (required)" if notes_required else "Notes (optional)"
                    notes = st.text_input(
                        notes_label,
                        value=st.session_state.results[item_id]["notes"],
                        key=f"notes_{item_id}",
                        placeholder="Describe the issue (required for Not OK)" if notes_required else "Optional notes",
                    )
                    if notes_required and not safe_text(notes):
                        st.warning("Notes are required when status is **Not OK**.", icon="⚠️")

                st.session_state.results[item_id]["status"] = status
                st.session_state.results[item_id]["notes"] = notes

                # Photos (per item)
                with st.expander("Photos for this item", expanded=False):
                    uploads = st.file_uploader(
                        "Upload photos (jpg/png)",
                        type=["jpg", "jpeg", "png"],
                        accept_multiple_files=True,
                        key=f"photos_{item_id}",
                    )

                    # Persist current selection
                    if uploads is not None:
                        st.session_state.photos_by_item[item_id] = [{"bytes": f.getvalue()} for f in uploads]

                    # Thumbnails
                    photos = st.session_state.photos_by_item.get(item_id, [])
                    if photos:
                        cols = st.columns(3)
                        for i, p in enumerate(photos):
                            with cols[i % 3]:
                                st.image(p["bytes"], use_container_width=True)

                    # Clear button
                    if st.button("Clear photos for this item", key=f"clear_photos_{item_id}"):
                        st.session_state.photos_by_item[item_id] = []
                        # also clear uploader widget state to avoid it re-populating
                        if f"photos_{item_id}" in st.session_state:
                            st.session_state[f"photos_{item_id}"] = None
                        st.rerun()

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
        "photos_by_item": st.session_state.photos_by_item,
    }

with tab2:
    report = st.session_state.get("current_report")
    if not report:
        st.info("Fill in the report first, then come back here.")
        st.stop()

    # Validation: block export if Not OK items have empty notes
    missing_notes = []
    for section in report["sections"]:
        for item in section["items"]:
            item_id = item["id"]
            label = item["label"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")
            if status == "Not OK" and not safe_text(notes):
                missing_notes.append(label)

    if missing_notes:
        st.error(
            "Cannot export yet: some items are **Not OK** but have missing notes:\n\n- "
            + "\n- ".join(missing_notes)
        )

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

            photos = report.get("photos_by_item", {}).get(item_id) or []
            if photos:
                cols = st.columns(3)
                for i, p in enumerate(photos):
                    with cols[i % 3]:
                        st.image(p["bytes"], use_container_width=True)

    st.markdown("### Findings / Issues")
    st.write(report["findings"].strip() or "None")

    st.markdown("### Recommendations / Actions")
    st.write(report["recommendations"].strip() or "None")

    st.divider()
    st.subheader("Export (PDF / Word / Excel only)")

    file_base = f"trane_chiller_report_{h['date']}"

    export_disabled = bool(missing_notes)

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
            disabled=export_disabled,
        )
    with c2:
        st.download_button(
            "Download Word (DOCX)",
            data=docx_bytes,
            file_name=f"{file_base}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            disabled=export_disabled,
        )
    with c3:
        st.download_button(
            "Download Excel (XLSX)",
            data=xlsx_bytes,
            file_name=f"{file_base}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=export_disabled,
        )
