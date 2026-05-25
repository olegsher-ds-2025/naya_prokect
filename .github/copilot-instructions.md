# Copilot Instructions

## Project Overview

**Environmental Health Intelligence Platform** — a Kaggle-native data project that correlates global air quality (OpenAQ), health mortality (WHO/IHME), and socioeconomic indicators (World Bank) to produce visual, decision-ready intelligence. Target outcomes: Kaggle medals on 3 published datasets + a daily-updated main analytics notebook.

Full business requirements: [`REQUIREMENTS.md`](../REQUIREMENTS.md)

## Environment Setup

Python **3.10** (matches Kaggle). Use `.venv` locally.

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Kaggle-standard packages (numpy, pandas, scikit-learn, torch, matplotlib, plotly, seaborn, scipy) are **not** in `requirements.txt` — they are pre-installed on Kaggle and assumed available everywhere.

## Kaggle Path Conventions

All notebooks must use Kaggle paths, not local paths:

```python
INPUT  = "/kaggle/input/"
OUTPUT = "/kaggle/working/"
```

Locally, map these to `./data/input/` and `./data/output/`.

## Architecture

```
src/
  openaq_client.py   # OpenAQ v3 API client (throttled, paginated, retry)
  pipeline.py        # Phase 1 ingestion → locations + daily + monthly CSVs
data/
  raw/               # Original source files, never modified (git-ignored)
  processed/         # Merged, normalized datasets ready for analysis
  output/            # Kaggle dataset exports
```

Notebooks are authored and run **directly on Kaggle** — not stored locally.

**Key data flow:** OpenAQ API + WHO/IHME/World Bank CSVs → normalize to ISO-3 + YYYY-MM-DD → merge on (country, year) → engineer risk scores → Plotly visualizations → Kaggle dataset versions.

## Key Conventions

- **Country key:** always ISO-3 (e.g. `IND`, `USA`). Never use free-text country names as join keys.
- **Date key:** `YYYY-MM-DD` strings. Air quality aggregated to monthly/annual for health data joins.
- **Engineered features** (`pollution_risk_score`, `exposure_score`, `health_impact_score`, `environmental_stress_index`) are defined in `REQUIREMENTS.md §FR-3` — do not redefine them ad hoc.
- **Visualizations:** Plotly for interactive (notebooks), Matplotlib/Seaborn for static exports. Every chart must have a 1–2 sentence markdown insight below it explaining the business finding.
- **Notebooks** must run top-to-bottom without errors and complete in < 10 minutes on Kaggle free tier.

## Commands

| Task | Command |
|------|---------|
| Run ingestion | `python -m src.pipeline` |
| Run all tests | `pytest` |
| Run a single test | `pytest tests/test_foo.py::test_bar_name` |
| Lint | `ruff check .` |
| Format | `ruff format .` |
