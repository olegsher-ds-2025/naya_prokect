"""Generate presentation chart PNGs from project data."""

import os
import warnings
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

warnings.filterwarnings('ignore')

OUT = 'notebooks/charts'
os.makedirs(OUT, exist_ok=True)

WHO_LIMIT = 15.0
PALETTE   = px.colors.qualitative.Bold

# ── Load data ─────────────────────────────────────────────────────────────────
who     = pd.read_csv('data/raw/who_gho_air_pollution.csv')
ihme    = pd.read_csv('data/raw/ihme_gbd_air_pollution.csv')
daily   = pd.read_csv('data/processed/openaq_daily.csv')

def who_countries(df):
    return df[df['country_code_3'].str.match('^[A-Z]{3}$', na=False)]

def save(fig, name, w=1200, h=600):
    path = f'{OUT}/{name}.png'
    pio.write_image(fig, path, format='png', width=w, height=h, scale=2)
    print(f'  saved {path}')

TEMPLATE = dict(
    template='plotly_dark',
    paper_bgcolor='#1A1A2E',
    plot_bgcolor='#16213E',
    font=dict(family='Arial', color='#CCDDEE', size=13),
)

# ── Q1: Top 30 countries by PM2.5 ────────────────────────────────────────────
print('Q1...')
pm25 = (who[(who['indicator_code']=='SDGPM25') & (who['sex']=='RESIDENCEAREATYPE_TOTL')]
        .pipe(who_countries)
        .groupby(['country_code_3','year'])['value'].median()
        .reset_index().rename(columns={'value':'pm25'}))

top30 = (pm25.sort_values('year')
             .groupby('country_code_3').last().reset_index()
             .nlargest(30,'pm25').sort_values('pm25'))
top30['multiple'] = (top30['pm25'] / WHO_LIMIT).round(1)
top30['bar_color'] = top30['pm25'].apply(
    lambda v: '#FF4D4D' if v > 45 else ('#FF6B35' if v > 30 else '#2DC671'))

fig = go.Figure(go.Bar(
    y=top30['country_code_3'], x=top30['pm25'], orientation='h',
    marker_color=top30['bar_color'],
    text=top30['pm25'].round(1).astype(str) + ' (' + top30['multiple'].astype(str) + '×)',
    textposition='outside', textfont=dict(color='#CCDDEE', size=11),
    hovertemplate='<b>%{y}</b>  PM2.5: %{x:.1f} µg/m³<extra></extra>',
))
fig.add_vline(x=WHO_LIMIT, line_dash='dash', line_color='#00B4D8', line_width=2,
              annotation_text='WHO limit 15 µg/m³', annotation_font_color='#00B4D8',
              annotation_position='top right')
fig.update_layout(
    title=dict(text='<b>Top 30 Countries by Annual Mean PM2.5 (2023, WHO GHO)</b>',
               font=dict(size=16, color='white')),
    xaxis_title='Annual Mean PM2.5 (µg/m³)',
    xaxis=dict(range=[0, top30['pm25'].max() * 1.25]),
    height=700, margin=dict(r=160, l=60, t=60, b=50),
    **TEMPLATE,
)
save(fig, 'q1_top30_pm25', w=1200, h=700)

# ── Q2: PM2.5 vs mortality scatter ───────────────────────────────────────────
print('Q2...')
air10 = (who[(who['indicator_code']=='AIR_10') & (who['sex']=='SEX_BTSX')]
         .pipe(who_countries)
         .groupby(['country_code_3','year'])['value'].median()
         .reset_index().rename(columns={'value':'mort_rate'}))

pm25_2019 = pm25[pm25['year']==2019]
q2 = pm25_2019.merge(air10[air10['year']==2019], on=['country_code_3','year'])
q2 = q2[q2['mort_rate'] > 0]

africa = {'NGA','TCD','SLE','MLI','GIN','NER','CIV','CAF','CMR','BFA','GNB','MOZ','MDG',
          'TZA','UGA','ETH','COD','SSD','SDN','ZMB','MWI','BDI','RWA','COG','GHA','SEN',
          'GMB','LBR','BEN','TGO','ERI','DJI','KEN','ZWE','LSO','SWZ','NAM','BWA','ZAF'}
q2['region'] = q2['country_code_3'].apply(
    lambda c: 'Sub-Saharan Africa' if c in africa
    else ('Gulf / MENA' if c in {'QAT','KWT','SAU','ARE','BHR','OMN','EGY','DZA','MAR','LBY'}
    else ('South Asia' if c in {'IND','PAK','BGD','NPL','LKA','AFG'} else 'Rest of World')))

corr = q2[['pm25','mort_rate']].corr().iloc[0,1]

fig = px.scatter(q2, x='pm25', y='mort_rate', color='region',
    trendline='ols', trendline_scope='overall',
    color_discrete_map={
        'Sub-Saharan Africa': '#FF6B35',
        'Gulf / MENA':        '#FF4D4D',
        'South Asia':         '#FFD600',
        'Rest of World':      '#00B4D8',
    },
    labels={'pm25':'Annual PM2.5 (µg/m³)', 'mort_rate':'Mortality Rate (per 100k)', 'region':'Region'},
    title=f'<b>PM2.5 vs Air-Pollution Mortality — 183 Countries (2019) | r = {corr:.2f}</b>',
    hover_data=['country_code_3'],
    template='plotly_dark',
)
fig.update_layout(paper_bgcolor='#1A1A2E', plot_bgcolor='#16213E',
                  font=dict(family='Arial', color='#CCDDEE', size=13))
fig.add_vline(x=WHO_LIMIT, line_dash='dot', line_color='#00B4D8',
              annotation_text='WHO 15 µg/m³', annotation_font_color='#00B4D8')
fig.update_traces(marker=dict(size=7, opacity=0.8),
                  selector=dict(mode='markers'))
fig.update_layout(height=550, margin=dict(t=60, b=50, l=60, r=30))
save(fig, 'q2_scatter', w=1200, h=550)

# ── Q3: IHME death rates top 20 ──────────────────────────────────────────────
print('Q3...')
ihme_rates = (ihme.dropna(subset=['death_rates_from_all_air_pollution_per_100000'])
              [['entity','year','death_rates_from_all_air_pollution_per_100000']])
excl = 'World|Asia|Africa|Europe|America|income|SDI|Global|Oceania|East Asia|South Asia|OECD'
ihme_c = ihme_rates[~ihme_rates['entity'].str.contains(excl, case=False, na=False)]

top20 = (ihme_c[ihme_c['year']==2015]
         .nlargest(20,'death_rates_from_all_air_pollution_per_100000')
         .sort_values('death_rates_from_all_air_pollution_per_100000')
         .rename(columns={'death_rates_from_all_air_pollution_per_100000':'rate'}))

fig = go.Figure(go.Bar(
    y=top20['entity'], x=top20['rate'], orientation='h',
    marker=dict(color=top20['rate'], colorscale='Reds', showscale=True,
                colorbar=dict(title=dict(text='Deaths/100k', font=dict(color='#CCDDEE')),
                              tickfont=dict(color='#CCDDEE'))),
    text=top20['rate'].round(1), textposition='outside',
    textfont=dict(color='#CCDDEE', size=11),
    hovertemplate='<b>%{y}</b><br>%{x:.1f} deaths per 100,000<extra></extra>',
))
fig.update_layout(
    title=dict(text='<b>Top 20 Countries: Air Pollution Death Rate per 100,000 (2015, IHME/Lelieveld)</b>',
               font=dict(size=15, color='white')),
    xaxis_title='Age-standardized Deaths per 100,000',
    xaxis=dict(range=[0, top20['rate'].max() * 1.2]),
    height=620, margin=dict(l=160, r=120, t=60, b=50),
    **TEMPLATE,
)
save(fig, 'q3_death_rates', w=1200, h=620)

# ── Q4: PM2.5 trends 2010-2023 ───────────────────────────────────────────────
print('Q4...')
top10_iso = pm25[pm25['year']==2023].nlargest(10,'pm25')['country_code_3'].tolist()
trend_df  = pm25[pm25['country_code_3'].isin(top10_iso)].copy()
base = (trend_df[trend_df['year']==2010]
        .set_index('country_code_3')['pm25'].rename('base2010'))
trend_df = trend_df.join(base, on='country_code_3')
trend_df['pct_vs_2010'] = (trend_df['pm25'] - trend_df['base2010']) / trend_df['base2010'] * 100

fig = make_subplots(1, 2,
    subplot_titles=('Absolute PM2.5 (µg/m³)', '% Change from 2010 baseline'),
    horizontal_spacing=0.1)

colors = ['#FF4D4D','#FF6B35','#FFD600','#00B4D8','#2DC671',
          '#A78BFA','#F472B6','#34D399','#60A5FA','#FB923C']
for i, iso in enumerate(top10_iso):
    d = trend_df[trend_df['country_code_3']==iso].sort_values('year')
    c = colors[i % len(colors)]
    kw = dict(x=d['year'], line=dict(color=c, width=2), mode='lines+markers',
              marker=dict(size=5), name=iso, legendgroup=iso)
    fig.add_trace(go.Scatter(**kw, y=d['pm25'],
        hovertemplate=f'<b>{iso}</b> %{{x}}: %{{y:.1f}} µg/m³<extra></extra>'), row=1, col=1)
    fig.add_trace(go.Scatter(**kw, y=d['pct_vs_2010'], showlegend=False,
        hovertemplate=f'<b>{iso}</b> %{{x}}: %{{y:+.1f}}%<extra></extra>'), row=1, col=2)

fig.add_hline(y=WHO_LIMIT, row=1, col=1, line_dash='dash', line_color='#00B4D8',
              annotation_text='WHO 15 µg/m³', annotation_font_color='#00B4D8')
fig.add_hline(y=0, row=1, col=2, line_color='#CCDDEE', line_width=1, line_dash='dot')
fig.update_yaxes(title_text='PM2.5 (µg/m³)', row=1, col=1,
                 gridcolor='#0F3D4A', color='#CCDDEE')
fig.update_yaxes(title_text='% vs 2010', row=1, col=2,
                 gridcolor='#0F3D4A', color='#CCDDEE')
fig.update_xaxes(gridcolor='#0F3D4A', color='#CCDDEE')
fig.update_layout(
    title=dict(text='<b>PM2.5 Trends — Top 10 Most-Polluted Countries (2010–2023)</b>',
               font=dict(size=15, color='white')),
    height=500, legend=dict(x=1.02, y=0.5, font=dict(color='#CCDDEE')),
    margin=dict(t=70, b=50, l=60, r=110),
    **TEMPLATE,
)
save(fig, 'q4_trends', w=1300, h=500)

# ── Q5: WHO exceedance ───────────────────────────────────────────────────────
print('Q5...')
pm25_d = daily[daily['parameter'] == 'pm25'].copy()
pm25_d['exceeds'] = pm25_d['value_ugm3'] > WHO_LIMIT

stats = (pm25_d.groupby('country_code')
         .agg(total=('value_ugm3','count'), over=('exceeds','sum'),
              peak=('value_ugm3','max'), mean=('value_ugm3','mean'))
         .assign(pct_over=lambda x: x['over'] / x['total'] * 100)
         .reset_index().sort_values('pct_over', ascending=False))

NAMES = {'BD':'Bangladesh','IN':'India','PK':'Pakistan','EG':'Egypt',
         'CN':'China','ID':'Indonesia','IL':'Israel','US':'United States'}
stats['country_name'] = stats['country_code'].map(NAMES)

bar_colors = ['#FF4D4D' if p >= 90 else '#FF6B35' if p >= 50 else '#2DC671'
              for p in stats['pct_over']]

fig = make_subplots(1, 2,
    subplot_titles=('% of Readings Exceeding WHO PM2.5 Limit (15 µg/m³)',
                    'Mean vs Peak PM2.5 by Country'),
    horizontal_spacing=0.12)

fig.add_trace(go.Bar(
    x=stats['country_name'], y=stats['pct_over'],
    marker_color=bar_colors,
    text=stats['pct_over'].round(0).astype(int).astype(str) + '%',
    textposition='outside', textfont=dict(color='#CCDDEE'),
    hovertemplate='<b>%{x}</b><br>%{y:.1f}% exceed WHO<extra></extra>',
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=stats['mean'], y=stats['peak'],
    mode='markers+text', text=stats['country_name'],
    textposition='top center', textfont=dict(color='#CCDDEE', size=11),
    marker=dict(size=16, color=stats['pct_over'], colorscale='Reds',
                showscale=True, colorbar=dict(title=dict(text='% Exceeding', font=dict(color='#CCDDEE')),
                              tickfont=dict(color='#CCDDEE'))),
    hovertemplate='<b>%{text}</b><br>Mean: %{x:.0f}  Peak: %{y:.0f} µg/m³<extra></extra>',
), row=1, col=2)
fig.add_vline(x=WHO_LIMIT, row=1, col=2, line_dash='dash', line_color='#00B4D8',
              annotation_text='WHO mean limit', annotation_font_color='#00B4D8')

fig.update_yaxes(title_text='% Readings Over Limit', row=1, col=1,
                 range=[0, 115], gridcolor='#0F3D4A', color='#CCDDEE')
fig.update_xaxes(gridcolor='#0F3D4A', color='#CCDDEE')
fig.update_xaxes(title_text='Mean PM2.5 (µg/m³)', row=1, col=2, color='#CCDDEE')
fig.update_yaxes(title_text='Peak Single Reading (µg/m³)', row=1, col=2,
                 gridcolor='#0F3D4A', color='#CCDDEE')
fig.update_layout(
    title=dict(text='<b>WHO PM2.5 Exceedance — 8 Monitored Countries</b>',
               font=dict(size=15, color='white')),
    height=500, showlegend=False, margin=dict(t=70, b=50, l=60, r=100),
    **TEMPLATE,
)
save(fig, 'q5_exceedance', w=1200, h=500)

print('\nAll charts generated in', OUT)
