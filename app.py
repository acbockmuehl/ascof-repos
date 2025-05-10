# app.py
from flask import Flask, render_template, request, jsonify
import pandas as pd

app = Flask(__name__)

# Load data
measures_df = pd.read_csv('data/measures.csv')
ons_df = pd.read_csv('data/ons_codes.csv')
direction_df = pd.read_csv('data/measure_direction.csv')

# Filter outcome measures at council level
df = measures_df[
    (measures_df["Geographical Level"] == "Council") &
    (measures_df["Measure Type"] == "Outcome")
].copy()
df = df.merge(ons_df, how='left', left_on='ONS Code', right_on='ONS Area Code')
df['Measure_Value'] = pd.to_numeric(df['Measure_Value'], errors='coerce')
df = df.merge(direction_df, on='Measure Group Description', how='left')
df = df.dropna(subset=['Measure_Value', 'Measure Group Description'])

# Add percentiles per group
def calc_percentiles(group):
    ascending = (group['Direction'].iloc[0] == "Lower is better")
    group['Percentile'] = group['Measure_Value'].rank(pct=True, ascending=ascending) * 100
    return group

df_outcomes = df.groupby('Measure Group Description', group_keys=False).apply(calc_percentiles)

# England-level fallback
df_eng = measures_df[
    (measures_df["Geographical Level"] == "Country") &
    (measures_df["Geographical Description"] == "England") &
    (measures_df["Measure Type"] == "Outcome")
].copy()
df_eng['Measure_Value'] = pd.to_numeric(df_eng['Measure_Value'], errors='coerce')
df_eng = df_eng.merge(direction_df, on='Measure Group Description', how='left')
df_eng = df_eng.merge(
    df_outcomes.groupby('Measure Group Description')[['Measure_Value']].median().rename(columns={'Measure_Value': 'Median'}),
    left_on='Measure Group Description', right_index=True, how='left'
)
df_eng['Percentile'] = df_eng.apply(
    lambda row: (df_outcomes[df_outcomes['Measure Group Description'] == row['Measure Group Description']]['Measure_Value']
                 .lt(row['Measure_Value']).mean() * 100)
    if row['Direction'] == "Lower is better"
    else (df_outcomes[df_outcomes['Measure Group Description'] == row['Measure Group Description']]['Measure_Value']
          .le(row['Measure_Value']).mean() * 100),
    axis=1
)

@app.route('/')
def index():
    measure_groups = sorted(df['Measure Group Description'].dropna().unique())
    regions = sorted(df['Council region'].dropna().unique())
    disaggregations = sorted(df['Disaggregation Level'].dropna().unique())
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

    agg = (
        filtered.groupby('Geographical Description')[['Measure_Value']].sum()
        .sort_values(ascending=False, by='Measure_Value')
        .reset_index()
    )
    merged = agg.merge(filtered[['Geographical Description', 'Percentile']].drop_duplicates(), on='Geographical Description', how='left')
    return jsonify(merged.to_dict(orient='records'))

@app.route('/disaggregation-options')
def disaggregation_options():
    selected_measure = request.args.get('measure')
    if not selected_measure:
        return jsonify([])

    filtered = df[df['Measure Group Description'] == selected_measure]
    options = sorted(filtered['Disaggregation Level'].dropna().unique().tolist())
    return jsonify(options)

@app.route('/la-outcomes')
def la_outcomes():
    la_name = request.args.get('la')

    if la_name:
        table_df = df_outcomes[df_outcomes['Geographical Description'] == la_name]
    else:
        table_df = df_eng.copy()
        table_df['Geographical Description'] = 'England'

    table_df = table_df[['Geographical Description', 'Measure Group Description', 'Measure_Value', 'Percentile', 'Direction']]
    return jsonify(table_df.to_dict(orient='records'))

if __name__ == '__main__':
    app.run(debug=True)
