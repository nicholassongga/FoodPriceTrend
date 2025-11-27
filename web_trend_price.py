#!/usr/bin/env python3 -m streamlit run
# To run this application: python3 -m streamlit run web_single_keyword_price.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
from pytrends.request import TrendReq
from datetime import datetime, timedelta
import json # Import json for BLS API data handling
import io # Import io for CSV download
import time # Import time for sleep function

# --- Configuration ---
BLS_API_KEY = "4be5fe73fbf24f75b69f074f7530d492"

# Mapping of common price names to BLS series IDs and units
# These are Consumer Price Index (CPI) Average Price Data (APU0000)
# This map will be used as a suggestion/lookup, not a strict limit.
BLS_SERIES_MAP = {
    "egg": {"id": "APU0000708111", "unit": "USD/Dozen", "name": "Egg Price"},
    "chicken": {"id": "APU0000704111", "unit": "USD/lb", "name": "Chicken Price"},
    "beef": {"id": "APU0000703111", "unit": "USD/lb", "name": "Beef Price"},
    "milk": {"id": "APU0000709111", "unit": "USD/Gallon", "name": "Milk Price"},
    "bread": {"id": "APU0000702111", "unit": "USD/lb", "name": "Bread Price"},
    "gasoline": {"id": "APU000074714", "unit": "USD/Gallon", "name": "Gasoline Price"}
}

# --- BLS API Helper ---
def fetch_bls_data(series_id, start_year, end_year, api_key):
    """
    Fetches data from the BLS API for a given series ID and time range.
    """
    headers = {'Content-type': 'application/json'}
    data = {
        "seriesid": [series_id],
        "startyear": str(start_year),
        "endyear": str(end_year),
        "registrationKey": api_key
    }
    try:
        response = requests.post('https://api.bls.gov/publicAPI/v2/timeseries/data/', json=data, headers=headers)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        json_data = response.json()

        prices = []
        if json_data['status'] == 'REQUEST_SUCCEEDED' and json_data['Results']['series']:
            for entry in json_data['Results']['series'][0]['data']:
                period_map = {f'M{i:02d}': f'{i:02d}' for i in range(1, 13)}
                period_name = entry['period']
                if period_name in period_map:
                    date_str = f"{entry['year']}-{period_map[period_name]}-01"
                    prices.append({
                        "date": datetime.strptime(date_str, '%Y-%m-%d').date(), # Store as date object
                        "price": float(entry['value'])
                    })
            # Set 'date' as index here, so it's ready for reindexing later
            df = pd.DataFrame(prices).set_index('date').sort_index()
            return df['price'] # Return the Series with date as index
        else:
            st.warning(f"No BLS data found for series '{series_id}' or API request failed: {json_data.get('message', 'Unknown error')}")
            return pd.Series(dtype='float64') # Return empty Series
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching BLS data: {e}")
        return pd.Series(dtype='float64')
    except Exception as e:
        st.error(f"An unexpected error occurred while processing BLS data: {e}")
        return pd.Series(dtype='float64')

# --- Google Trends Helper ---
def fetch_google_trends(keyword, start_date_str, end_date_str, geo='US', max_retries=3, initial_delay=5):
    """
    Fetches Google Trends 'Interest Over Time' and 'Interest by Region' data with retry logic.
    Returns two DataFrames: one for time series and one for regional data.
    """
    pytrends = TrendReq(hl='en-US', tz=360)
    timeframe = f'{start_date_str} {end_date_str}'
    kw_list = [keyword]

    df_over_time = pd.DataFrame()
    regional_data = pd.DataFrame()

    for attempt in range(max_retries):
        try:
            # Fetch interest over time (for line plot)
            pytrends.build_payload(kw_list, timeframe=timeframe, geo=geo)
            df_over_time_raw = pytrends.interest_over_time()
            if not df_over_time_raw.empty:
                if 'isPartial' in df_over_time_raw.columns:
                    df_over_time_raw = df_over_time_raw.drop(columns=['isPartial'])
                df_over_time = df_over_time_raw.rename(columns={keyword: 'frequency'})
                df_over_time.index = df_over_time.index.normalize().date # Normalize index to date objects
            else:
                st.warning(f"No national Google Trends data found for '{keyword}'.")

            # Fetch interest by region (for map)
            pytrends.build_payload(kw_list, timeframe=timeframe, geo=geo)
            df_regional_raw = pytrends.interest_by_region(resolution='REGION', inc_low_vol=True, inc_geo_code=False)
            if not df_regional_raw.empty:
                regional_data = df_regional_raw[[keyword]].rename(columns={keyword: 'frequency'})
                regional_data.index.name = 'state_name' # Rename index for clarity
            else:
                st.warning(f"No regional Google Trends data found for '{keyword}'.")

            return df_over_time, regional_data # Success, exit function

        except requests.exceptions.RequestException as e:
            st.error(f"Network or API error fetching Google Trends data (Attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = initial_delay * (2 ** attempt) # Exponential backoff
                st.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                st.error("Max retries reached. Could not fetch Google Trends data.")
                return pd.DataFrame(), pd.DataFrame() # Return empty DataFrames after all retries fail
        except Exception as e:
            # Catch other unexpected errors
            st.error(f"An unexpected error occurred while fetching Google Trends data: {e}")
            return pd.DataFrame(), pd.DataFrame()

    return pd.DataFrame(), pd.DataFrame() # Should not be reached if max_retries is handled

# --- Streamlit UI ---
st.set_page_config(layout="wide")
st.title("Correlation between Keyword Trend and Food Price")

# Initialize session state for analysis flag and data
if 'run_analysis' not in st.session_state:
    st.session_state.run_analysis = False
if 'merged_df' not in st.session_state:
    st.session_state.merged_df = pd.DataFrame()
if 'regional_trends_df' not in st.session_state:
    st.session_state.regional_trends_df = pd.DataFrame()
if 'price_signal_name' not in st.session_state:
    st.session_state.price_signal_name = ""
if 'price_signal_unit' not in st.session_state:
    st.session_state.price_signal_unit = ""
if 'current_keyword' not in st.session_state:
    st.session_state.current_keyword = "avian"
if 'current_item_input' not in st.session_state:
    st.session_state.current_item_input = "egg"
if 'current_start_date' not in st.session_state:
    st.session_state.current_start_date = datetime(2024, 7, 1).date()
if 'current_end_date' not in st.session_state:
    st.session_state.current_end_date = datetime.now().date()


with st.sidebar:
    st.header("Input Parameters")
    keyword_input = st.text_input("Google Trends Keyword", value=st.session_state.current_keyword, help="Enter the keyword to search on Google Trends.")

    item_input_sidebar = st.text_input(
        "Consumer Item Name",
        value=st.session_state.current_item_input,
        help=f"Enter the name of the consumer item (e.g., 'egg', 'chicken', 'beef'). "
             f"Known items: {', '.join(BLS_SERIES_MAP.keys())}. "
             f"If not found, you'll be prompted to enter a BLS Series ID."
    )

    start_date_sidebar = st.date_input("Start Date", value=st.session_state.current_start_date)
    end_date_sidebar = st.date_input("End Date", value=st.session_state.current_end_date)

    if st.button("Analyze Data"):
        st.session_state.run_analysis = True
        st.session_state.current_keyword = keyword_input
        st.session_state.current_item_input = item_input_sidebar
        st.session_state.current_start_date = start_date_sidebar
        st.session_state.current_end_date = end_date_sidebar

        # Perform analysis and store results in session state
        selected_bls_item = BLS_SERIES_MAP.get(st.session_state.current_item_input.lower())
        bls_series_id = None
        st.session_state.price_signal_name = st.session_state.current_item_input.title() + " Price"
        st.session_state.price_signal_unit = "Units"

        if selected_bls_item:
            bls_series_id = selected_bls_item["id"]
            st.session_state.price_signal_name = selected_bls_item["name"]
            st.session_state.price_signal_unit = selected_bls_item["unit"]
        else:
            st.warning(f"'{st.session_state.current_item_input}' is not a recognized common item. "
                       f"Attempting to fetch data with this as a generic item. "
                       f"If this fails, please try a recognized item or manually enter a BLS Series ID.")
            manual_bls_series_id = st.text_input(
                "Enter BLS Series ID (if item not recognized)",
                value="",
                help="If your item is not listed, you can manually enter a BLS Series ID here. "
                     "Example for Eggs: APU0000708111. You can find more IDs on the BLS website."
            )
            if manual_bls_series_id:
                bls_series_id = manual_bls_series_id
                st.session_state.price_signal_name = st.session_state.current_item_input.title() + " Price"
                st.session_state.price_signal_unit = "Units"
            else:
                st.error("Please enter a recognized item name or a valid BLS Series ID to proceed.")
                st.session_state.run_analysis = False # Stop analysis if no ID
                # st.stop() # Removed st.stop() to allow the script to continue and display the error message

        if not bls_series_id:
            st.error("Could not determine BLS Series ID. Please provide a valid item name or Series ID.")
            st.session_state.run_analysis = False # Stop analysis if no ID
            # st.stop() # Removed st.stop()
        
        # Only proceed with data fetching if bls_series_id is determined
        if st.session_state.run_analysis and bls_series_id:
            with st.spinner("Fetching and processing data..."):
                trend_df, regional_trends_df = fetch_google_trends(st.session_state.current_keyword, st.session_state.current_start_date.strftime('%Y-%m-%d'), st.session_state.current_end_date.strftime('%Y-%m-%d'))
                bls_df_series = fetch_bls_data(bls_series_id, st.session_state.current_start_date.year, st.session_state.current_end_date.year, BLS_API_KEY)

                full_date_range = pd.to_datetime(pd.date_range(start=st.session_state.current_start_date, end=st.session_state.current_end_date, freq='D')).date
                df = pd.DataFrame(index=full_date_range)

                if not trend_df.empty:
                    df_trends_reindexed = trend_df.reindex(full_date_range)
                    df_trends_reindexed['frequency'] = df_trends_reindexed['frequency'].interpolate(method='linear')
                    df[f'{st.session_state.current_keyword.title()} Search Frequency'] = df_trends_reindexed['frequency']
                else:
                    df[f'{st.session_state.current_keyword.title()} Search Frequency'] = np.nan

                if not bls_df_series.empty:
                    df_price_reindexed = bls_df_series.reindex(full_date_range)
                    df[st.session_state.price_signal_name] = df_price_reindexed.interpolate(method='linear')
                else:
                    df[st.session_state.price_signal_name] = np.nan

                df.dropna(subset=[f'{st.session_state.current_keyword.title()} Search Frequency', st.session_state.price_signal_name], how='all', inplace=True)

                if df.empty:
                    st.error("No common data points with valid data found for the selected period. Cannot generate plots.")
                    st.session_state.run_analysis = False
                else:
                    st.session_state.merged_df = df.reset_index().rename(columns={'index': 'date'})
                    st.session_state.regional_trends_df = regional_trends_df
            # Removed st.rerun() here. Streamlit will naturally rerun after button click.


# --- Display Results ---
if st.session_state.run_analysis:
    # --- Map Display ---
    st.subheader("Regional Search Frequency Map (US States)")
    st.caption("Google Trends regional data is an average over the selected period, not daily. Therefore, the map's colors represent the overall average frequency for each state during the selected date range and do not change with a time slider.")

    if not st.session_state.regional_trends_df.empty:
        try:
            geojson_url = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"
            response = requests.get(geojson_url)
            response.raise_for_status()
            us_states_geojson = response.json()

            regional_trends_df_for_map = st.session_state.regional_trends_df.reset_index()
            regional_trends_df_for_map.rename(columns={'state_name': 'name'}, inplace=True)

            map_fig = px.choropleth_mapbox(
                regional_trends_df_for_map,
                geojson=us_states_geojson,
                locations='name',
                featureidkey="properties.name",
                color='frequency',
                color_continuous_scale="Viridis",
                range_color=(0, regional_trends_df_for_map['frequency'].max()),
                mapbox_style="carto-positron",
                zoom=3, center={"lat": 37.0902, "lon": -95.7129},
                opacity=0.7,
                labels={'frequency': f'{st.session_state.current_keyword.title()} Search Frequency'}
            )
            map_fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(map_fig, use_container_width=True, config={'scrollZoom': True})
        except Exception as e:
            st.error(f"Could not load or display map: {e}. Please check your internet connection or the GeoJSON URL.")
    else:
        st.info("No regional search frequency data available to display on the map.")

    # --- Line Plot ---
    st.subheader("Search Frequency vs. Item Price Over Time")

    if not st.session_state.merged_df.empty:
        fig_line = go.Figure()

        # Add Search Frequency Trace
        fig_line.add_trace(go.Scatter(
            x=st.session_state.merged_df['date'],
            y=st.session_state.merged_df[f'{st.session_state.current_keyword.title()} Search Frequency'],
            name=f"{st.session_state.current_keyword.title()} Search Frequency",
            mode='lines',
            line=dict(color='skyblue'),
            yaxis="y1"
        ))

        # Add Price Signal Trace
        fig_line.add_trace(go.Scatter(
            x=st.session_state.merged_df['date'],
            y=st.session_state.merged_df[st.session_state.price_signal_name],
            name=st.session_state.price_signal_name,
            mode='lines',
            line=dict(color='salmon', dash='dash'),
            yaxis="y2"
        ))

        fig_line.update_layout(
            title_text=f"{st.session_state.current_keyword.title()} Search Frequency vs. {st.session_state.current_item_input.title()} Price",
            xaxis_title="Date",
            yaxis=dict(
                title=f"Search Frequency (Google Trends)",
                side="left",
                showgrid=True,
                zeroline=True,
                title_font=dict(color='skyblue'),
                tickfont=dict(color='skyblue')
            ),
            yaxis2=dict(
                title=f"{st.session_state.price_signal_name} ({st.session_state.price_signal_unit})",
                overlaying="y",
                side="right",
                showgrid=False,
                zeroline=False,
                title_font=dict(color='salmon'),
                tickfont=dict(color='salmon')
            ),
            legend=dict(x=0.01, y=0.99),
            hovermode="x unified",
            height=450,
        )

        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("No time series data available for plotting.")

    # --- Data Table ---
    st.subheader("Raw Data Table")
    if not st.session_state.merged_df.empty:
        display_df = st.session_state.merged_df[['date', f'{st.session_state.current_keyword.title()} Search Frequency', st.session_state.price_signal_name]].copy()
        display_df['date'] = display_df['date'].astype(str)
        st.dataframe(display_df, height=300)

        csv_data = display_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Data as CSV",
            data=csv_data,
            file_name=f"{st.session_state.current_keyword}_vs_{st.session_state.current_item_input}_price_data.csv",
            mime="text/csv",
            help="Click to download the displayed table data as a CSV file."
        )
    else:
        st.info("No data available for table display.")
