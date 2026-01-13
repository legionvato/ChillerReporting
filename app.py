import json
import os
from datetime import date

import streamlit as st

st.set_page_config(page_title="Trane Chiller Maintenance Report", layout="wide")

CHECKLIST_PATH = os.path.join("docs", "checklists", "trane_chiller_v1.json")


def default_checklist() -> dict:
    return {
        "name": "Trane Chiller Maintenance Checklist (Built-in fallback)",
        "version": "1.0",
        "sections": [
            {
                "title": "Safety & Pre-check",
                "items": [
                    {"id": "safety_loto", "label": "LOTO/PPE confirmed"},
                    {"id": "safety_area", "label": "Work area safe / no hazards observed"},
                ],
            },
            {
                "title": "Visual Inspection",
                "items": [
                    {"id": "visual_leaks", "label": "No evidence of oil/refrigerant leaks"},
                    {"id": "visual_vibration", "label": "No abnormal noise/vibration"},
                    {"id": "visual_corrosion", "label": "No corrosion/damage observed"},
                ],
            },
            {
                "title": "Electrical",
                "items": [
                    {"id": "elec_panel", "label": "Main disconnect / panel condition OK"},
                    {"id": "elec_wiring", "label": "Wiring/terminals tight/clean (no discoloration)"},
                    {"id": "elec_amps", "label": "Compressor amps checked (record in notes)"},
                ],
            },
            {
                "title": "Refrigerant & Oil",
                "items": [
                    {"id": "ref_oil_level", "label": "Oil level/condition checked"},
                    {"id": "ref_leaks", "label": "No refrigerant leak indications"},
                ],
            },
            {
                "title": "Water Side",
                "items": [
                    {"id": "water_temps", "label": "Entering/leaving water temperatures recorded"},
                    {"id": "water_flow", "label": "Flow/DP indication normal"},
                    {"id": "water_strainers", "label": "Strainers checked/cleaned (if applicable)"},
                ],
            },
            {
                "title": "Controls & Alarms",
                "items": [
                    {"id": "ctrl_display", "label": "Controller display/operation OK"},
                    {"id": "ctrl_alarms", "label": "Alarm history reviewed"},
                ],
            },
            {
                "title": "Cleaning / Housekeeping",
                "items": [
                    {"id": "clean_general", "label": "Unit/panels reasonably clean and dry"},
                ],
            },
            {
                "title": "Final Status",
                "items": [
                    {"id": "final_operation", "label": "Unit returned to normal operation"},
                    {"id": "final_followup", "label": "Follow-up required (describe in notes)"},
                ],
            },
        ],
    }


def load_checklist(path: str) -> tuple[dict, bool, str]:
    """
    Returns: (checklist_dict, loaded_from_file, message)
    """
    if not os.path.exists(path):
        return default_checklist(), False, f"Checklist file not found at: {path} — using built-in fallback."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), True, f"Loaded checklist from: {path}"
    except Exception as e:
        return default_checklist(), False, f"Failed to read checklist file ({e}) — using built-in fallback."


def build_report_md(header: dict, checklist: dict, results: dict, findings: str, recommendations: str) -> str:
    lines = []
    lines.append("# Trane Chiller Maintenance Report\n")

    lines.append("## Report Header")
    lines.append(f"- **Date:** {header['date']}")
    lines.append(f"- **Project:** {header['project']}")
    lines.append(f"- **Serial Number:** {header['serial_number']}")
    lines.append(f"- **Model:** {header['model']}")
    lines.append(f"- **Technician:** {header['technician']}")
    lines.append("")

    lines.append("## Checklist")
    for section in checklist.get("sections", []):
        lines.append(f"### {section['title']}")
        for item in section.get("items", []):
            item_id = item["id"]
            label = item["label"]
            status = results.get(item_id, {}).get("status", "")
            notes = results.get(item_id, {}).get("notes", "")
            lines.append(f"- **{label}** — {status if status else '—'}")
            if notes.strip():
                lines.append(f"  - Notes: {notes.strip()}")
        lines.append("")

    lines.append("## Findings / Issues")
    lines.append(findings.strip() if findings.strip() else "_None_")
    lines.append("")

    lines.append("## Recommendations / Actions")
    lines.append(recommendations.strip() if recommendations.strip() else "_None_")
    lines.append("")

    lines.append("---")
    lines.append("**Signature (Technician):** ___________________________")
    return "\n".join(lines)


st.title("Trane Chiller Maintenance Report")
checklist, loaded_from_file, checklist_msg = load_checklist(CHECKLIST_PATH)
st.caption(checklist_msg)

tab1, tab2 = st.tabs(["1) Create report", "2) Preview & export"])

# Session state for checklist values
if "results" not in st.session_state:
    st.session_state.results = {}

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
    findings = st.text_area("Findings / Issues", height=120)
    recommendations = st.text_area("Recommendations / Actions", height=120)

    header = {
        "date": str(report_date),
        "project": project.strip(),
        "serial_number": serial_number.strip(),
        "model": model.strip(),
        "technician": technician.strip(),
    }

    st.session_state.current_report = {
        "header": header,
        "checklist": checklist,
        "results": st.session_state.results,
        "findings": findings,
        "recommendations": recommendations,
    }

with tab2:
    report = st.session_state.get("current_report")
    if not report:
        st.info("Fill in the report on the first tab, then come back here.")
        st.stop()

    missing = [k for k, v in report["header"].items() if k != "date" and not v]
    if missing:
        st.warning(f"Missing fields: {', '.join(missing)} (you can still export).")

    md = build_report_md(
        report["header"],
        report["checklist"],
        report["results"],
        report["findings"],
        report["recommendations"],
    )

    st.subheader("Preview")
    st.markdown(md)

    st.divider()
    st.subheader("Export")
    st.caption("Download Markdown, or use browser Print → Save as PDF from the preview.")

    st.download_button(
        label="Download report (.md)",
        data=md.encode("utf-8"),
        file_name=f"trane_chiller_report_{report['header']['date']}.md",
        mime="text/markdown",
    )

