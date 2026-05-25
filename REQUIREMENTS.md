# Environmental Health Intelligence Platform
### Business System Requirements

---

## 1. Executive Summary

**Project name:** Environmental Health Intelligence Platform  
**Platform:** Kaggle (datasets + notebooks)  
**Business goal:** Provide clean, visual, decision-ready intelligence on how air pollution impacts human health globally — enabling policymakers, public health analysts, and researchers to identify high-risk locations and quantify environmental burden.  
**Success criteria:** Kaggle medals on published datasets and notebooks; daily-updated data pipeline; portfolio-quality visualizations.

---

## 2. Stakeholders & Users

| Role | Need |
|---|---|
| Public health decision maker | Identify high-risk countries/cities to prioritize intervention |
| Policy analyst | Correlate pollution levels with mortality and economic cost |
| Environmental researcher | Access clean, merged, normalized multi-source dataset |
| Kaggle community | Explore and fork well-documented data + notebooks |

---

## 3. Data Sources

| Source | Data | Update cadence | License |
|---|---|---|---|
| [OpenAQ](https://openaq.org) | Real-time air quality (PM2.5, PM10, NO2, O3, SO2, CO) by station/city | Daily | CC BY 4.0 |
| [WHO GHO](https://www.who.int/data/gho) | Mortality, respiratory disease, PM2.5 exposure by country | Annual | CC BY-NC-SA 3.0 |
| [IHME GBD](https://www.healthdata.org/research-analysis/gbd) | Deaths & DALYs attributable to PM2.5 by country/year | Annual | IHME free for non-commercial |
| [World Bank Open Data](https://data.worldbank.org) | GDP, population, life expectancy, healthcare spending | Annual | CC BY 4.0 |
| [Our World in Data](https://ourworldindata.org/air-pollution) | Historical pollution + deaths trends | Annual | CC BY 4.0 |
| [Open-Meteo](https://open-meteo.com) | Temperature, humidity, wind (weather context) | Daily | CC BY 4.0 |

---

## 4. Functional Requirements

### FR-1: Data Ingestion & Normalization
- Ingest all sources via API or CSV download
- Normalize country names to **ISO-3 codes**
- Normalize city names to lowercase ASCII
- Normalize dates to `YYYY-MM-DD`
- Store raw data separately from processed data

### FR-2: Kaggle Datasets (published, medal-eligible)

| Dataset | Description | Update |
|---|---|---|
| `global-air-quality-openaq` | Cleaned OpenAQ readings by country/city/date | Daily |
| `global-pollution-health-impact` | Merged: OpenAQ + WHO + IHME + World Bank | Weekly |
| `environmental-risk-scores` | Engineered features + risk rankings | Weekly |

Each dataset must include:
- A `README` / dataset description card with methodology
- Data dictionary (column definitions, units, sources)
- Version history

### FR-3: Engineered Features

| Feature | Formula / Definition |
|---|---|
| `pollution_risk_score` | Weighted sum of normalized PM2.5, PM10, NO2 |
| `exposure_score` | `pollution_risk_score × population_density` |
| `health_impact_score` | `PM2.5 × deaths_per_100k` (normalized) |
| `environmental_stress_index` | Composite: pollution + health impact + economic burden |
| `monitoring_coverage` | Stations per 1M population |

### FR-4: Main Analytics Notebook (`main_analysis.ipynb`)

The primary notebook for decision makers. Must include:

**Section 1 — Global Overview**
- World choropleth map: PM2.5 average by country (latest year)
- World choropleth map: deaths attributable to air pollution per 100k

**Section 2 — Top 20 Rankings**
- Top 20 most polluted countries (PM2.5)
- Top 20 highest respiratory mortality countries
- Top 20 highest Environmental Risk Score countries
- Top 20 cities by pollution level (OpenAQ)

**Section 3 — Correlation Analysis**
- Scatter: PM2.5 vs deaths per 100k — with regression line + R²
- Scatter: PM2.5 vs life expectancy
- Scatter: GDP per capita vs pollution levels (inequality lens)
- Heatmap: correlation matrix of all key variables

**Section 4 — Time-Series Trends**
- Pollution trend by region (2015–present)
- Mortality trend from air pollution (2015–present)
- Year-over-year change for top 10 countries

**Section 5 — Inequality Analysis**
- Rich vs. poor countries: pollution burden vs. healthcare spending
- Monitoring coverage gap: measured vs. unmeasured populations

**Section 6 — Risk Score Dashboard**
- Bubble chart: exposure_score (size) × health_impact_score (color) × country
- Ranked table: Environmental Stress Index, top 50 countries

### FR-5: Daily Update Notebook (`data_update.ipynb`)
- Runs daily on Kaggle's scheduled notebook runner
- Pulls fresh OpenAQ and Open-Meteo data
- Appends to datasets, validates schema
- Logs update timestamp and row counts

---

## 5. Non-Functional Requirements

| Requirement | Specification |
|---|---|
| Platform | Kaggle Notebooks (Python 3.10, no paid GPU needed) |
| Reproducibility | All notebooks run top-to-bottom with no manual steps |
| Performance | Full notebook runtime < 10 minutes |
| Portability | No local file paths; use `/kaggle/input/` and `/kaggle/working/` |
| Visualization | Plotly (interactive) as primary; Matplotlib/Seaborn for static exports |
| Data freshness | Air quality data: ≤ 24h lag; health/economic data: latest annual release |
| Documentation | Every notebook has a markdown intro explaining the business question |

---

## 6. Delivery Phases

### Phase 1 — Foundation (Week 1–2)
- [ ] Set up data ingestion: OpenAQ API → cleaned CSV
- [ ] Publish `global-air-quality-openaq` dataset on Kaggle
- [ ] Basic notebook: Top 20 polluted cities/countries

### Phase 2 — Health Layer (Week 3–4)
- [ ] Ingest WHO mortality + IHME GBD data
- [ ] Merge with Phase 1 dataset on ISO-3 + year
- [ ] Publish `global-pollution-health-impact` dataset
- [ ] Add correlation charts (PM2.5 vs mortality) to main notebook

### Phase 3 — Economic Layer (Week 5–6)
- [ ] Ingest World Bank indicators (GDP, population, life expectancy)
- [ ] Engineer `environmental_stress_index` and `exposure_score`
- [ ] Publish `environmental-risk-scores` dataset
- [ ] Add inequality and risk score visuals to main notebook

### Phase 4 — Time-Series & Weather (Week 7–8)
- [ ] Add Open-Meteo weather enrichment
- [ ] Build time-series trend section
- [ ] Set up daily scheduled update notebook

### Phase 5 — Polish & Medal Push (Week 9–10)
- [ ] Full narrative storytelling in notebooks (markdown, callouts, insights)
- [ ] Tableau-ready export (clean CSV with all features)
- [ ] Cross-promote datasets and notebooks
- [ ] Promote notebooks for upvotes / medal eligibility

---

## 7. Key Metrics for Success

| KPI | Target |
|---|---|
| Kaggle dataset usability medals | ≥ 2 Gold |
| Kaggle notebook medals | ≥ 1 Gold, ≥ 1 Silver |
| Dataset forks/downloads | > 500 within 3 months |
| Notebook views | > 2,000 within 3 months |
| Data freshness | Air quality updated daily |
| Notebook reproducibility | 100% run without errors |

---

## 8. Technical Stack (Kaggle-native)

| Layer | Tool |
|---|---|
| Data ingestion | `requests`, `pandas`, `kaggle` API |
| Data processing | `pandas`, `numpy` |
| Visualization | `plotly`, `seaborn`, `matplotlib` |
| Geospatial | `plotly` choropleth + `geopandas` (optional) |
| Correlation/stats | `scipy`, `scikit-learn` |
| Scheduling | Kaggle scheduled notebooks |
| Storage | Kaggle Datasets (versioned) |
