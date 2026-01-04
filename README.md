
# Chiller Datasheet Compare (Streamlit)

Upload **2 chiller datasheet PDFs** → auto-extract key specs → compare side-by-side → optional OPEX + simple payback → export PDF report.

This MVP is tuned for **structured selection reports** (e.g., Trane Select Assist "Product Report" PDFs), and is easy to extend with more vendor formats.

## Features
- Upload exactly **2 PDFs**
- Automatic extraction of common fields (model, capacity, power, EER, flow, acoustics, electrical, dimensions, weights, IPLV/NPLV)
- Editable extracted values (safety)
- Comparison table (includes numeric B-A difference where possible)
- OPEX summary using Equivalent Full-Load Hours (EFLH)
- Optional simple payback if CAPEX inputs are provided
- Export a **client-ready PDF report**

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (Streamlit Community Cloud)
1. Push this repo to GitHub
2. In Streamlit Cloud, create a new app from the repo
3. Set main file: `app.py`

## How extraction works
Rule-based patterns in `src/extract.py` parse the PDF text (via `pdfplumber`) using robust label patterns.
To support more datasheets, add patterns to `LABEL_PATTERNS` and (if needed) implement table parsing.

## Notes
- If a PDF is scanned (image-only), you’ll need OCR support (not included in this MVP).
- Always verify critical values before sending to clients.
