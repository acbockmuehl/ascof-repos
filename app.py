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
population_raw = pd.read_csv("data/ons_population_data.csv")

measures_df = pd.read_csv('data/measures.csv')
ons_df = pd.read_csv('data/ons_codes.csv')
direction_df = pd.read_csv('data/measure_direction.csv')  # contains 'Measure Group Description', 'Direction'
df_trend_full = pd.read_csv('data/trend_data.csv')  # trend data 2017–2024
population_raw = pd.read_csv("data/ons_population_data.csv")

# === Preprocess Population Data ===
population_raw['AREA_CODE'] = population_raw['AREA_CODE'].astype(str).str.strip()

# Ensure 'SEX' column exists and 'persons' is the correct value for total population by age band
if 'SEX' in population_raw.columns:
    population_raw = population_raw[population_raw["SEX"] == "persons"]

# Filter out 'All ages' as it's not a specific band for our age group calculations
population_raw = population_raw[population_raw['AGE_GROUP'] != 'All ages']

population_raw["2025"] = pd.to_numeric(population_raw["2025"], errors='coerce').fillna(0)

def get_min_age_from_ons_band(band_str):
    band_str = str(band_str).strip()
    if "and over" in band_str: # Handles "90 and over"
        return int(band_str.split(' ')[0])
    try:
        return int(band_str)
    except ValueError:
        return -1 # Indicates an unparsable or irrelevant band

population_raw['MinAge'] = population_raw['AGE_GROUP'].apply(get_min_age_from_ons_band)

# Population for 18-64: Sum ONS bands where min_age is between 18 and 64.
# The current get_min_age_from_ons_band is a simplification.
# A truly accurate solution might require disaggregating ONS population data to single years of age first.
# For now, we proceed with the min_age logic, assuming it's a reasonable proxy or ONS bands align well.

pop_18_64_df = population_raw[
    (population_raw['MinAge'] >= 18) & (population_raw['MinAge'] <= 64)
].groupby('AREA_CODE')['2025'].sum().reset_index().rename(
    columns={'AREA_CODE': 'GEOGRAPHY_CODE', '2025': 'Population_18_64'}
)

pop_65_plus_df = population_raw[
    population_raw['MinAge'] >= 65
].groupby('AREA_CODE')['2025'].sum().reset_index().rename(
    columns={'AREA_CODE': 'GEOGRAPHY_CODE', '2025': 'Population_65_plus'}
)

pop_total_adults_df = population_raw[
    population_raw['MinAge'] >= 18
].groupby('AREA_CODE')['2025'].sum().reset_index().rename(
    columns={'AREA_CODE': 'GEOGRAPHY_CODE', '2025': 'Population_Total_Adults'}
)

population_prepared_df = pop_total_adults_df.merge(
    pop_18_64_df, on='GEOGRAPHY_CODE', how='outer'
).merge(
    pop_65_plus_df, on='GEOGRAPHY_CODE', how='outer'
).fillna(0)

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
cost_df['GEOGRAPHY_CODE'] = cost_df['GEOGRAPHY_CODE'].astype(str).str.strip()
cost_df['ITEMVALUE'] = pd.to_numeric(cost_df['ITEMVALUE'], errors='coerce')
cost_df['ITEMVALUE'] = cost_df['ITEMVALUE'].apply(lambda x: x if x >= 0 else np.nan)

def calculate_per_100k(df_to_calculate, population_source_df, age_groups_list, 
                       item_value_col='ITEMVALUE', geo_code_col='GEOGRAPHY_CODE'):
    """
    Calculates 'per 100k' population for item_value_col in df_to_calculate.
    Assumes df_to_calculate has one row per geography for the period being calculated.
    """
    if df_to_calculate.empty:
        # Ensure ITEMVALUE column exists even if empty, to prevent downstream errors
        if item_value_col not in df_to_calculate.columns:
             df_to_calculate[item_value_col] = pd.Series(dtype='float64')
        return df_to_calculate

    merged_df = df_to_calculate.merge(population_source_df, on=geo_code_col, how='left')

    # Initialize Population_to_use with NaN, to be filled based on age_groups_list
    merged_df['Population_to_use'] = np.nan

    if not age_groups_list:  # No specific age group filter from request (e.g. "Total" costs)
        merged_df['Population_to_use'] = merged_df['Population_Total_Adults']
    elif len(age_groups_list) == 1:
        if age_groups_list[0] == "18 to 64":
            merged_df['Population_to_use'] = merged_df['Population_18_64']
        elif age_groups_list[0] == "65 and over":
            merged_df['Population_to_use'] = merged_df['Population_65_plus']
        else: # Fallback if a single, unexpected age group is passed
            merged_df['Population_to_use'] = merged_df['Population_Total_Adults']
    elif set(age_groups_list) == {"18 to 64", "65 and over"}: # Both standard adult groups selected
        # Costs are summed for both, so population is sum of both (i.e., total adults)
        merged_df['Population_to_use'] = merged_df['Population_Total_Adults']
    else: # Multiple age groups, but not the standard combined adult set, or unexpected values
          # This case implies the cost data was filtered by these specific multiple age_groups.
          # For simplicity, if it's not a recognized single or combined group, default to Total_Adults.
          # A more granular approach would require summing specific population bands if they were pre-calculated.
        merged_df['Population_to_use'] = merged_df['Population_Total_Adults']

    # Ensure population columns used for calculation exist and fill NaNs from merge if any LA was missing population data
    for pop_col in ['Population_Total_Adults', 'Population_18_64', 'Population_65_plus', 'Population_to_use']:
        if pop_col in merged_df.columns:
            merged_df[pop_col] = merged_df[pop_col].fillna(0)

    merged_df[item_value_col] = merged_df[item_value_col] / (merged_df['Population_to_use'].replace(0, np.nan) / 100000.0)
    merged_df[item_value_col].replace([np.inf, -np.inf], np.nan, inplace=True)
    return merged_df

@app.route('/cost-data')
def cost_data():
    # Get filters
    selected_la = request.args.get('la')
    region = request.args.get('region')
    age_groups = request.args.getlist('age_groups[]')
    setting = request.args.get('support_setting', 'Total')
    reason = request.args.get('primary_support_reason', 'Total')
    display_mode = request.args.get('display_mode', 'total')  # 'total' or 'per_100k'

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
        benchmark_df.groupby(['DH_GEOGRAPHY_NAME', 'GEOGRAPHY_CODE'], as_index=False)['ITEMVALUE']
        .sum()
        .dropna(subset=['ITEMVALUE']) 
        .sort_values(by='ITEMVALUE', ascending=False)
    )

    if display_mode == 'per_100k':
        benchmark_data = calculate_per_100k(benchmark_data, population_prepared_df, age_groups, item_value_col='ITEMVALUE', geo_code_col='GEOGRAPHY_CODE')
        # Re-sort after per 100k calculation to maintain Pareto order
        benchmark_data.sort_values(by='ITEMVALUE', ascending=False, inplace=True)

    benchmark = [
        {'Geographical Description': row['DH_GEOGRAPHY_NAME'], 'Measure_Value': round(row['ITEMVALUE'], 2) if pd.notna(row['ITEMVALUE']) else None}
        for _, row in benchmark_data.iterrows()
    ]

    # === Build trend lines ===
    base_trend_df = df.copy()
    if age_groups:
        base_trend_df = base_trend_df[base_trend_df['AgeBand'].isin(age_groups)]
    if setting:
        base_trend_df = base_trend_df[base_trend_df['SupportSetting'] == setting]
    if reason:
        base_trend_df = base_trend_df[base_trend_df['PrimarySupportReason'] == reason]

    # --- England Average Trend ---
    england_las_trend_base = base_trend_df[base_trend_df['GEOGRAPHY_LEVEL'] == 'Local Authority'].copy()
    # Sum ITEMVALUE per LA per Year
    england_la_yearly_sum = england_las_trend_base.groupby(['FY_ENDING', 'GEOGRAPHY_CODE', 'DH_GEOGRAPHY_NAME'])['ITEMVALUE'].sum().reset_index()
    if display_mode == 'per_100k':
               england_la_yearly_sum = calculate_per_100k(england_la_yearly_sum, population_prepared_df, age_groups, 
                                                   item_value_col='ITEMVALUE', geo_code_col='GEOGRAPHY_CODE')

    england_avg_trend = england_la_yearly_sum.groupby('FY_ENDING')['ITEMVALUE'].mean().reset_index()
    england_avg_trend.rename(columns={'FY_ENDING': 'Year', 'ITEMVALUE': 'Measure_Value'}, inplace=True)
    england_avg_trend['Measure_Value'] = england_avg_trend['Measure_Value'].round(2)
    england_avg = england_avg_trend.to_dict(orient='records')

    # --- LA Trend ---
    la_trend_data = []
    if selected_la:
        la_df_abs = base_trend_df[base_trend_df['DH_GEOGRAPHY_NAME'] == selected_la].copy()
        la_yearly_sum = la_df_abs.groupby(['FY_ENDING', 'GEOGRAPHY_CODE'])['ITEMVALUE'].sum().reset_index()

        if display_mode == 'per_100k':
            la_yearly_sum = calculate_per_100k(la_yearly_sum, population_prepared_df, age_groups, 
                                               item_value_col='ITEMVALUE', geo_code_col='GEOGRAPHY_CODE')
        
        la_yearly_sum.rename(columns={'FY_ENDING': 'Year', 'ITEMVALUE': 'Measure_Value'}, inplace=True)
        la_yearly_sum['Measure_Value'] = la_yearly_sum['Measure_Value'].round(2)
        la_trend_data = la_yearly_sum[['Year', 'Measure_Value']].to_dict(orient='records')

    # --- Region Trend ---
    region_trend_data = []
    # Determine region_name based on selected_la (if provided) or selected_region (if provided directly)
    # This part of logic for finding region_name and region_las needs to be robust
    # For this example, we'll assume selected_la implies the region.
    # If 'region' is a direct filter from request.args.get('region'), that should be used.
    # The current code derives region from selected_la if selected_la is present.

    actual_region_name = None
    if selected_la:
        # Find region name of selected LA from df_outcomes (which has 'Council region')
        la_info = df_outcomes[df_outcomes['Geographical Description'].str.strip().str.lower() == selected_la.strip().lower()]
        if not la_info.empty and 'Council region' in la_info.columns:
            actual_region_name = la_info['Council region'].dropna().unique()
            if len(actual_region_name) > 0:
                actual_region_name = actual_region_name[0]
            else:
                actual_region_name = None
    elif request.args.get('region'): # if region is passed as a direct filter
        actual_region_name = request.args.get('region').strip()

    if actual_region_name:
        # Get list of LAs in the determined region from cost_df's GEOGRAPHY_NAME (assuming it's region name)
        # or from a mapping if GEOGRAPHY_NAME in cost_df is not region name.
        # The original code used df_outcomes to find LAs in a region, which is better.
        region_las_geo_desc = df_outcomes[
            df_outcomes['Council region'] == actual_region_name
        ]['Geographical Description'].unique()

        region_df_abs = base_trend_df[base_trend_df['DH_GEOGRAPHY_NAME'].isin(region_las_geo_desc)].copy()
        
        if not region_df_abs.empty:
            region_la_yearly_sum = region_df_abs.groupby(['FY_ENDING', 'GEOGRAPHY_CODE', 'DH_GEOGRAPHY_NAME'])['ITEMVALUE'].sum().reset_index()

            if display_mode == 'per_100k':
                region_la_yearly_sum = calculate_per_100k(region_la_yearly_sum, population_prepared_df, age_groups,
                                                          item_value_col='ITEMVALUE', geo_code_col='GEOGRAPHY_CODE')
            
            region_avg_trend = region_la_yearly_sum.groupby('FY_ENDING')['ITEMVALUE'].mean().reset_index()
            region_avg_trend.rename(columns={'FY_ENDING': 'Year', 'ITEMVALUE': 'Measure_Value'}, inplace=True)
            region_avg_trend['Measure_Value'] = region_avg_trend['Measure_Value'].round(2)
            region_trend_data = region_avg_trend.to_dict(orient='records')


    print(f"FILTERED LA: {selected_la} | AGE_GROUPS: {age_groups} | DISPLAY_MODE: {display_mode}")
    print(f"Benchmark LAs: {len(benchmark)}, England Trend Points: {len(england_avg)}, LA Trend Points: {len(la_trend_data)}, Region Trend Points: {len(region_trend_data)}")

    return jsonify({
        'benchmark': benchmark,
        'england': england_avg,
        'region': region_trend_data,
        'la': la_trend_data
    })

    
# === Run the app ===
if __name__ == '__main__':
    app.run(debug=True)