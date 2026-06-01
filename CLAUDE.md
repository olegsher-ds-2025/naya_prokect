# naya_project — Environmental Health Intelligence Platform

## Purpose

Analyzes air quality data (PM2.5/PM10) alongside WHO GHO mortality, IHME GBD burden-of-disease, World Bank economic indicators, and Open-Meteo weather context. Produces Kaggle datasets and notebooks targeting medals. OpenAQ data was pre-collected and lives in CSVs — no live API calls.

## Environment

- Python 3.10, virtualenv at `.venv/`
- `source .venv/bin/activate` before running
- Kaggle pre-installs: numpy, pandas, plotly, scipy, scikit-learn, seaborn, matplotlib, requests — intentionally absent from `requirements.txt`

## Key Commands

```bash
ruff check . && ruff format .
pytest
```

## Architecture

```
data/                 # All git-ignored (*.csv in .gitignore)
  raw/openaq_locations.csv     # Station metadata (static, pre-collected)
  processed/openaq_daily.csv   # Daily PM2.5/PM10 per station (static)
  processed/openaq_monthly.csv # Monthly country-level aggregates (static)
  output/                      # Kaggle export path
```

Notebooks are authored and run on Kaggle, not stored locally.

## Data Schemas

**`data/raw/openaq_locations.csv`**
```
location_id, location_name, country_code, country_name, locality,
lat, lon, is_monitor, parameter_id, parameter, sensor_id, date_first, date_last
```

**`data/processed/openaq_daily.csv`**
```
date, location_id, location_name, country_code, country_name, locality,
lat, lon, parameter, value_ugm3, reading_count
```

**`data/processed/openaq_monthly.csv`**
```
year_month, country_code, country_name, parameter,
value_mean_ugm3, station_count, reading_count, exceeds_who_guideline
```

- `parameter` values: `"pm25"` or `"pm10"` (lowercase)
- `date` / `date_first` / `date_last`: `"YYYY-MM-DD"` strings, not datetime objects
- `value_ugm3`: always ≥ 0

## Key Constants

```python
WHO_AQG_PM25 = 15.0   # µg/m³ — WHO 2021 annual guideline
```

## Country Key Convention

OpenAQ data uses **ISO-2** country codes (`country_code`). Phase 2+ health datasets (WHO, IHME, World Bank) use **ISO-3**. Always add an ISO-2 → ISO-3 mapping step before joining. Never use free-text country names as join keys.

## Pitfalls

1. **CSVs are git-ignored** — `*.csv` is in `.gitignore`. Never assume data files exist in a fresh clone.
2. **`locality` is often empty** — Common for India and China rows. Match on `location_name` when `locality` is blank.
3. **ISO-2 vs ISO-3** — OpenAQ uses ISO-2; all health/economic data uses ISO-3. Map before every merge.
4. **`parameter` is lowercase** — `"pm25"` not `"PM2.5"`. Filter with exact lowercase string.

## Phase Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| 1 | Done | OpenAQ air quality data (static CSVs) |
| 2 | Next | WHO GHO + IHME GBD health data |
| 3 | Planned | World Bank economic indicators + feature engineering |
| 4 | Planned | Open-Meteo weather enrichment + time-series |
| 5 | Planned | Kaggle dataset polish + medal push |

## Custom Slash Commands

- `/check-data` — Data quality audit on all output CSVs
- `/research-papers` — Search PubMed for air quality / health literature
- `/add-city` — (reference) Shows how to add a city if pipeline is re-enabled
