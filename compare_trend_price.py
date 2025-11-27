#!/usr/bin/env python3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from pytrends.request import TrendReq
import requests
import json

# --- Configuration ---
NUM_DAYS = 365 # Past 1 year
# Set TODAY to midnight for consistent date handling across all data sources
TODAY_DT = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
# Calculate the exact start date for the past NUM_DAYS
START_DATE_DT = TODAY_DT - timedelta(days=NUM_DAYS - 1)

# Format for pytrends timeframe: "YYYY-MM-DD YYYY-MM-DD"
PYTRENDS_TIMEFRAME = f"{START_DATE_DT.strftime('%Y-%m-%d')} {TODAY_DT.strftime('%Y-%m-%d')}"

# For BLS, we'll calculate the start and end dates in YYYYMM format.
END_DATE_BLS = TODAY_DT.strftime('%Y%m')
START_DATE_BLS = (TODAY_DT - timedelta(days=NUM_DAYS)).strftime('%Y%m')

# BLS API Key (updated as per user request)
BLS_API_KEY = "4be5fe73fbf24f75b69f074f7530d492"

# Mapping of common price names to BLS series IDs
# These IDs are for Consumer Price Index (CPI) Average Price Data (APU0000)
# and are generally available for public access.
BLS_SERIES_MAP = {
    "egg": "APU0000708111",      # Eggs, grade A, large, per doz.
    "chicken": "APU0000704111",  # Chicken, fresh, whole, per lb. (Note: This is a common one, but BLS has many chicken-related series)
    "beef": "APU0000703111",     # Ground chuck, 100% beef, per lb. (Note: Many beef series exist, this is a common one)
    "milk": "APU0000709111",     # Milk, fresh, whole, fortified, per gal.
    "bread": "APU0000702111",    # Bread, white, pan, per lb.
    "gasoline": "APU000074714"   # Gasoline, unleaded regular, per gallon
}


# --- Fetch Google Trends Data ---
def get_google_trends_data(keyword, timeframe, geo='US'):
    """
    Fetches Google Trends 'Interest Over Time' data for a given keyword.
    Keyword: The search term (e.g., "avian").
    timeframe: The time period in "YYYY-MM-DD YYYY-MM-DD" format.
    geo: Geographic region (e.g., 'US' for United States).
    """
    print(f"Fetching Google Trends data for '{keyword}'...")
    pytrends = TrendReq(hl='en-US', tz=360) # hl: host language, tz: timezone offset
    kw_list = [keyword]
    try:
        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo, gprop='')
        df_trends = pytrends.interest_over_time()
        if not df_trends.empty:
            # Drop the 'isPartial' column
            df_trends = df_trends.drop(columns=['isPartial'])
            # Normalize the index to just dates (midnight)
            df_trends.index = df_trends.index.normalize()
            # Check if all values in the keyword column are NaN after fetching
            if df_trends[keyword].dropna().empty:
                print(f"Google Trends data for '{keyword}' fetched, but all values are NaN/zero.")
                return pd.DataFrame() # Return empty if no meaningful data
            print(f"Successfully fetched Google Trends data for '{keyword}'.")
            return df_trends
        else:
            print(f"No Google Trends data found for '{keyword}' in the specified timeframe/region.")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching Google Trends data for '{keyword}': {e}")
        return pd.DataFrame()

# --- Fetch BLS Data ---
def get_bls_data(series_id, start_yearmonth, end_yearmonth, api_key=""):
    """
    Fetches data from the BLS API for a given series ID and time range.
    series_id: The BLS series ID (e.g., 'APU0000708111').
    start_yearmonth: Start date in YYYYMM format.
    end_yearmonth: End date in YYYYMM format.
    api_key: Your BLS API key (optional for public series, but recommended).
    """
    print(f"Fetching BLS data for series '{series_id}' from {start_yearmonth} to {end_yearmonth}...")
    headers = {'Content-type': 'application/json'}
    data = json.dumps({
        "seriesid": [series_id],
        "startyear": start_yearmonth[:4],
        "endyear": end_yearmonth[:4],
        "catalog": False,
        "calculations": False,
        "annualaverage": False,
        "aspects": False,
        "registrationkey": api_key # Include API key if provided
    })
    url = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'

    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        json_data = json.loads(response.text)

        if json_data['status'] == 'REQUEST_SUCCEEDED':
            series_data = json_data['Results']['series'][0]['data']
            bls_df = pd.DataFrame(series_data)
            if not bls_df.empty:
                # Process BLS data
                bls_df['year'] = bls_df['year'].astype(str)
                bls_df['period'] = bls_df['period'].replace({'M01': '01', 'M02': '02', 'M03': '03', 'M04': '04',
                                                             'M05': '05', 'M06': '06', 'M07': '07', 'M08': '08',
                                                             'M09': '09', 'M10': '10', 'M11': '11', 'M12': '12'})
                bls_df['Date'] = pd.to_datetime(bls_df['year'] + '-' + bls_df['period'] + '-01')
                # Normalize the Date column to just dates (midnight)
                bls_df['Date'] = bls_df['Date'].dt.normalize()
                bls_df['value'] = pd.to_numeric(bls_df['value'])
                bls_df = bls_df.sort_values('Date').set_index('Date')['value']
                # Check if all values are NaN after processing
                if bls_df.dropna().empty:
                    print(f"BLS data for series '{series_id}' fetched, but all values are NaN/zero.")
                    return pd.Series(dtype='float64') # Return empty series if no meaningful data
                print(f"Successfully fetched BLS data for series '{series_id}'.")
                return bls_df
            else:
                print(f"No BLS data found for series '{series_id}' in the specified timeframe.")
                return pd.Series(dtype='float64')
        else:
            print(f"BLS API Error: {json_data.get('message', 'Unknown error')}")
            return pd.Series(dtype='float64')
    except requests.exceptions.RequestException as e:
        print(f"Error fetching BLS data: {e}")
        return pd.Series(dtype='float64')
    except Exception as e:
        print(f"An unexpected error occurred while processing BLS data: {e}")
        return pd.Series(dtype='float64')


# --- Main Data Fetching and Processing ---
def main():
    # Get user input for search keyword
    search_keyword = input("Enter the Google Trends search keyword (e.g., 'avian'): ")
    if not search_keyword:
        print("Search keyword cannot be empty. Exiting.")
        return

    # Get user input for BLS price name
    price_name_input = input(f"Enter a price name to compare (e.g., {', '.join(BLS_SERIES_MAP.keys())}): ").lower()
    bls_series_id = BLS_SERIES_MAP.get(price_name_input)

    if not bls_series_id:
        print(f"'{price_name_input}' is not a recognized price name. Please enter a valid name from the list or provide a BLS series ID if you know it.")
        bls_series_id = input("Enter the BLS series ID directly if you know it (e.g., 'APU0000708111'): ")
        if not bls_series_id:
            print("BLS series ID cannot be empty. Exiting.")
            return
        price_signal_name = price_name_input # Use the user's input as the name if they provide a custom ID
    else:
        price_signal_name = price_name_input.replace('_', ' ').title() + " Price" # Format for display


    # Get Google Trends data using the explicit timeframe and user keyword
    df_trends = get_google_trends_data(search_keyword, timeframe=PYTRENDS_TIMEFRAME)
    # Get BLS price data using user-provided series ID
    df_price = get_bls_data(bls_series_id, START_DATE_BLS, END_DATE_BLS, BLS_API_KEY)
    print(df_trends, df_price)
    # Create a full date range for the past year for merging, ensuring it's just dates (midnight)
    full_date_range = pd.date_range(start=START_DATE_DT, end=TODAY_DT, freq='D')
    df = pd.DataFrame(index=full_date_range)

    # Merge Search Frequency
    if not df_trends.empty:
        df_trends.index.name = 'Date'
        # Reindex df_trends to the full_date_range to ensure all dates are present
        df_trends_reindexed = df_trends.reindex(full_date_range)
        # Interpolate the reindexed weekly data to fill daily gaps
        df_trends_reindexed[search_keyword] = df_trends_reindexed[search_keyword].interpolate(method='linear')
        df[f'{search_keyword} Search Frequency'] = df_trends_reindexed[search_keyword]
    else:
        df[f'{search_keyword} Search Frequency'] = np.nan # Fill with NaN if data not available

    # Merge Price Signal
    if not df_price.empty:
        df_price.index.name = 'Date'
        # Reindex df_price (monthly) to the full_date_range
        df_price_reindexed = df_price.reindex(full_date_range)
        # Interpolate the reindexed monthly data to fill daily gaps
        df[price_signal_name] = df_price_reindexed.interpolate(method='linear')
    else:
        df[price_signal_name] = np.nan # Fill with NaN if data not available

    # Drop any rows where both values are NaN (e.g., if one data source is much shorter or entirely missing)
    df.dropna(subset=[f'{search_keyword} Search Frequency', price_signal_name], how='all', inplace=True)

    if df.empty:
        print("No common data points with valid data found after merging and cleaning. Cannot generate plot.")
        return

    # --- Plotting ---
    plt.figure(figsize=(14, 7)) # Set the figure size for better readability

    # Plot Search Frequency
    if f'{search_keyword} Search Frequency' in df.columns and not df[f'{search_keyword} Search Frequency'].dropna().empty:
        plt.plot(df.index, df[f'{search_keyword} Search Frequency'], label=f'{search_keyword} Search Frequency (Google Trends)', color='skyblue', linewidth=2)
    else:
        print(f"{search_keyword} Search Frequency data not available for plotting after cleaning.")

    # Plot Price Signal
    if price_signal_name in df.columns and not df[price_signal_name].dropna().empty:
        # Use a secondary y-axis for price if scales are vastly different
        ax2 = plt.gca().twinx()
        ax2.plot(df.index, df[price_signal_name], label=f'{price_signal_name} (BLS)', color='salmon', linewidth=2, linestyle='--')
        ax2.set_ylabel(f'{price_signal_name}', fontsize=12, color='salmon')
        ax2.tick_params(axis='y', labelcolor='salmon')
        ax2.legend(loc='upper right', fontsize=10)
    else:
        print(f"{price_signal_name} data not available for plotting after cleaning.")

    # Add title and labels for the primary y-axis (Search Frequency)
    plt.title(f'{search_keyword} Search Frequency vs. {price_signal_name} (Past 1 Year)', fontsize=16)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel(f'{search_keyword} Search Frequency (Relative Index)', fontsize=12, color='skyblue')
    plt.tick_params(axis='y', labelcolor='skyblue')


    # Add grid for better readability
    plt.grid(True, linestyle='--', alpha=0.7)

    # Format x-axis to show dates clearly
    plt.gcf().autofmt_xdate() # Auto-formats date labels to prevent overlap

    # Show the plot
    plt.tight_layout() # Adjust layout to prevent labels from overlapping
    plt.show()

    print("Plot generated successfully!")

if __name__ == "__main__":
    main()
