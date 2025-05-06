from flask import Flask, render_template, request, jsonify
import pandas as pd

app = Flask(__name__)

# Load data
measures_df = pd.read_csv('data/measures.csv')
ons_df = pd.read_csv('data/ons_codes.csv')
df = measures_df[
    (measures_df["Geographical Level"] == "Council") &
    (measures_df["Measure Type"] == "Outcome")
].copy()
df = df.merge(ons_df, how='left', left_on='ONS Code', right_on='ONS Area Code')

# Static filter: One specific measure only
TARGET_MEASURE = "Long-term support needs of younger adults (aged 18-64) met by admission to residential and nursing care homes, per 100,000 population"

@app.route('/')
def index():
    measure_groups = sorted(df['Measure Group Description'].dropna().unique())
    regions = sorted(df['Council region'].dropna().unique())
    disaggregations = sorted(df['Disaggregation Level'].dropna().unique())
    return render_template('index.html', measure_groups=measure_groups, regions=regions, disaggregations=disaggregations)

@app.route('/pareto-data')
def pareto_data():
    selected_measure = request.args.get('measure')
    selected_regions = request.args.getlist('regions[]')  # multi-select
    selected_disagg = request.args.get('disagg')

    if not selected_measure:
        return jsonify({"error": "No measure provided"}), 400

    filtered = df[df['Measure Group Description'] == selected_measure].copy()

    if selected_regions:
        filtered = filtered[filtered['Council region'].isin(selected_regions)]

    filtered['Measure_Value'] = pd.to_numeric(filtered['Measure_Value'], errors='coerce')
    filtered = filtered.dropna(subset=['Measure_Value'])

    if selected_disagg:
        filtered = filtered[filtered['Disaggregation Level'] == selected_disagg]

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

    filtered = df[df['Measure Group Description'] == selected_measure]
    options = sorted(filtered['Disaggregation Level'].dropna().unique().tolist())
    return jsonify(options)

if __name__ == '__main__':
    app.run(debug=True)
