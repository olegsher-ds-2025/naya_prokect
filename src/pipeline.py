"""
OpenAQ ingestion pipeline.

Produces two clean datasets:
  data/raw/openaq_locations.csv      — station metadata (country, city, lat/lng, sensors)
  data/processed/openaq_daily.csv    — daily PM2.5 / PM10 averages per location
  data/processed/openaq_monthly.csv  — monthly aggregates per country (for health data join)
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from loguru import logger

from src.openaq_client import (
    OpenAQClient, PM10_PARAMETER_ID, PM25_PARAMETER_ID,
    _GLOBAL_BACKOFF, _SHUTDOWN_EVENT,
)

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Kaggle paths (override when running on Kaggle)
KAGGLE_OUTPUT = Path(os.getenv("KAGGLE_OUTPUT", "data/output"))
KAGGLE_OUTPUT.mkdir(parents=True, exist_ok=True)

WHO_AQG_PM25 = 15.0   # µg/m³ — WHO 2021 guideline

# Top 10 cities ranked by absolute air-pollution-attributable mortality
# Source: IHME Global Burden of Disease 2019 / WHO Ambient Air Quality Database
# Format: (ISO-2 country code, locality keyword for OpenAQ substring match)
# Use None as keyword to include ALL sensors in a country (no locality filter).
TOP_MORTALITY_CITIES: list[tuple[str, str | None]] = [
    ("IN", "Delhi"),
    ("CN", "Beijing"),
    ("BD", "Dhaka"),
    ("PK", "Karachi"),
    ("IN", "Mumbai"),
    ("IN", "Kolkata"),
    ("PK", "Lahore"),
    ("EG", "Cairo"),
    ("ID", "Jakarta"),
    ("AF", "Kabul"),
]

# US comparison cities — highest PM2.5 burden in the US (EPA / ALA State of the Air 2023)
US_COMPARISON_CITIES: list[tuple[str, str | None]] = [
    ("US", "Los Angeles"),
    ("US", "Fresno"),
    ("US", "Houston"),
]

# Israel — all available sensors (small network, ~16 stations)
ISRAEL_CITIES: list[tuple[str, str | None]] = [
    ("IL", None),  # None = fetch every sensor in this country
]

# Combined: use this for the --top-mortality-cities flag
PRIORITY_CITIES: list[tuple[str, str | None]] = (
    TOP_MORTALITY_CITIES + US_COMPARISON_CITIES + ISRAEL_CITIES
)


def _extract_sensor_id(location: dict, parameter_id: int) -> int | None:
    for sensor in location.get("sensors", []):
        if sensor.get("parameter", {}).get("id") == parameter_id:
            return sensor["id"]
    return None


def _parse_dt(dt_field: dict | None) -> str | None:
    if not dt_field:
        return None
    return (dt_field.get("utc") or "")[:10] or None


def build_locations_df(
    client: OpenAQClient,
    country_codes: list[str] | None = None,
    cities: list[tuple[str, str]] | None = None,
    monitor_only: bool | None = None,
    min_date_last: date | None = None,
) -> pd.DataFrame:
    """
    Fetch all active monitoring locations globally (or for specified countries/cities).

    Args:
        country_codes:  ISO-2 country codes to fetch (e.g. ["US", "IN"]).
                        None = global fetch.
        cities:         List of (ISO-2, locality_keyword) pairs to restrict to specific
                        cities, e.g. [("IN", "Delhi"), ("CN", "Beijing")].
                        Fetches per country then post-filters by locality substring.
                        Overrides country_codes when provided.
        monitor_only:   Restrict to government/reference monitors.
                        Defaults to True for global/country mode, False for city mode
                        (developing-world cities rarely have reference-grade monitors).
        min_date_last:  Drop sensors whose last report is before this date.
                        Defaults to 18 months ago so stale sensors are excluded.
    """
    # Auto-resolve monitor_only based on mode
    if monitor_only is None:
        monitor_only = cities is None  # False for city mode, True for global/country

    # Default recency cutoff: sensors must have reported in the last 18 months
    if min_date_last is None:
        min_date_last = date.today() - timedelta(days=548)

    # Build fetch targets: derive country list from cities if provided
    if cities:
        unique_countries = list(dict.fromkeys(cc for cc, _ in cities))
        targets = unique_countries
        city_keywords: dict[str, list] = {}
        for cc, kw in cities:
            # None keyword = country-wide (no locality filter); keep as None, don't lowercase
            city_keywords.setdefault(cc, []).append(kw.lower() if kw is not None else None)
        logger.info(
            f"City filter active — {len(cities)} entries across "
            f"{len(unique_countries)} countries: "
            + ", ".join(f"{kw or 'ALL'}({cc})" for cc, kw in cities)
        )
    else:
        targets = country_codes or [None]  # None = global fetch
        city_keywords = {}

    logger.info(
        f"monitor_only={monitor_only}  |  "
        f"min_date_last={min_date_last} (sensors inactive before this are skipped)"
    )

    rows = []

    for cc in targets:
        label = cc or "global"
        logger.info(f"Fetching locations for {label} (monitor_only={monitor_only})")
        for param_id in (PM25_PARAMETER_ID, PM10_PARAMETER_ID):
            locs = client.get_locations(
                country_code=cc,
                parameters_id=param_id,
                only_active=True,
                monitor_only=monitor_only,
            )

            # Drop sensors that haven't reported since min_date_last
            before_recency = len(locs)
            locs = [
                loc for loc in locs
                if (_parse_dt(loc.get("datetimeLast")) or "0000-00-00") >= str(min_date_last)
            ]
            if before_recency != len(locs):
                logger.info(
                    f"  {cc or 'global'}/{param_id}: "
                    f"{before_recency} → {len(locs)} after recency filter (>{min_date_last})"
                )

            # Post-filter to matching localities when city filter is active.
            # Check both `locality` and `name` — many countries (India, China, etc.)
            # leave locality=None but embed the city in the location name.
            # A None keyword means "all sensors in this country" — skip filtering.
            if cc and cc in city_keywords:
                keywords = city_keywords[cc]
                if None not in keywords:
                    before = len(locs)
                    locs = [
                        loc for loc in locs
                        if any(
                            kw in (loc.get("locality") or "").lower()
                            or kw in (loc.get("name") or "").lower()
                            for kw in keywords
                        )
                    ]
                    logger.info(f"  {cc}/{param_id}: {before} → {len(locs)} after city filter")
                else:
                    logger.info(f"  {cc}/{param_id}: {len(locs)} sensors (all included — country-wide)")

            for loc in locs:
                sensor_id = _extract_sensor_id(loc, param_id)
                if sensor_id is None:
                    continue
                coord = loc.get("coordinates") or {}
                rows.append({
                    "location_id":   loc["id"],
                    "location_name": loc.get("name", ""),
                    "country_code":  loc.get("country", {}).get("code", ""),
                    "country_name":  loc.get("country", {}).get("name", ""),
                    "locality":      loc.get("locality") or "",
                    "lat":           coord.get("latitude"),
                    "lon":           coord.get("longitude"),
                    "is_monitor":    loc.get("isMonitor", False),
                    "parameter_id":  param_id,
                    "parameter":     "pm25" if param_id == PM25_PARAMETER_ID else "pm10",
                    "sensor_id":     sensor_id,
                    "date_first":    _parse_dt(loc.get("datetimeFirst")),
                    "date_last":     _parse_dt(loc.get("datetimeLast")),
                })

    df = pd.DataFrame(rows).drop_duplicates(subset=["sensor_id"])
    logger.info(f"Locations found: {len(df)}")
    if df.empty:
        logger.warning(
            "No locations found! Possible causes: all sensors stale, "
            "locality names don't match OpenAQ data, or no sensors for these countries."
        )
    return df


def _fetch_measurements_for_sensor(
    client: OpenAQClient, sensor_id: int, date_from: date, date_to: date
) -> list[dict]:
    try:
        return client.get_sensor_measurements(sensor_id, date_from, date_to)
    except Exception as e:
        logger.warning(f"Sensor {sensor_id} failed: {e}")
        return []


def _measurements_to_df(raw: list[dict], sensor_id: int) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    rows = []
    for m in raw:
        dt_from = (m.get("period") or {}).get("datetimeFrom", {})
        utc_str = (dt_from.get("utc") or "") if isinstance(dt_from, dict) else ""
        if not utc_str:
            continue
        rows.append({
            "sensor_id": sensor_id,
            "datetime_utc": utc_str,
            "date": utc_str[:10],
            "value": m.get("value"),
        })
    return pd.DataFrame(rows)


def build_daily_df(
    client: OpenAQClient,
    locations_df: pd.DataFrame,
    date_from: date,
    date_to: date,
    max_workers: int | None = None,
) -> pd.DataFrame:
    """
    Fetch hourly measurements for all sensors and aggregate to daily averages.

    max_workers defaults to 2 for full-load (wide date range) and 4 for
    incremental runs, to stay within API rate limits.
    """
    date_span_days = (date_to - date_from).days
    if max_workers is None:
        max_workers = 2 if date_span_days > 30 else 4
    sensors = locations_df[["sensor_id", "location_id", "location_name",
                              "country_code", "country_name", "locality",
                              "lat", "lon", "parameter"]].drop_duplicates("sensor_id")

    logger.info(f"Fetching measurements for {len(sensors)} sensors "
                f"({date_from} → {date_to}) with {max_workers} workers")

    all_frames: list[pd.DataFrame] = []
    _SHUTDOWN_EVENT.clear()  # ensure clean state before starting

    pool = ThreadPoolExecutor(max_workers=max_workers)
    future_to_row = {
        pool.submit(_fetch_measurements_for_sensor, client, row.sensor_id, date_from, date_to): row
        for row in sensors.itertuples()
    }
    done = 0
    total = len(future_to_row)
    try:
        for future in as_completed(future_to_row):
            row = future_to_row[future]
            try:
                raw = future.result()
            except (InterruptedError, Exception) as exc:
                if isinstance(exc, InterruptedError):
                    raise KeyboardInterrupt from exc
                logger.warning(f"Sensor {row.sensor_id} error: {exc}")
                raw = []
            df = _measurements_to_df(raw, row.sensor_id)
            if not df.empty:
                df["location_id"]   = row.location_id
                df["location_name"] = row.location_name
                df["country_code"]  = row.country_code
                df["country_name"]  = row.country_name
                df["locality"]      = row.locality
                df["lat"]           = row.lat
                df["lon"]           = row.lon
                df["parameter"]     = row.parameter
                all_frames.append(df)
            done += 1
            if done % 50 == 0:
                logger.info(f"  {done}/{total} sensors processed")
    except KeyboardInterrupt:
        logger.warning(f"Interrupted after {done}/{total} sensors — returning partial results")
        _SHUTDOWN_EVENT.set()   # wake any threads sleeping in rate-limit backoff
        _GLOBAL_BACKOFF.set()   # unblock threads waiting on the backoff gate
        pool.shutdown(wait=False, cancel_futures=True)
    else:
        pool.shutdown(wait=False)

    if not all_frames:
        logger.warning("No measurement data returned!")
        return pd.DataFrame()

    hourly = pd.concat(all_frames, ignore_index=True)
    hourly["value"] = pd.to_numeric(hourly["value"], errors="coerce")
    hourly = hourly[hourly["value"] >= 0]  # drop negative/invalid readings

    # Aggregate to daily average per location + parameter
    daily = (
        hourly.groupby(
            ["date", "location_id", "location_name", "country_code",
             "country_name", "locality", "lat", "lon", "parameter"],
            as_index=False,
        )
        .agg(value_mean=("value", "mean"), reading_count=("value", "count"))
        .rename(columns={"value_mean": "value_ugm3"})
    )
    daily["value_ugm3"] = daily["value_ugm3"].round(2)
    daily = daily.sort_values(["date", "country_code", "location_name"])
    logger.info(f"Daily records: {len(daily)}")
    return daily


def build_monthly_country_df(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily location data to monthly country-level averages."""
    df = daily_df.copy()
    df["year_month"] = df["date"].str[:7]  # YYYY-MM

    monthly = (
        df.groupby(["year_month", "country_code", "country_name", "parameter"], as_index=False)
        .agg(
            value_mean_ugm3=("value_ugm3", "mean"),
            station_count=("location_id", "nunique"),
            reading_count=("reading_count", "sum"),
        )
    )
    monthly["value_mean_ugm3"] = monthly["value_mean_ugm3"].round(2)

    # Flag countries exceeding WHO guideline (PM2.5)
    pm25 = monthly["parameter"] == "pm25"
    monthly.loc[pm25, "exceeds_who_guideline"] = (
        monthly.loc[pm25, "value_mean_ugm3"] > WHO_AQG_PM25
    )
    monthly = monthly.sort_values(["year_month", "country_code"])
    logger.info(f"Monthly country records: {len(monthly)}")
    return monthly


def run_pipeline(
    api_key: str,
    date_from: date | None = None,
    date_to: date | None = None,
    country_codes: list[str] | None = None,
    cities: list[tuple[str, str]] | None = None,
    monitor_only: bool | None = None,
    max_workers: int | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Full Phase 1 pipeline.

    Returns dict with keys: 'locations', 'daily', 'monthly'
    and saves CSV files to data/raw/ and data/processed/.

    Args:
        cities:       List of (ISO-2, locality_keyword) pairs, e.g. TOP_MORTALITY_CITIES.
                      When set, overrides country_codes and restricts to matching cities.
        monitor_only: None = auto (True for global/country, False for city mode).
    """
    date_to   = date_to   or date.today()
    date_from = date_from or (date_to - timedelta(days=365))

    client = OpenAQClient(api_key)

    # 1. Locations — monitor_only auto-resolves; sensors inactive before date_from excluded
    locations_df = build_locations_df(
        client, country_codes, cities=cities,
        monitor_only=monitor_only,
        min_date_last=date_from,
    )
    locations_path = RAW_DIR / "openaq_locations.csv"
    locations_df.to_csv(locations_path, index=False)
    logger.success(f"Saved {len(locations_df)} locations → {locations_path}")

    # 2. Daily measurements (workers auto-scaled by date range)
    daily_df = build_daily_df(client, locations_df, date_from, date_to)
    if not daily_df.empty:
        daily_path = PROCESSED_DIR / "openaq_daily.csv"
        daily_df.to_csv(daily_path, index=False)
        logger.success(f"Saved {len(daily_df)} daily records → {daily_path}")

    # 3. Monthly country aggregation
    if not daily_df.empty:
        monthly_df = build_monthly_country_df(daily_df)
        monthly_path = PROCESSED_DIR / "openaq_monthly.csv"
        monthly_df.to_csv(monthly_path, index=False)
        logger.success(f"Saved {len(monthly_df)} monthly records → {monthly_path}")
    else:
        monthly_df = pd.DataFrame()

    return {"locations": locations_df, "daily": daily_df, "monthly": monthly_df}


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="OpenAQ ingestion pipeline")
    parser.add_argument(
        "--country",
        nargs="+",
        metavar="ISO2",
        default=None,
        help="ISO-2 country code(s) to filter (e.g. US, IN, DE). Omit for global fetch.",
    )
    parser.add_argument(
        "--top-mortality-cities",
        action="store_true",
        help=(
            "Download sensors for the top 10 highest-mortality cities (IHME GBD 2019) "
            "+ 3 US comparison cities (Los Angeles, Fresno, Houston). "
            "Overrides --country."
        ),
    )
    parser.add_argument(
        "--city",
        nargs="+",
        metavar="ISO2:LOCALITY",
        default=None,
        help=(
            "Custom city filter as ISO2:locality pairs, "
            "e.g. --city IN:Delhi CN:Beijing"
        ),
    )
    parser.add_argument("--date-from", metavar="YYYY-MM-DD", default=None)
    parser.add_argument("--date-to",   metavar="YYYY-MM-DD", default=None)
    parser.add_argument(
        "--max-workers", type=int, default=None,
        help="Parallel download threads (default: auto-scaled by date range)",
    )
    parser.add_argument(
        "--monitor-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Force monitor_only on/off. Default: auto (True for global/country, "
            "False for city mode — needed for developing-world cities)."
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENAQ_API_KEY", "")
    if not api_key:
        raise SystemExit("ERROR: OPENAQ_API_KEY not set in environment / .env file")

    # Resolve city filter
    cities: list[tuple[str, str | None]] | None = None
    if args.top_mortality_cities:
        cities = PRIORITY_CITIES
    elif args.city:
        try:
            cities = []
            for pair in args.city:
                parts = pair.split(":", 1)
                cc = parts[0].upper()
                kw = parts[1] if len(parts) > 1 else None  # no colon → country-wide
                cities.append((cc, kw))
        except (IndexError, ValueError):
            raise SystemExit("ERROR: --city values must be ISO2 or ISO2:locality, e.g. IL or IN:Delhi")

    run_pipeline(
        api_key=api_key,
        date_from=date.fromisoformat(args.date_from) if args.date_from else None,
        date_to=date.fromisoformat(args.date_to)     if args.date_to   else None,
        country_codes=args.country if not cities else None,
        cities=cities,
        monitor_only=args.monitor_only,
        max_workers=args.max_workers,
    )
