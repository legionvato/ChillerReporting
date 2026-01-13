import json
import os
import io
from datetime import date

import streamlit as st
from PIL import Image

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from docx import Document
from docx.shared import Inches

from openpyxl import Workbook


st.set_page_config(page_title="Trane Chiller Maintenance Report", layout="wide")

CHECKLIST_PATH = os.path.join("docs", "checklists", "trane_chiller_v1.json")


def default_checklist() -> dict:
    return {
        "name": "Trane Chiller Maintenance Checklist (Built-in fallback)",
        "version": "1.0",
        "sections": [
            {"title": "Safety & Pre-check", "items": [
                {"id": "safety_loto", "label": "LOTO/PPE confirmed"},
                {"id": "safety_area", "label": "Work area safe / no hazards observed"},
            ]},
            {"title": "Visual Inspection", "items": [
                {"id": "visual_leaks", "label": "No evidence of oil/refrigerant leaks"},
                {"id": "visual_vibration", "label": "No abnormal noise/vibration"},
            ]},
            {"title": "Electrical", "items": [
                {"id": "elec_panel", "label": "Main disconnect / panel condition OK"},
                {"id": "elec_wiring", "label": "Wiring/terminals tight/clean (no discoloration)"},
            ]},
            {"title": "Final Status", "items": [
                {"id": "final_operation", "label": "Unit returned to normal operation"},
                {"id": "final_followup", "label": "Follow-up required (describe in notes)"},
            ]},
        ],
    }


def load_checklist(path: str) -> tuple[dict, str]:
    if not os.path.exists(path):
        return default_checklist(), f"Checklist file not found at: {path} — using built-in fallback."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), f"Loaded checklist from: {path}"
    except Exception as e:
        return default_checklist(), f"Failed to read checklist file ({e}) — using built-in fallback."


def safe_text(x: str) -> str:
    return (x or "").strip()


def build_pdf_bytes(report: dict) -> bytes:
    """
    Simple, reliable PDF generator using reportlab.
    Includes photos (scaled) appended at the end.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    left = 18 * mm
    top = h - 18 * mm
    y = top
    line = 6 * mm

    def write(text: str, bold=False):
        nonlocal y
        if y < 20 * mm:
            c.showPage()
            y = top
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawString(left, y, text)
        y -= line

    header = report["header"]
    write("Trane Chiller Maintenance Report", bold=True)
    y -= 2 * mm

    write("Report Header", bold=True)
    write(f"Date: {header['date']}")
    write(f"Project: {header['project']}")
    write(f"Serial Number: {header['serial_number']}")
    write(f"Model: {header['model']}")
    write(f"Technician: {header['technician']}")
    y -= 2 * mm

    write("Checklist", bold=True)
    for section in report["checklist"].get("sections", []):
        write(section["title"], bold=True)
        for item in section.get("items", []):
            item_id = item["id"]
            label = item["label"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")
            write(f"- {label} — {status or '—'}")
            if safe_text(notes):
                write(f"  Notes: {notes}")
        y -= 1 * mm

    write("Findings / Issues", bold=True)
    for paragraph in (report["findings"].strip() or "None").splitlines():
        write(paragraph)

    y -= 1 * mm
    write("Recommendations / Actions", bold=True)
    for paragraph in (report["recommendations"].strip() or "None").splitlines():
        write(paragraph)

    # Photos
    photos = report.get("photos", [])
    if photos:
        c.showPage()
        y = top
        write("Photos", bold=True)
        y -= 2 * mm

        max_w = w - 2 * left
        max_h = 90 * mm  # each photo block height

        for p in photos:
            if y < 30 * mm:
                c.showPage()
                y = top

            write(f"{p['name']}", bold=True)
            # Render image scaled to fit max_w x max_h
            img = Image.open(io.BytesIO(p["bytes"])).convert("RGB")
            iw, ih = img.size
            scale = min(max_w / iw, max_h / ih)
            tw, th = iw * scale, ih * scale

            img_buf = io.BytesIO()
            img.save(img_buf, format="JPEG", quality=85)
            img_buf.seek(0)

            if y - th < 20 * mm:
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


# reportlab helper
from reportlab.lib.utils import ImageReader


def build_docx_bytes(report: dict) -> bytes:
    doc = Document()
    header = report["header"]

    doc.add_heading("Trane Chiller Maintenance Report", level=1)

    doc.add_heading("Report Header", level=2)
    doc.add_paragraph(f"Date: {header['date']}")
    doc.add_paragraph(f"Project: {header['project']}")
    doc.add_paragraph(f"Serial Number: {header['serial_number']}")
    doc.add_paragraph(f"Model: {header['model']}")
    doc.add_paragraph(f"Technician: {header['technician']}")

    doc.add_heading("Checklist", level=2)
    for section in report["checklist"].get("sections", []):
        doc.add_heading(section["title"], level=3)
        for item in section.get("items", []):
            item_id = item["id"]
            label = item["label"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")
            p = doc.add_paragraph(f"{label} — {status or '—'}", style="List Bullet")
            if safe_text(notes):
                doc.add_paragraph(f"Notes: {notes}")

    doc.add_heading("Findings / Issues", level=2)
    doc.add_paragraph(report["findings"].strip() or "None")

    doc.add_heading("Recommendations / Actions", level=2)
    doc.add_paragraph(report["recommendations"].strip() or "None")

    photos = report.get("photos", [])
    if photos:
        doc.add_heading("Photos", level=2)
        for p in photos:
            doc.add_paragraph(p["name"])
            img = Image.open(io.BytesIO(p["bytes"])).convert("RGB")
            img_buf = io.BytesIO()
            img.save(img_buf, format="JPEG", quality=85)
            img_buf.seek(0)
            # 6 inches wide max
            doc.add_picture(img_buf, width=Inches(6))

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def build_xlsx_bytes(report: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    header = report["header"]
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

    for section in report["checklist"].get("sections", []):
        for item in section.get("items", []):
            item_id = item["id"]
            label = item["label"]
            status = report["results"].get(item_id, {}).get("status", "")
            notes = report["results"].get(item_id, {}).get("notes", "")
            ws.append([section["title"], label, status, notes])

    ws.append([])
    ws.append(["Findings / Issues", report["findings"].strip() or "None"])
    ws.append(["Recommendations / Actions", report["recommendations"].strip() or "None"])

    photos = report.get("photos", [])
    if photos:
        ws.append([])
        ws.append(["Photos (filenames only)"])
        for p in photos:
            ws.append([p["name"]])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


st.title("Trane Chiller Maintenance Report")
checklist, checklist_msg = load_checklist(CHECKLIST_PATH)
st.caption(checklist_msg)

tab1, tab2 = st.tabs(["1) Create report", "2) Preview & export"])

if "results" not in st.session_state:
    st.session_state.results = {}
if "photos" not in st.session_state:
    st.session_state.photos = []

with tab1:
    st.subheader("Report header")
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

    for section in checklist.get("sections", []):
        with st.expander(section["title"], expanded=True):
            for item in section.get("items", []):
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
    st.caption("Upload photos from the job. They will be shown in the report and included in PDF/DOCX exports.")
    uploads = st.file_uploader(
        "Upload photos (jpg/png)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if uploads:
        # Replace current photos with latest selection
        photos = []
        for f in uploads:
            photos.append({"name": f.name, "bytes": f.getvalue()})
        st.session_state.photos = photos

    if st.session_state.photos:
        cols = st.columns(3)
        for i, p in enumerate(st.session_state.photos):
            with cols[i % 3]:
                st.image(p["bytes"], caption=p["name"], use_container_width=True)

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
        "checklist": checklist,
        "results": st.session_state.results,
        "findings": findings,
        "recommendations": recommendations,
        "photos": st.session_state.photos,
    }

with tab2:
    report = st.session_state.get("current_report")
    if not report:
        st.info("Fill in the report on the first tab, then come back here.")
        st.stop()

    missing = [k for k, v in report["header"].items() if k != "date" and not v]
    if missing:
        st.warning(f"Missing fields: {', '.join(missing)} (you can still export).")

    st.subheader("Preview (web)")
    st.write("Header:", report["header"])

    st.write("Checklist:")
    for section in report["checklist"].get("sections", []):
        st.markdown(f"### {section['title']}")
        for item in section.get("items", []):
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
                st.image(p["bytes"], caption=p["name"], use_container_width=True)

    st.divider()
    st.subheader("Export")

    pdf_bytes = build_pdf_bytes(report)
    docx_bytes = build_docx_bytes(report)
    xlsx_bytes = build_xlsx_bytes(report)

    file_base = f"trane_chiller_report_{report['header']['date']}"

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
