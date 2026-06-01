"""
Download Phase 2 health and economic data.

Sources:
  1. WHO GHO  — air pollution mortality indicators (OData API, no auth)
  2. World Bank — economic + population indicators (REST API, no auth)
  3. IHME GBD  — burden-of-disease via Our World in Data public CSVs
  4. Open-Meteo — historical daily weather for PRIORITY_CITIES (ERA5 archive, no auth)

Outputs (all written to data/raw/):
  who_gho_air_pollution.csv
  world_bank_indicators.csv
  ihme_gbd_air_pollution.csv
  open_meteo_weather.csv
"""

from __future__ import annotations

import time
import sys
from pathlib import Path

import requests
import pandas as pd

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "naya-project/1.0 (health research; non-commercial)"


def get(url: str, params: dict | None = None, timeout: int = 60) -> requests.Response:
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------------------
# 1. WHO GHO
# ---------------------------------------------------------------------------
WHO_INDICATORS = {
    "AIR_10": "deaths_ambient_air_pollution_n",
    "AIR_11": "asmr_ambient_air_pollution_per100k",
    "AIR_12": "crude_death_rate_ambient_air_pollution_per100k",
    "SDGPM25": "pm25_annual_mean_ug_m3",
}


def download_who_gho() -> None:
    print("=== 1. WHO GHO ===")
    frames = []
    for code, label in WHO_INDICATORS.items():
        url = f"https://ghoapi.azureedge.net/api/{code}"
        try:
            data = get(url).json().get("value", [])
            df = pd.DataFrame(data)
            if df.empty:
                print(f"  {code}: empty response")
                continue
            df["indicator_code"] = code
            df["indicator_label"] = label
            frames.append(df)
            print(f"  {code}: {len(df):,} rows")
        except Exception as e:
            print(f"  {code}: FAILED — {e}")
        time.sleep(0.5)

    if not frames:
        print("  No WHO GHO data downloaded.")
        return

    raw = pd.concat(frames, ignore_index=True)

    keep = {
        "indicator_code": "indicator_code",
        "indicator_label": "indicator_label",
        "SpatialDim": "country_code_3",
        "TimeDim": "year",
        "Dim1": "sex",
        "NumericValue": "value",
        "Low": "value_low",
        "High": "value_high",
    }
    out = raw.rename(columns={k: v for k, v in keep.items() if k in raw.columns})
    out = out[[v for v in keep.values() if v in out.columns]]
    out = out.dropna(subset=["value"])

    path = RAW_DIR / "who_gho_air_pollution.csv"
    out.to_csv(path, index=False)
    print(f"  → {path}  ({len(out):,} rows)\n")


# ---------------------------------------------------------------------------
# 2. World Bank
# ---------------------------------------------------------------------------
WB_INDICATORS = {
    "NY.GDP.PCAP.CD":    "gdp_per_capita_usd",
    "SP.POP.TOTL":       "population_total",
    "SP.DYN.LE00.IN":    "life_expectancy_years",
    "SH.XPD.CHEX.GD.ZS": "health_expenditure_pct_gdp",
    "SP.URB.TOTL.IN.ZS": "urban_population_pct",
    "EN.ATM.PM25.MC.M3": "pm25_mean_annual_ug_m3_wb",
}


def download_world_bank() -> None:
    print("=== 2. World Bank ===")
    frames = []
    for code, label in WB_INDICATORS.items():
        url = f"https://api.worldbank.org/v2/country/all/indicator/{code}"
        params = {"format": "json", "per_page": 500, "mrv": 12}
        try:
            payload = get(url, params=params).json()
            if len(payload) < 2 or not payload[1]:
                print(f"  {code}: no data returned")
                continue
            rows = [
                {
                    "country_code_3": r["countryiso3code"],
                    "country_name":   r["country"]["value"],
                    "year":           int(r["date"]),
                    "indicator_code": code,
                    "indicator_label": label,
                    "value":          r["value"],
                }
                for r in payload[1]
                if r.get("value") is not None and r.get("countryiso3code")
            ]
            df = pd.DataFrame(rows)
            frames.append(df)
            print(f"  {code}: {len(df):,} rows")
        except Exception as e:
            print(f"  {code}: FAILED — {e}")
        time.sleep(0.3)

    if not frames:
        print("  No World Bank data downloaded.")
        return

    out = pd.concat(frames, ignore_index=True)
    path = RAW_DIR / "world_bank_indicators.csv"
    out.to_csv(path, index=False)
    print(f"  → {path}  ({len(out):,} rows)\n")


# ---------------------------------------------------------------------------
# 3. IHME GBD via Our World in Data
# ---------------------------------------------------------------------------
_OWID_BASE = "https://raw.githubusercontent.com/owid/owid-datasets/master/datasets"
OWID_DATASETS = [
    (
        "Absolute deaths from ambient PM2.5 air pollution- State of Global Air",
        "Absolute deaths from ambient PM2.5 air pollution- State of Global Air.csv",
    ),
    (
        "Share of deaths attributed to air pollution (IHME, 2019)",
        "Share of deaths attributed to air pollution (IHME, 2019).csv",
    ),
    (
        "Deaths attributed to air pollution (Lelieveld et al. 2019)",
        "Deaths attributed to air pollution (Lelieveld et al. 2019).csv",
    ),
]


def download_ihme_owid() -> None:
    import urllib.parse
    from io import StringIO

    print("=== 3. IHME GBD via Our World in Data (GitHub) ===")
    frames = []
    for folder, filename in OWID_DATASETS:
        url = f"{_OWID_BASE}/{urllib.parse.quote(folder)}/{urllib.parse.quote(filename)}"
        try:
            r = get(url, timeout=60)
            df = pd.read_csv(StringIO(r.text))
            df["source_dataset"] = folder
            frames.append(df)
            print(f"  {folder[:55]}: {len(df):,} rows")
        except Exception as e:
            print(f"  {folder[:55]}: FAILED — {e}")
        time.sleep(0.5)

    if not frames:
        print("  No IHME/OWID data downloaded.")
        return

    normalized = []
    for df in frames:
        df.columns = [
            c.lower().replace(" ", "_").replace("-", "_")
             .replace("(", "").replace(")", "").replace(",", "")
            for c in df.columns
        ]
        normalized.append(df)

    out = pd.concat(normalized, ignore_index=True)
    path = RAW_DIR / "ihme_gbd_air_pollution.csv"
    out.to_csv(path, index=False)
    print(f"  → {path}  ({len(out):,} rows)\n")


# ---------------------------------------------------------------------------
# 4. Open-Meteo — historical daily weather per city
# ---------------------------------------------------------------------------
WEATHER_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "windspeed_10m_max",
]
WEATHER_START = "2020-01-01"
WEATHER_END   = "2024-12-31"


def _clean_cities(locs: pd.DataFrame) -> pd.DataFrame:
    """
    Return one representative (country_code, city_label, lat, lon) per city.
    Collapses Paris arrondissements → 'Paris' and deduplicates case variants.
    """
    df = locs.copy()
    # Collapse Paris arrondissements
    paris_mask = df["locality"].str.contains("PARIS", case=False, na=False)
    df.loc[paris_mask, "locality"] = "Paris"
    # Normalise case for deduplication (FRESNO → Fresno)
    df["locality_norm"] = df["locality"].str.strip().str.title()
    cities = (
        df.groupby(["country_code", "locality_norm"])
        .agg(lat=("lat", "median"), lon=("lon", "median"))
        .reset_index()
        .rename(columns={"locality_norm": "city"})
    )
    return cities.dropna(subset=["lat", "lon"])


def download_open_meteo() -> None:
    print("=== 4. Open-Meteo (ERA5 historical weather) ===")
    locs_path = RAW_DIR / "openaq_locations.csv"
    if not locs_path.exists():
        print("  openaq_locations.csv not found — skipping.")
        return

    locs = pd.read_csv(locs_path)
    cities = _clean_cities(locs)
    print(f"  Fetching weather for {len(cities)} city groups…")

    frames = []
    for _, row in cities.iterrows():
        params = {
            "latitude":   round(row["lat"], 4),
            "longitude":  round(row["lon"], 4),
            "start_date": WEATHER_START,
            "end_date":   WEATHER_END,
            "daily":      ",".join(WEATHER_VARS),
            "timezone":   "UTC",
        }
        for attempt in range(3):
            try:
                r = SESSION.get("https://archive-api.open-meteo.com/v1/archive",
                                params=params, timeout=45)
                if r.status_code == 429:
                    wait = 15 * (attempt + 1)
                    print(f"  429 — waiting {wait}s…")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                daily = r.json().get("daily", {})
                dates = daily.get("time", [])
                if not dates:
                    print(f"  {row['country_code']}:{row['city']} — no data")
                    break
                n = len(dates)
                df = pd.DataFrame({
                    "date":              dates,
                    "country_code":      row["country_code"],
                    "city":              row["city"],
                    "lat":               row["lat"],
                    "lon":               row["lon"],
                    "temp_max_c":        daily.get("temperature_2m_max",  [None] * n),
                    "temp_min_c":        daily.get("temperature_2m_min",  [None] * n),
                    "precipitation_mm":  daily.get("precipitation_sum",   [None] * n),
                    "windspeed_max_kmh": daily.get("windspeed_10m_max",   [None] * n),
                })
                frames.append(df)
                print(f"  {row['country_code']}:{row['city']}: {n} days")
                break
            except Exception as e:
                print(f"  {row['country_code']}:{row['city']} attempt {attempt+1}: {e}")
                time.sleep(5)
        time.sleep(2.5)

    if not frames:
        print("  No Open-Meteo data downloaded.")
        return

    out = pd.concat(frames, ignore_index=True)
    path = RAW_DIR / "open_meteo_weather.csv"
    out.to_csv(path, index=False)
    print(f"  → {path}  ({len(out):,} rows)\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent)  # run from project root
    download_who_gho()
    download_world_bank()
    download_ihme_owid()
    download_open_meteo()
    print("=== All downloads complete ===")
