
from __future__ import annotations
import io, re
from typing import Any, Dict, Optional

import pdfplumber

# This extractor is intentionally "rules-first" for reliability on structured selection reports.
# It works very well on Trane Select Assist "Product Report" PDFs like the samples you shared.
# For other vendors, you can add patterns to LABEL_PATTERNS and TABLE_BLOCK_PATTERNS.

def _to_float(x: str) -> Optional[float]:
    if x is None:
        return None
    x = x.strip()
    if not x:
        return None
    x = x.replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", x)
    return float(m.group(0)) if m else None

def _grab(text: str, pattern: str, flags=re.IGNORECASE) -> Optional[str]:
    """Return the first non-empty captured group from a regex match."""
    m = re.search(pattern, text, flags)
    if not m:
        return None

    # Some patterns use alternation, so group(1) might be None.
    for i in range(1, (m.lastindex or 0) + 1):
        g = m.group(i)
        if g is not None and str(g).strip() != "":
            return str(g).strip()

    return None
LABEL_PATTERNS = {
    # Unit overview
    "range": r"Range\s+(.+)",
    "chiller_model": r"Chiller model\s+(.+)",
    "model": r"Model\s+([A-Z0-9\-\s]+?)(?:\n|$)",
    "unit_application": r"Unit Application\s+(.+)",
    "compressor_type": r"Compressor type\s+(.+)",
    "refrigerant": r"Refrigerant Type.*?\s([Rr]\d{3,4}[A-Za-z0-9]*)",
    "refrigerant_gwp": r"Refrigerant GWP\s+(\d+(\.\d+)?)",
    "electrical_supply": r"Electrical supply\s+(.+)",

    # Project conditions
    "design_ambient_c": r"Outdoor air dry bulb temperature\s+(\d+(\.\d+)?)\s*C",
    "ewt_c": r"Fluid entering temperature\s+(\d+(\.\d+)?)\s*C",
    "lwt_c": r"Fluid leaving temperature\s+(\d+(\.\d+)?)\s*C",
    "fluid": r"Fluid Type and concentration\s+([A-Za-z ]+)",
    "antifreeze_pct": r"Fluid Type and concentration.*?/\s+(\d+(\.\d+)?)\s*%",
    "elevation_m": r"Elevation\s+(\d+(\.\d+)?)\s*m",

    # Unit performance
    "gross_capacity_kw": r"Gross capacity\s+(\d+(\.\d+)?)\s*kW",
    "net_capacity_kw": r"Net capacity\s+(\d+(\.\d+)?)\s*kW",
    "power_kw": r"(?:Gross unit power|Total absorbed power)\s+(\d+(\.\d+)?)\s*kW",
    "gross_eer_kw_per_kw": r"Gross EER\s+(\d+(\.\d+)?)\s*EER",
    "net_eer_kw_per_kw": r"Net EER\s+(\d+(\.\d+)?)\s*EER",
    "design_flow_ls": r"Design flow rate\s+(\d+(\.\d+)?)\s*L/s",
    "evap_pressure_drop_kpa": r"Evaporator Pressure drop \(Design\)\s+(\d+(\.\d+)?)\s*kPa",

    # Acoustic
    "sound_power_dba": r"Outdoor sound power level.*?\s(\d+(\.\d+)?)\s*dBA",
    "sound_pressure_dba": r"Outdoor sound pressure level.*?\s(\d+(\.\d+)?)\s*dBA",

    # Partload headline KPI
    "iplv_si": r"IPLV\.SI\s+(\d+(\.\d+)?)",
    "nplv_si": r"NPLV\.SI\s+(\d+(\.\d+)?)",

    # Electrical block
    "running_current_a": r"Current\s+(\d+(\.\d+)?)\s*A",
    "startup_current_a": r"Start-up current\s+(\d+(\.\d+)?)\s*A",
    "max_amps_a": r"Max amps\s+(\d+(\.\d+)?)\s*A|Maximum running current\s+(\d+(\.\d+)?)\s*A",
    "max_power_kw": r"Maximum power at maximum current\s+(\d+(\.\d+)?)\s*kW",
    "cos_phi": r"Displacement power factor \(cos-phi\)\s+(\d+(\.\d+)?)",

    # Dimensions/weight
    "length_mm": r"Length\s+(\d+(\.\d+)?)\s*mm",
    "width_mm": r"Width\s+(\d+(\.\d+)?)\s*mm",
    "height_mm": r"Height\s+(\d+(\.\d+)?)\s*mm",
    "shipping_weight_kg": r"(?:Unit shipping weight|Shipping weight including packaging)\s+(\d+(\.\d+)?)\s*kg",
    "operating_weight_kg": r"Operating weight\s+(\d+(\.\d+)?)\s*kg",
}

def extract_specs_from_pdf(file) -> Dict[str, Any]:
    """
    file: a Streamlit UploadedFile or file-like object.
    Returns a dict of extracted fields + _raw_text for debugging.
    """
    # Read bytes
    pdf_bytes = file.read() if hasattr(file, "read") else file
    if hasattr(file, "seek"):
        try: file.seek(0)
        except Exception: pass

    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t)

    text = "\n".join(text_parts)
    out: Dict[str, Any] = {"_raw_text": text}

    # Apply label patterns
    for key, pat in LABEL_PATTERNS.items():
        val = _grab(text, pat)
        if val is None:
            continue
        # numeric conversions
        if key in {
            "design_ambient_c","ewt_c","lwt_c","antifreeze_pct","elevation_m",
            "gross_capacity_kw","net_capacity_kw","power_kw","gross_eer_kw_per_kw","net_eer_kw_per_kw",
            "design_flow_ls","evap_pressure_drop_kpa","sound_power_dba","sound_pressure_dba",
            "iplv_si","nplv_si","running_current_a","startup_current_a","max_amps_a","max_power_kw",
            "cos_phi","length_mm","width_mm","height_mm","shipping_weight_kg","operating_weight_kg",
            "refrigerant_gwp"
        }:
            out[key] = _to_float(val)
        else:
            out[key] = val

    # Fix "model" – Trane reports sometimes repeat "Model Number" later
    # Keep the short "Model" line, not the long model number string.
    if out.get("model") and len(out["model"]) > 60:
        out["model"] = out["model"][:60].strip()

    return out
