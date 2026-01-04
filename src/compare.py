
from __future__ import annotations
from typing import Any, Dict, Optional
import pandas as pd

DISPLAY = [
    ("Model", "model"),
    ("Range / Series", "range"),
    ("Chiller model", "chiller_model"),
    ("Application", "unit_application"),
    ("Compressor type", "compressor_type"),
    ("Refrigerant", "refrigerant"),
    ("Refrigerant GWP", "refrigerant_gwp"),
    ("Electrical supply", "electrical_supply"),
    ("Design ambient (°C)", "design_ambient_c"),
    ("LWT (°C)", "lwt_c"),
    ("EWT (°C)", "ewt_c"),
    ("Fluid", "fluid"),
    ("Antifreeze (%)", "antifreeze_pct"),
    ("Elevation (m)", "elevation_m"),
    ("Net capacity (kW)", "net_capacity_kw"),
    ("Gross capacity (kW)", "gross_capacity_kw"),
    ("Power input (kW)", "power_kw"),
    ("Net EER (kW/kW)", "net_eer_kw_per_kw"),
    ("Gross EER (kW/kW)", "gross_eer_kw_per_kw"),
    ("Design flow (L/s)", "design_flow_ls"),
    ("Evap ΔP (kPa)", "evap_pressure_drop_kpa"),
    ("Sound power (dBA)", "sound_power_dba"),
    ("Sound pressure (dBA)", "sound_pressure_dba"),
    ("IPLV.SI", "iplv_si"),
    ("NPLV.SI", "nplv_si"),
    ("Start-up current (A)", "startup_current_a"),
    ("Running current (A)", "running_current_a"),
    ("Max amps (A)", "max_amps_a"),
    ("Max power (kW)", "max_power_kw"),
    ("cos φ", "cos_phi"),
    ("Length (mm)", "length_mm"),
    ("Width (mm)", "width_mm"),
    ("Height (mm)", "height_mm"),
    ("Shipping weight (kg)", "shipping_weight_kg"),
    ("Operating weight (kg)", "operating_weight_kg"),
]

def _as_num(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    try:
        return float(s)
    except Exception:
        return None

def build_comparison_table(a: Dict[str, Any], b: Dict[str, Any], label_a="A", label_b="B") -> pd.DataFrame:
    rows = []
    for label, key in DISPLAY:
        va = a.get(key)
        vb = b.get(key)
        rows.append({"Metric": label, label_a: va, label_b: vb})
    df = pd.DataFrame(rows)

    # Optional "difference" for numeric fields
    diffs = []
    for _, key in DISPLAY:
        na = _as_num(a.get(key))
        nb = _as_num(b.get(key))
        if na is None or nb is None:
            diffs.append("")
        else:
            diffs.append(nb - na)
    df["B - A"] = diffs
    return df

def opex_summary(a: Dict[str, Any], b: Dict[str, Any], electricity_price: float, eflh: float, years: int, currency: str, capex_a: float=0.0, capex_b: float=0.0) -> pd.DataFrame:
    """
    Very simple OPEX model:
    - Use design power (kW) from datasheet (power_kw). If missing, fall back to capacity/ EER.
    - Annual kWh = power_kw * EFLH
    """
    def power_from(d: Dict[str, Any]) -> Optional[float]:
        p = _as_num(d.get("power_kw"))
        if p is not None:
            return p
        cap = _as_num(d.get("net_capacity_kw")) or _as_num(d.get("gross_capacity_kw"))
        eer = _as_num(d.get("net_eer_kw_per_kw")) or _as_num(d.get("gross_eer_kw_per_kw"))
        if cap is None or eer in (None, 0):
            return None
        return cap / eer

    pa = power_from(a)
    pb = power_from(b)

    def annual_kwh(p: Optional[float]) -> Optional[float]:
        return None if p is None else p * float(eflh)

    kwh_a = annual_kwh(pa)
    kwh_b = annual_kwh(pb)

    cost_a = None if kwh_a is None else kwh_a * float(electricity_price)
    cost_b = None if kwh_b is None else kwh_b * float(electricity_price)

    total_a = None if cost_a is None else cost_a * years
    total_b = None if cost_b is None else cost_b * years

    savings_per_year = None if (cost_a is None or cost_b is None) else (cost_a - cost_b)  # positive means B cheaper to run
    capex_delta = capex_b - capex_a

    payback_years = None
    if savings_per_year and savings_per_year > 0 and capex_delta > 0:
        payback_years = capex_delta / savings_per_year

    df = pd.DataFrame([
        {"Item": "Power used (kW)", "Option A": pa, "Option B": pb},
        {"Item": f"Annual energy (kWh) @ {eflh:.0f} h/y", "Option A": kwh_a, "Option B": kwh_b},
        {"Item": f"Annual energy cost ({currency})", "Option A": cost_a, "Option B": cost_b},
        {"Item": f"{years}-year energy cost ({currency})", "Option A": total_a, "Option B": total_b},
        {"Item": f"Annual savings (A - B) ({currency})", "Option A": "", "Option B": savings_per_year},
        {"Item": f"CAPEX delta (B - A) ({currency})", "Option A": "", "Option B": capex_delta},
        {"Item": "Simple payback (years)", "Option A": "", "Option B": payback_years},
    ])
    return df
