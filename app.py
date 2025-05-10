from flask import Flask, render_template, request, jsonify
import pandas as pd

app = Flask(__name__)

# Load raw data
measures_df = pd.read_csv('data/measures.csv')
ons_df = pd.read_csv('data/ons_codes.csv')
direction_df = pd.read_csv('data/measure_direction.csv')  # contains 'Measure Group Description', 'Direction'

# Preprocess
df = measures_df[
    (measures_df["Geographical Level"] == "Council") &
    (measures_df["Measure Type"] == "Outcome")
].copy()

df['Measure_Value'] = pd.to_numeric(df['Measure_Value'], errors='coerce')
df = df.dropna(subset=['Measure_Value'])

# Collapse to 1 row per LA + measure group (avg or first as appropriate)
df = df.groupby(['ONS Code', 'Geographical Description', 'Measure Group Description']).agg({
    'Measure_Value': 'mean',
    'Disaggregation Level': 'first',
    'Measure Group': 'first'
}).reset_index()

# Merge ONS info and directions
df = df.merge(ons_df, how='left', left_on='ONS Code', right_on='ONS Area Code')
df = df.merge(direction_df, how='left', on='Measure Group Description')

df_outcomes = df  # used throughout app

@app.route('/')
def index():
    measure_groups = sorted(df_outcomes['Measure Group Description'].dropna().unique())
    regions = sorted(df_outcomes['Council region'].dropna().unique())
    disaggregations = sorted(df_outcomes['Disaggregation Level'].dropna().unique())
    return render_template('index.html', measure_groups=measure_groups, regions=regions, disaggregations=disaggregations)

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

    filtered = filtered.dropna(subset=['Measure_Value'])

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

    # National percentile
    def compute_national_percentile(row):
        group = base_df[
            base_df['Measure Group Description'] == row['Measure Group Description']
        ].dropna(subset=['Measure_Value'])

        if group.empty:
            return None

        try:
            value = float(row['Measure_Value'])
        except (TypeError, ValueError):
            return None

        if row['Direction'] == "Lower is better":
            rank = group['Measure_Value'].lt(value).mean()
        else:
            rank = group['Measure_Value'].le(value).mean()

        return round(rank * 100, 2)

    # Regional percentile
    def compute_regional_percentile(row):
        region = row.get('Council region')
        if pd.isna(region):
            return None

        group = base_df[
            (base_df['Measure Group Description'] == row['Measure Group Description']) &
            (base_df['Council region'] == region)
        ].dropna(subset=['Measure_Value'])

        if group.empty:
            return None

        try:
            value = float(row['Measure_Value'])
        except (TypeError, ValueError):
            return None

        if row['Direction'] == "Lower is better":
            rank = group['Measure_Value'].lt(value).mean()
        else:
            rank = group['Measure_Value'].le(value).mean()

        return round(rank * 100, 2)

    subset['Percentile_National'] = subset.apply(compute_national_percentile, axis=1)
    subset['Percentile_Regional'] = subset.apply(compute_regional_percentile, axis=1)

    result = subset[[
        'Measure Group',
        'Measure Group Description',
        'Measure_Value',
        'Percentile_National',
        'Percentile_Regional',
        'Direction'
    ]].copy()

    result.sort_values(by='Measure Group Description', ascending=False, inplace=True)
    return jsonify(result.to_dict(orient='records'))

if __name__ == '__main__':
    app.run(debug=True)
