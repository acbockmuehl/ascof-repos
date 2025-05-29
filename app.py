from flask import Flask, render_template, request, jsonify
import pandas as pd
from dotenv import load_dotenv
import os
import numpy as np

# Load environment variables
load_dotenv()

app = Flask(__name__)

# === Load raw data ===
measures_df = pd.read_csv('data/measures.csv')
ons_df = pd.read_csv('data/ons_codes.csv')
direction_df = pd.read_csv('data/measure_direction.csv')  # contains 'Measure Group Description', 'Direction'
df_trend_full = pd.read_csv('data/trend_data.csv')  # trend data 2017–2024

# === Preprocess static summary data ===
df = measures_df[
    (measures_df["Geographical Level"] == "Council") &
    (measures_df["Measure Type"] == "Outcome")
].copy()

df['Measure_Value'] = pd.to_numeric(df['Measure_Value'], errors='coerce')
df.dropna(subset=['Measure_Value'], inplace=True)

df = df.groupby(['ONS Code', 'Geographical Description', 'Measure Group Description', 'Disaggregation Level']).agg({
    'Measure_Value': 'mean',
    'Measure Group': 'first'
}).reset_index()

df = df.merge(ons_df, how='left', left_on='ONS Code', right_on='ONS Area Code')
df = df.merge(direction_df, how='left', on='Measure Group Description')

df_outcomes = df  # used throughout app

# === Routes ===

@app.route('/')
def index():
    measure_group_df = df_outcomes[['Measure Group', 'Measure Group Description']].dropna().drop_duplicates()
    measure_group_df['Display'] = measure_group_df['Measure Group'] + ' – ' + measure_group_df['Measure Group Description']
    measure_group_df.sort_values(by='Measure Group', inplace=True)

    measure_groups = measure_group_df[['Measure Group Description', 'Display']].to_records(index=False)
    regions = sorted(df_outcomes['Council region'].dropna().unique())
    disaggregations = sorted(df_outcomes['Disaggregation Level'].dropna().unique())
    councils = sorted(df_outcomes['Geographical Description'].dropna().unique())

    return render_template('index.html', measure_groups=measure_groups, regions=regions, disaggregations=disaggregations, councils=councils)

@app.route('/pareto-data')
def pareto_data():
    selected_measure = request.args.get('measure')
    selected_regions = request.args.getlist('regions[]')
    selected_disagg = request.args.get('disagg')

    if not selected_measure:
        return jsonify({"error": "No measure provided"}), 400

    filtered = df_outcomes[df_outcomes['Measure Group Description'] == selected_measure].copy()

    if selected_regions:
        filtered = filtered[filtered['Council region'].isin(selected_regions)]
    if selected_disagg:
        filtered = filtered[filtered['Disaggregation Level'] == selected_disagg]

    filtered.dropna(subset=['Measure_Value'], inplace=True)

    agg = (
        filtered
        .groupby(['Geographical Description', 'Council region'])['Measure_Value']
        .sum()
        .reset_index()          # no sort yet
        .sort_values('Measure_Value', ascending=False)
    )
    return jsonify(agg.to_dict(orient='records'))

@app.route('/disaggregation-options')
def disaggregation_options():
    selected_measure = request.args.get('measure')
    if not selected_measure:
        return jsonify([])

    filtered = df_outcomes[df_outcomes['Measure Group Description'] == selected_measure]
    options = sorted(filtered['Disaggregation Level'].dropna().unique().tolist())
    return jsonify(options)

@app.route('/la-outcomes')
def la_outcomes():
    la_name = request.args.get('la')
    base_df = df_outcomes.copy()

    if la_name:
        subset = base_df[base_df['Geographical Description'].str.strip().str.lower() == la_name.strip().lower()].copy()
    else:
        subset = base_df[base_df['Geographical Description'].str.contains("England", case=False, na=False)].copy()

    if subset.empty:
        return jsonify([])

    def compute_percentile(value, group, direction):
        try:
            value = float(value)
        except:
            return None
        if direction == "Lower is better":
            return round(group['Measure_Value'].lt(value).mean() * 100, 2)
        else:
            return round(group['Measure_Value'].le(value).mean() * 100, 2)

    def compute_national_percentile(row):
        group = base_df[base_df['Measure Group Description'] == row['Measure Group Description']].dropna(subset=['Measure_Value'])
        return compute_percentile(row['Measure_Value'], group, row['Direction'])

    def compute_regional_percentile(row):
        region = row.get('Council region')
        if pd.isna(region):
            return None
        group = base_df[
            (base_df['Measure Group Description'] == row['Measure Group Description']) &
            (base_df['Council region'] == region)
        ].dropna(subset=['Measure_Value'])
        return compute_percentile(row['Measure_Value'], group, row['Direction'])

    subset['Percentile_National'] = subset.apply(compute_national_percentile, axis=1)
    subset['Percentile_Regional'] = subset.apply(compute_regional_percentile, axis=1)

    result = subset[[
        'Measure Group',
        'Measure Group Description',
        'Measure_Value',
        'Percentile_National',
        'Percentile_Regional',
        'Direction',
        'Disaggregation Level'
    ]].copy()

    result.sort_values(by='Measure Group', inplace=True)
    return jsonify(result.to_dict(orient='records'))

@app.route('/mistral-summary')
def mistral_summary_route():
    council = request.args.get('council')
    if not council:
        return jsonify({'error': 'Council not specified'}), 400

    comparison_df = generate_summary_for_council(council)
    summary = generate_mistral_summary(comparison_df, council)
    return jsonify({'summary': summary})

@app.route('/trend-data')
def trend_data():
    measure = request.args.get('measure')
    la = request.args.get('la')

    if not measure:
        return jsonify({'error': 'No measure provided'}), 400

    filtered = df_trend_full[df_trend_full['Measure Group Description'] == measure].copy()

    if filtered.empty:
        return jsonify({'error': 'No data found for that measure'}), 404

    england_df = filtered[filtered['Geographical Description'].str.lower() == 'england']
    england_trend = england_df.groupby('Year')['Measure_Value'].mean().sort_index().reset_index()
    result = {'england': england_trend.to_dict(orient='records')}

    if la:
        la_df = filtered[filtered['Geographical Description'].str.lower() == la.strip().lower()]
        la_trend = la_df.groupby('Year')['Measure_Value'].mean().sort_index().reset_index()
        result['la'] = la_trend.to_dict(orient='records')

        region = df_outcomes.loc[
            df_outcomes['Geographical Description'].str.lower() == la.strip().lower(),
            'Council region'
        ].dropna().unique()

        if len(region) > 0:
            region_name = region[0]
            region_df = filtered[filtered['Geographical Description'].isin(
                df_outcomes[df_outcomes['Council region'] == region_name]['Geographical Description']
            )]
            region_trend = region_df.groupby('Year')['Measure_Value'].mean().sort_index().reset_index()
            region_trend['Region'] = region_name  # ✅ add label for JS
            result['region'] = region_trend.to_dict(orient='records')

    return jsonify(result)

# === Placeholder functions – these should be implemented as needed ===
def generate_summary_for_council(council_name):
    return df_outcomes[df_outcomes['Geographical Description'].str.lower() == council_name.lower()]

def generate_mistral_summary(df, council_name):
    return f"Summary for {council_name} with {len(df)} outcome indicators."

# Load cost data
cost_df = pd.read_csv("data/grosscurrentexpenditure.csv")
cost_df['ITEMVALUE'] = pd.to_numeric(cost_df['ITEMVALUE'], errors='coerce')
cost_df['ITEMVALUE'] = cost_df['ITEMVALUE'].apply(lambda x: x if x >= 0 else np.nan)

@app.route('/cost-data')
def cost_data():
    # Get filters
    selected_la = request.args.get('la')
    region = request.args.get('region')
    age_groups = request.args.getlist('age_groups[]')
    setting = request.args.get('support_setting', 'Total')
    reason = request.args.get('primary_support_reason', 'Total')

    # Copy the full dataset for filtering
    df = cost_df.copy()

    # === Apply filters to build benchmark ===
    benchmark_df = df.copy()
    if region:
        benchmark_df = benchmark_df[benchmark_df['GEOGRAPHY_NAME'].notna() & (benchmark_df['GEOGRAPHY_NAME'].str.strip() == region.strip())]
    if age_groups:
        benchmark_df = benchmark_df[benchmark_df['AgeBand'].isin(age_groups)]
    if setting:
        benchmark_df = benchmark_df[benchmark_df['SupportSetting'] == setting]
    if reason:
        benchmark_df = benchmark_df[benchmark_df['PrimarySupportReason'] == reason]

    benchmark_df = benchmark_df[benchmark_df['GEOGRAPHY_LEVEL'] == 'Local Authority']
    latest_year = benchmark_df['FY_ENDING'].max()
    benchmark_df = benchmark_df[benchmark_df['FY_ENDING'] == latest_year]

    benchmark_data = (
        benchmark_df.groupby('DH_GEOGRAPHY_NAME', as_index=False)['ITEMVALUE']
        .sum()
        .dropna()
        .sort_values(by='ITEMVALUE', ascending=False)
    )

    benchmark = [
        {'Geographical Description': row['DH_GEOGRAPHY_NAME'], 'Measure_Value': round(row['ITEMVALUE'], 2)}
        for _, row in benchmark_data.iterrows()
    ]

    # === Build trend lines using full dataset ===
    def get_trend(df_subset):
        if df_subset.empty:
            return []
        trend = df_subset.groupby('FY_ENDING', as_index=False)['ITEMVALUE'].sum()
        trend.rename(columns={'FY_ENDING': 'Year', 'ITEMVALUE': 'Measure_Value'}, inplace=True)
        return trend.to_dict(orient='records')

    # Always use full dataset for trend (but apply filters)
    base_trend_df = df.copy()
    if age_groups:
        base_trend_df = base_trend_df[base_trend_df['AgeBand'].isin(age_groups)]
    if setting:
        base_trend_df = base_trend_df[base_trend_df['SupportSetting'] == setting]
    if reason:
        base_trend_df = base_trend_df[base_trend_df['PrimarySupportReason'] == reason]

    # England average of all Local Authorities (filtered)
    england_las_df = base_trend_df[base_trend_df['GEOGRAPHY_LEVEL'] == 'Local Authority']
    england_avg = (
        england_las_df
        .groupby('FY_ENDING')['ITEMVALUE']
        .mean()
        .reset_index()
        .rename(columns={'FY_ENDING': 'Year', 'ITEMVALUE': 'Measure_Value'})
        .to_dict(orient='records')
    )

    la = []
    region = []

    if selected_la:
        la_df = base_trend_df[base_trend_df['DH_GEOGRAPHY_NAME'] == selected_la]
        la = get_trend(la_df)

        # Find region name of selected LA
        region_name_arr = df[
            (df['DH_GEOGRAPHY_NAME'] == selected_la) & 
            (df['GEOGRAPHY_LEVEL'] == 'Local Authority')
        ]['GEOGRAPHY_NAME'].dropna().unique()

        if len(region_name_arr) > 0:
            region_name = region_name_arr[0]

            # Get list of other LAs in same region
            region_las = df[
                (df['GEOGRAPHY_NAME'] == region_name) &
                (df['GEOGRAPHY_LEVEL'] == 'Local Authority')
            ]['DH_GEOGRAPHY_NAME'].unique()

            # Filter for those LAs in the base trend df
            region_df = base_trend_df[base_trend_df['DH_GEOGRAPHY_NAME'].isin(region_las)]

            region = (
                region_df
                .groupby('FY_ENDING')['ITEMVALUE']
                .mean()
                .reset_index()
                .rename(columns={'FY_ENDING': 'Year', 'ITEMVALUE': 'Measure_Value'})
                .to_dict(orient='records')
            )

    print("FILTERED LA:", selected_la, "| REGION:", region, "| LA Trend Rows:", len(la), "| Region Trend Rows:", len(region))

    return jsonify({
        'benchmark': benchmark,
        'england': england_avg,
        'region': region,
        'la': la
    })

    
# === Run the app ===
if __name__ == '__main__':
    app.run(debug=True)