"""
Generates 5 flat CSVs for Tableau — one per business question in the analysis notebook.

Output: data/output/tableau/
  q1_country_pm25_ranking.csv        — Q1: Where is air dirtiest?
  q2_pollution_vs_mortality.csv      — Q2: Does pollution cause more deaths?
  q3_per_capita_death_rates.csv      — Q3: Who bears the highest per-capita toll?
  q4_pm25_trends.csv                 — Q4: Are we winning or losing? (2010–2023)
  q5_who_exceedance.csv              — Q5: How effective is the WHO guideline?
"""

import os
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'data', 'raw')
PROC = os.path.join(ROOT, 'data', 'processed')
OUT = os.path.join(ROOT, 'data', 'output', 'tableau')
os.makedirs(OUT, exist_ok=True)

WHO_LIMIT = 15.0

# ── Load sources ──────────────────────────────────────────────────────────────
who   = pd.read_csv(os.path.join(RAW, 'who_gho_air_pollution.csv'))
ihme  = pd.read_csv(os.path.join(RAW, 'ihme_gbd_air_pollution.csv'))
daily = pd.read_csv(os.path.join(PROC, 'openaq_daily.csv'))


def _keep_country_codes(df, col='country_code_3'):
    """Drop regional aggregates — keep only 3-letter ISO country codes."""
    return df[df[col].str.match(r'^[A-Z]{3}$', na=False)]


# ── Q1: Country PM2.5 ranking ─────────────────────────────────────────────────
print('Q1 …')
pm25_all = (
    who[(who['indicator_code'] == 'SDGPM25') & (who['sex'] == 'RESIDENCEAREATYPE_TOTL')]
    .pipe(_keep_country_codes)
    .groupby(['country_code_3', 'year'], as_index=False)['value']
    .median()
    .rename(columns={'value': 'pm25_ugm3'})
)

# Latest available year per country
q1 = (
    pm25_all.sort_values('year')
    .groupby('country_code_3', as_index=False).last()
    .assign(
        who_multiple=lambda x: (x['pm25_ugm3'] / WHO_LIMIT).round(2),
        who_limit_ugm3=WHO_LIMIT,
        exceeds_who=lambda x: x['pm25_ugm3'] > WHO_LIMIT,
        pollution_tier=lambda x: x['pm25_ugm3'].apply(
            lambda v: 'Critical (>3× WHO)'  if v > 45
            else ('High (2–3× WHO)'         if v > 30
            else ('Moderate (1–2× WHO)'     if v > 15
            else 'Clean (≤ WHO limit)'))
        ),
    )
    .rename(columns={'country_code_3': 'country_code', 'year': 'data_year'})
    [['country_code', 'data_year', 'pm25_ugm3', 'who_limit_ugm3', 'who_multiple',
      'exceeds_who', 'pollution_tier']]
    .sort_values('pm25_ugm3', ascending=False)
    .reset_index(drop=True)
)

q1.to_csv(os.path.join(OUT, 'q1_country_pm25_ranking.csv'), index=False)
print(f'  {len(q1)} countries → q1_country_pm25_ranking.csv')


# ── Q2: PM2.5 vs mortality scatter ────────────────────────────────────────────
print('Q2 …')
air10 = (
    who[(who['indicator_code'] == 'AIR_10') & (who['sex'] == 'SEX_BTSX')]
    .pipe(_keep_country_codes)
    .groupby(['country_code_3', 'year'], as_index=False)['value']
    .median()
    .rename(columns={'value': 'mortality_rate_per_100k'})
)

pm25_2019 = pm25_all[pm25_all['year'] == 2019]
mort_2019 = air10[air10['year'] == 2019]

AFRICA = {
    'NGA','TCD','SLE','MLI','GIN','NER','CIV','CAF','CMR','BFA','GNB','MOZ','MDG',
    'TZA','UGA','ETH','COD','SSD','SDN','ZMB','MWI','BDI','RWA','COG','GHA','SEN',
    'GMB','LBR','BEN','TGO','ERI','DJI','KEN','ZWE','LSO','SWZ','NAM','BWA','ZAF',
}
GULF = {'QAT','KWT','SAU','ARE','BHR','OMN','EGY','DZA','MAR','LBY'}
SOUTH_ASIA = {'IND','PAK','BGD','NPL','LKA','AFG'}

q2 = (
    pm25_2019.merge(mort_2019, on=['country_code_3', 'year'])
    .query('mortality_rate_per_100k > 0')
    .assign(
        region=lambda x: x['country_code_3'].map(
            lambda c: 'Sub-Saharan Africa' if c in AFRICA
            else ('Gulf / MENA'   if c in GULF
            else ('South Asia'    if c in SOUTH_ASIA
            else 'Rest of World'))
        ),
        who_limit_ugm3=WHO_LIMIT,
        exceeds_who=lambda x: x['pm25_ugm3'] > WHO_LIMIT,
    )
    .rename(columns={'country_code_3': 'country_code', 'year': 'data_year'})
    [['country_code', 'data_year', 'pm25_ugm3', 'mortality_rate_per_100k',
      'region', 'who_limit_ugm3', 'exceeds_who']]
    .sort_values('pm25_ugm3', ascending=False)
    .reset_index(drop=True)
)

q2.to_csv(os.path.join(OUT, 'q2_pollution_vs_mortality.csv'), index=False)
print(f'  {len(q2)} countries → q2_pollution_vs_mortality.csv')


# ── Q3: Per-capita death rates (IHME) ────────────────────────────────────────
print('Q3 …')
EXCL = r'World|Asia|Africa|Europe|America|income|SDI|Global|Oceania|East Asia|South Asia|OECD'
q3 = (
    ihme[
        ihme['death_rates_from_all_air_pollution_per_100000'].notna()
        & ~ihme['entity'].str.contains(EXCL, case=False, na=False)
    ]
    [['entity', 'year',
      'death_rates_from_all_air_pollution_per_100000',
      'death_rates_from_air_pollution_from_fossil_fuels_per_100000',
      'share_of_deaths_from_air_pollution_outdoor_and_indoor_ihme_2019']]
    .rename(columns={
        'entity': 'country_name',
        'year': 'data_year',
        'death_rates_from_all_air_pollution_per_100000': 'death_rate_all_per_100k',
        'death_rates_from_air_pollution_from_fossil_fuels_per_100000': 'death_rate_fossil_per_100k',
        'share_of_deaths_from_air_pollution_outdoor_and_indoor_ihme_2019': 'share_of_deaths_pct',
    })
    .sort_values(['data_year', 'death_rate_all_per_100k'], ascending=[True, False])
    .reset_index(drop=True)
)

q3.to_csv(os.path.join(OUT, 'q3_per_capita_death_rates.csv'), index=False)
print(f'  {len(q3)} rows → q3_per_capita_death_rates.csv')


# ── Q4: PM2.5 trends 2010–2023 ───────────────────────────────────────────────
print('Q4 …')
top10_iso = (
    pm25_all[pm25_all['year'] == 2023]
    .nlargest(10, 'pm25_ugm3')['country_code_3']
    .tolist()
)

trend = pm25_all[pm25_all['country_code_3'].isin(top10_iso)].copy()
base_2010 = (
    trend[trend['year'] == 2010]
    .set_index('country_code_3')['pm25_ugm3']
    .rename('pm25_2010_baseline')
)
trend = trend.join(base_2010, on='country_code_3')
trend['pct_change_vs_2010'] = (
    (trend['pm25_ugm3'] - trend['pm25_2010_baseline']) / trend['pm25_2010_baseline'] * 100
).round(2)
trend['who_limit_ugm3'] = WHO_LIMIT
trend['who_multiple'] = (trend['pm25_ugm3'] / WHO_LIMIT).round(2)

q4 = (
    trend
    .rename(columns={'country_code_3': 'country_code', 'year': 'data_year'})
    [['country_code', 'data_year', 'pm25_ugm3', 'pm25_2010_baseline',
      'pct_change_vs_2010', 'who_limit_ugm3', 'who_multiple']]
    .sort_values(['country_code', 'data_year'])
    .reset_index(drop=True)
)

q4.to_csv(os.path.join(OUT, 'q4_pm25_trends.csv'), index=False)
print(f'  {len(q4)} rows ({len(top10_iso)} countries) → q4_pm25_trends.csv')


# ── Q5: WHO exceedance — monitored countries ─────────────────────────────────
print('Q5 …')
pm25_d = daily[daily['parameter'] == 'pm25'].copy()
pm25_d['exceeds_who'] = pm25_d['value_ugm3'] > WHO_LIMIT

# Station-level detail (one row per reading — useful for date-based Tableau filters)
q5_detail = (
    pm25_d[['date', 'country_code', 'country_name', 'location_name',
             'lat', 'lon', 'value_ugm3', 'exceeds_who']]
    .assign(who_limit_ugm3=WHO_LIMIT)
    .sort_values(['country_code', 'date'])
    .reset_index(drop=True)
)
q5_detail.to_csv(os.path.join(OUT, 'q5_exceedance_daily_detail.csv'), index=False)

# Country-level summary (for bar/scatter charts)
q5_summary = (
    pm25_d.groupby(['country_code', 'country_name'], as_index=False)
    .agg(
        total_readings=('value_ugm3', 'count'),
        readings_over_who=('exceeds_who', 'sum'),
        mean_pm25_ugm3=('value_ugm3', 'mean'),
        peak_pm25_ugm3=('value_ugm3', 'max'),
        median_pm25_ugm3=('value_ugm3', 'median'),
    )
    .assign(
        pct_over_who=lambda x: (x['readings_over_who'] / x['total_readings'] * 100).round(1),
        who_limit_ugm3=WHO_LIMIT,
        mean_who_multiple=lambda x: (x['mean_pm25_ugm3'] / WHO_LIMIT).round(2),
        peak_who_multiple=lambda x: (x['peak_pm25_ugm3'] / WHO_LIMIT).round(1),
        compliance_status=lambda x: x['pct_over_who'].apply(
            lambda p: 'Near-compliant (<20%)'   if p < 20
            else ('Struggling (20–60%)'         if p < 60
            else ('Non-compliant (60–95%)'      if p < 95
            else 'Critical (≥95%)'))
        ),
    )
    .sort_values('pct_over_who', ascending=False)
    .reset_index(drop=True)
)
q5_summary.to_csv(os.path.join(OUT, 'q5_exceedance_country_summary.csv'), index=False)

print(f'  {len(q5_detail)} daily rows → q5_exceedance_daily_detail.csv')
print(f'  {len(q5_summary)} countries  → q5_exceedance_country_summary.csv')


# ── Done ─────────────────────────────────────────────────────────────────────
print(f'\nAll files written to: {OUT}')
files = sorted(os.listdir(OUT))
for f in files:
    size_kb = os.path.getsize(os.path.join(OUT, f)) // 1024
    print(f'  {f:<45} {size_kb:>4} KB')
