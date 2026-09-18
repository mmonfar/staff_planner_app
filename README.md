# Staff Planner App

An acuity-driven nurse establishment planner built with Python and Streamlit.

It answers one question: **does this staffing ratio actually meet the nursing
demand this ward generates?** Demand comes from the Safer Nursing Care Tool
acuity ladder — a Level 3 patient needs 6x the nursing time of a Level 0 — and
is modelled as a distribution, not a point estimate, because census and case mix
vary daily. Ratios are then tested against it rather than assumed adequate.

Every clinical and regulatory constant carries a citation. See
[research/SOURCES.md](research/SOURCES.md).

---

## 🛠️ Features
- **Acuity-driven demand** from the SNCT ladder (L0 4.35 → L3 26.2 HPPD).
- **Stochastic modelling** — negative-binomial census and Dirichlet acuity mix;
  establishment sized at the 90th percentile, per SNCT modelling findings.
- **Ratio adequacy** — the gap between what a ratio buys and what acuity demands.
- **Case-mix sensitivity** — where each model stops coping as CMI rises.
- **Cited evidence store** — SQLite, queryable at runtime, with a generated
  markdown view and a full retrieval log including failed lookups.

---

## 📦 Folder Structure

staff-planner-app/
│
├── app/
│   ├── __init__.py         # Marks the app as a Python package.
│   ├── planner.py          # The StaffPlanner class (all business logic).
│   ├── main.py             # The Streamlit app.
│   ├── styles.css          # Custom styles, loaded by main.py.
│
├── tests/
│   └── test_planner.py     # Characterization tests for planner.py.
│
├── .streamlit/config.toml  # Theme settings.
├── pyproject.toml          # Package metadata, pinned deps, pytest config.
├── requirements.txt        # Pinned runtime dependencies.
├── .gitignore
├── README.md


---

## 🚀 How to Run the App

1. Clone this Repository:
   ```bash
   git clone https://github.com/your-username/staff-planner-app.git
   cd staff-planner-app

2. Install Dependencies: install the project itself (this pulls in the pinned
   dependencies and puts `app` on the import path):

   pip install -e ".[dev]"

   For a runtime-only install, `pip install -r requirements.txt` also works.

3. Start the Streamlit App: Run the app using the streamlit CLI tool:

   streamlit run app/main.py

4. Open Your Browser:

   Visit http://localhost:8501 to interact with the app

---

## 🖌️ Customize Styles

The app includes a styles.css file for custom styles (e.g., sidebar colors, font sizes). Update this file under app/styles.css to change the UI.

---

## 🛡️ Testing

Tests live in `tests/test_planner.py` and run with pytest:

    python -m pytest

Tests marked `xfail` are **not** flaky — they document confirmed defects in the
demand formula (see the note below) and describe the behaviour the planner
should have. They will flip to passing when that formula is corrected.

## ⚠️ Status

**Mock data.** The machinery is tested and internally consistent, but no output
is clinically valid until real census, CMI and acuity observations replace the
defaults. Do not present results as staffing advice.

Assumptions still needing local calibration are listed in the app's *Evidence
and assumptions* panel and in [PROJECT_STATUS.md](PROJECT_STATUS.md): the
CMI→acuity tilt, the base acuity mix, census dispersion and CMI variability.

## 🔌 Local MCP config

`.mcp.json` is gitignored — it holds machine-specific absolute paths. Copy
`.mcp.json.example` and fill in your own.

---

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.
