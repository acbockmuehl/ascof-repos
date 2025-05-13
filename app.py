from flask import Flask, render_template, request, jsonify
import pandas as pd
from dotenv import load_dotenv
import os

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
        filtered.groupby('Geographical Description')['Measure_Value']
        .sum()
        .sort_values(ascending=False)
        .reset_index()
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

# === Run the app ===
if __name__ == '__main__':
    app.run(debug=True)
