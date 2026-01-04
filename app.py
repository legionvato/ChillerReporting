
import streamlit as st
import pandas as pd

import os, sys
# Ensure local imports work on Streamlit Cloud
sys.path.append(os.path.dirname(__file__))


from src.extract import extract_specs_from_pdf
from src.compare import build_comparison_table, opex_summary
from src.report import build_pdf_report

st.set_page_config(page_title="Chiller Datasheet Compare", layout="wide")

st.title("Chiller Datasheet Compare")
st.caption("Upload 2 chiller datasheet PDFs (e.g., Trane Select Assist reports) → auto-extract specs → compare → optional OPEX + report export.")

with st.sidebar:
    st.header("Project Inputs (for OPEX/ROI)")
    col1, col2 = st.columns(2)
    with col1:
        electricity_price = st.number_input("Electricity price (per kWh)", min_value=0.0, value=0.12, step=0.01, format="%.3f")
        analysis_years = st.number_input("Analysis period (years)", min_value=1, value=10, step=1)
    with col2:
        eflh = st.number_input("Equivalent full-load hours (h/year)", min_value=0, value=2500, step=100)
        currency = st.text_input("Currency", value="€", help="Used only for display in OPEX/ROI outputs.")

    st.divider()
    st.header("Optional commercial inputs")
    st.caption("These do not exist in most datasheets; enter if you want payback/ROI.")
    capex_a = st.number_input("CAPEX Option A", min_value=0.0, value=0.0, step=1000.0)
    capex_b = st.number_input("CAPEX Option B", min_value=0.0, value=0.0, step=1000.0)

st.subheader("1) Upload datasheets (2 PDFs)")
files = st.file_uploader("Upload exactly 2 PDF datasheets", type=["pdf"], accept_multiple_files=True)

if not files:
    st.info("Upload two PDFs to begin.")
    st.stop()

if len(files) != 2:
    st.warning(f"Please upload exactly 2 PDFs (you uploaded {len(files)}).")
    st.stop()

# Extract
with st.spinner("Extracting specs from PDFs..."):
    specs = []
    for f in files:
        data = extract_specs_from_pdf(f)
        data["_file_name"] = f.name
        specs.append(data)

a, b = specs[0], specs[1]

st.subheader("2) Extracted specs (editable)")
st.caption("If a value is missing or looks wrong, edit it here before comparing.")

def editable_specs(spec: dict, key_order: list[str]) -> dict:
    out = dict(spec)
    for k in key_order:
        if k in out:
            v = out[k]
            if isinstance(v, (int, float)) and v is not None:
                out[k] = st.text_input(k, value=str(v))
            else:
                out[k] = st.text_input(k, value="" if v is None else str(v))
    # Also show any other keys
    other = [k for k in out.keys() if k not in key_order and not k.startswith("_")]
    if other:
        with st.expander("Other extracted fields"):
            for k in sorted(other):
                v = out[k]
                out[k] = st.text_input(k, value="" if v is None else str(v), key=f"other_{k}_{id(out)}")
    return out

KEY_ORDER = [
    "model", "range", "chiller_model", "unit_application",
    "compressor_type", "refrigerant", "refrigerant_gwp",
    "electrical_supply",
    "design_ambient_c", "lwt_c", "ewt_c", "fluid", "antifreeze_pct", "elevation_m",
    "net_capacity_kw", "gross_capacity_kw",
    "net_eer_kw_per_kw", "gross_eer_kw_per_kw",
    "power_kw",
    "design_flow_ls", "evap_pressure_drop_kpa",
    "sound_power_dba", "sound_pressure_dba",
    "length_mm", "width_mm", "height_mm", "operating_weight_kg", "shipping_weight_kg",
    "iplv_si", "nplv_si",
    "startup_current_a", "running_current_a", "max_amps_a", "max_power_kw", "cos_phi"
]

colA, colB = st.columns(2)
with colA:
    st.markdown(f"**Option A:** {a.get('_file_name','')}")
    a_edit = editable_specs(a, KEY_ORDER)
with colB:
    st.markdown(f"**Option B:** {b.get('_file_name','')}")
    b_edit = editable_specs(b, KEY_ORDER)

st.subheader("3) Comparison")
comp = build_comparison_table(a_edit, b_edit, label_a="Option A", label_b="Option B")
st.dataframe(comp, use_container_width=True)

st.subheader("4) OPEX & simple payback (optional)")
op = opex_summary(a_edit, b_edit, electricity_price=electricity_price, eflh=eflh, years=int(analysis_years), currency=currency, capex_a=capex_a, capex_b=capex_b)
st.dataframe(op, use_container_width=True)

st.subheader("5) Export report")
st.caption("Generates a simple PDF report with the extracted specs, comparison, and OPEX summary.")
if st.button("Generate PDF report"):
    pdf_bytes = build_pdf_report(a_edit, b_edit, comp, op, title="Chiller Datasheet Comparison Report")
    st.download_button("Download report PDF", data=pdf_bytes, file_name="chiller_comparison_report.pdf", mime="application/pdf")
