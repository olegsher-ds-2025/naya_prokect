Perform a structured data quality audit on the project's output CSVs.

**Filter (optional):** $ARGUMENTS

If an ISO-2 country code (e.g. `IN`) or city name (e.g. `Delhi`) is provided, filter all stats to that subset. Otherwise audit the full dataset.

Load the following files if they exist:
- `data/raw/openaq_locations.csv`
- `data/processed/openaq_daily.csv`
- `data/processed/openaq_monthly.csv`

For each file, report:

**Basic stats:**
- Row count and column names
- Date range (min/max of `date` or `year_month`)
- Unique `country_code` values and unique `location_id` or `location_name` values

**Parameter breakdown:**
- Count of `pm25` vs `pm10` rows in daily and locations files

**WHO guideline exceedances (monthly file):**
- Fraction of pm25 rows where `exceeds_who_guideline == True`
- Top 10 countries by `value_mean_ugm3` (worst pm25 pollution)

**Missing value check:**
- Any nulls in: `date`, `country_code`, `value_ugm3`, `location_id`, `parameter`

**Outlier detection:**
- Any `value_ugm3 > 500 µg/m³` — flag these rows (location, date, value) for review but do not delete them

**Recency check:**
- Is there daily data within the last 7 days? If not, warn that the pipeline likely needs re-running.

**Coverage gap check:**
- Which `location_id` values appear in `openaq_locations.csv` but have zero rows in `openaq_daily.csv`? List them (location_id, location_name, country_code).

Use pandas for all analysis. Print a clear, structured summary with section headers.

End with a one-line verdict:
- **PASS** — no issues found
- **WARN: [list of issues]** — one or more checks failed

Do not modify any files.
