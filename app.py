from flask import Flask, render_template, request, jsonify
import pandas as pd
import requests
import os
from dotenv import load_dotenv
load_dotenv()

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
    measure_groups = sorted(df['Measure Group Description'].dropna().unique())
    regions = sorted(df['Council region'].dropna().unique())
    disaggregations = sorted(df['Disaggregation Level'].dropna().unique())
    councils = sorted(df['Geographical Description'].dropna().unique())
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

# Functions Jack added 10/05 - used by Council Summary Generator in index.html (currently commented out)

def generate_summary_for_council(council_name: str):
    selected_council_df = df[
        (df['Geographical Description'] == council_name) & 
        (df['Measure Type'] == 'Outcome')
    ].copy()

    national_df = df[
        (df['Geographical Description'] != council_name) & 
        (df['Measure Type'] == 'Outcome') & 
        (df['Geographical Level'] == 'Council')
    ].copy()

    # Ensure numeric values
    selected_council_df['Measure_Value'] = pd.to_numeric(selected_council_df['Measure_Value'], errors='coerce')
    national_df['Measure_Value'] = pd.to_numeric(national_df['Measure_Value'], errors='coerce')

    # Aggregate
    council_avg = (
        selected_council_df
        .groupby('Measure Group Description')['Measure_Value']
        .mean()
        .reset_index()
        .rename(columns={'Measure_Value': council_name})
    )

    national_avg = (
        national_df
        .groupby('Measure Group Description')['Measure_Value']
        .mean()
        .reset_index()
        .rename(columns={'Measure_Value': 'National_Avg'})
    )

    # Merge
    comparison_df = pd.merge(
        council_avg,
        national_avg,
        on='Measure Group Description',
        how='inner'
    )

    # Compare
    def compare(council, national):
        if pd.isna(council) or pd.isna(national):
            return "no data"
        diff_pct = (council - national) / national * 100
        if diff_pct > 5:
            return f"+{diff_pct:.1f}%"
        elif diff_pct < -5:
            return f"{diff_pct:.1f}%"
        else:
            return "Within 5%"

    comparison_df['Compared to National_Avg'] = comparison_df.apply(
        lambda row: compare(row[council_name], row['National_Avg']),
        axis=1
    )

    # print(comparison_df.to_string(index=False))

    return comparison_df

def generate_nlg_summary(comparison_df, council_name):
    # Calculate % difference first
    def pct_diff(row):
        try:
            return abs((row[council_name] - row['National_Avg']) / row['National_Avg']) * 100
        except:
            return 0

    comparison_df['Pct_Diff'] = comparison_df.apply(pct_diff, axis=1)

    # Now categorise
    above = comparison_df[comparison_df['Compared to National_Avg'].str.startswith('+')]
    below = comparison_df[comparison_df['Compared to National_Avg'].str.startswith('-')]
    approx = comparison_df[comparison_df['Compared to National_Avg'] == 'Within 5%']

    # Summary stats
    total = len(comparison_df)
    num_above = len(above)
    num_below = len(below)
    num_approx = len(approx)

    # Top 3 deltas
    top_strengths = above.sort_values(by='Pct_Diff', ascending=False).head(3)['Measure Group Description'].tolist()
    top_weaknesses = below.sort_values(by='Pct_Diff', ascending=False).head(3)['Measure Group Description'].tolist()

    def format_list(items):
        if len(items) == 0:
            return "none"
        if len(items) == 1:
            return items[0]
        return ", ".join(items[:-1]) + " and " + items[-1]

    # Final summary
    summary = (
        f"{council_name} has data available for {total} ASCOF outcome measures. "
        f"It performs above the national average in {num_above} measures, "
        f"about average in {num_approx}, and below average in {num_below}.\n\n"
    )

    if top_strengths:
        summary += f"Notable strengths include {format_list(top_strengths)}.\n"
    if top_weaknesses:
        summary += f"Areas for improvement include {format_list(top_weaknesses)}.\n"

    print("Performance Summary:")
    # print(summary)
    return summary

def generate_mistral_summary(comparison_df, council_name):
    # Create the prompt from comparison_df
    bullet_points = []
    for _, row in comparison_df.iterrows():
        label = row['Compared to National_Avg']
        bullet_points.append(
            f"- {row['Measure Group Description']}: {council_name} = {row[council_name]:.1f}, National Avg = {row['National_Avg']:.1f} ({label})"
        )

    prompt = f"""
Summarise this council's performance compared to the national average across ASCOF outcome measures.

Highlight the most clear strengths and weaknesses. Write it in a professional but casual and informative tone. The summary should be 2-3 sentences long in total.

Council: {council_name}

Comparison data:
{chr(10).join(bullet_points)}
"""

    # Call OpenRouter API
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",  # Store your key in .env or replace this line
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            { "role": "system", "content": "You are a social care consultant about to go into a meeting with a council client." },
            { "role": "user", "content": prompt }
        ],
        "temperature": 0.7
    }

    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        content = response.json()['choices'][0]['message']['content']
        print("\nSummary:\n")
        print(content)
        return content
    else:
        print("❌ Error:", response.status_code, response.text)
        return None
    
@app.route('/mistral-summary')
def mistral_summary_route():
    council = request.args.get('council')
    if not council:
        return jsonify({'error': 'Council not specified'}), 400

    comparison_df = generate_summary_for_council(council)
    summary = generate_mistral_summary(comparison_df, council)
    return jsonify({'summary': summary})

if __name__ == '__main__':
    # commparison_data = generate_summary_for_council("Kent")
    # generate_mistral_summary(commparison_data, "Kent")
    print('Hello world!')
    app.run(debug=True)
