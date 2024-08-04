from flask import Flask, render_template, jsonify, render_template_string, redirect, url_for
import requests
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta, timezone
import numpy as np
import urllib.request
import matplotlib.pyplot as plt
import io
import base64
import os

app = Flask(__name__)

with open("api.key", "r") as f:
    API_KEY = f.read()

with open("weather_api.key", "r") as f:
    data = f.readlines()
    WEATHER_KEY = data[0]
    postcode1, postcode2 = data[1].split(":")

def fetch_weather_forecast(filename="weather_forecast.csv"):
    """Get the 15-day weather forecast for Birmingham, UK return result as a dataframe with a datetime index"""
    base_dir = "/Users/chandler/Documents/Coding/EnergyDashboard/data"
    if os.path.exists(f"{base_dir}/{filename}"):
        file_mtime = datetime.fromtimestamp(os.path.getmtime(f"{base_dir}/{filename}"))
        if datetime.utcnow() - file_mtime < timedelta(days=1): # File made within the last day
            return pd.read_csv(f"{base_dir}/{filename}", index_col=["datetime"], parse_dates=["datetime"]).sort_index(ascending=True)

    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{postcode1}%20{postcode2}?unitGroup=metric&include=days&key={WEATHER_KEY}&contentType=csv"
    ResultBytes = urllib.request.urlopen(url)
    # Parse the results as CSV
    df = pd.read_csv(ResultBytes)
    df.drop(["name", "stations", "preciptype", "icon"], inplace=True, axis=1)
    df.set_index("datetime", inplace=True)
    df.sort_index(ascending=True, inplace=True) # Rows progress towards later dates
    df.to_csv(f"{base_dir}/{filename}")
    return df

def fetch_weather_data(filename="weather_data.csv"):
    # Default URL for if no current data exists
    today = datetime.now()
    start = (today - timedelta(days=31)).strftime("%Y-%m-%d")
    today = today.strftime("%Y-%m-%d")
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{postcode1}%20{postcode2}/{start}/{today}?unitGroup=metric&include=hours&key={WEATHER_KEY}&contentType=csv"

    base_dir = "/Users/chandler/Documents/Coding/EnergyDashboard/data"
    if os.path.exists(f"{base_dir}/{filename}"):
        file_mtime = datetime.fromtimestamp(os.path.getmtime(f"{base_dir}/{filename}"))
        if datetime.utcnow() - file_mtime < timedelta(days=1):
            return pd.read_csv(f"{base_dir}/{filename}", index_col=["datetime"], parse_dates=["datetime"]).sort_index(ascending=False)
        else:
            # File exists but is out-of-date get data from the last datetime to now and append to existing
            df = pd.read_csv(f"{base_dir}/{filename}", index_col=["datetime"], parse_dates=["datetime"]).sort_index(ascending=False)
            most_recent_date = datetime(df.index[0]).strftime("%Y-%m-%d")
            today = datetime.now().strftime("%Y-%m-%d")
            url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{postcode1}%20{postcode2}/{most_recent_date}/{today}?unitGroup=metric&include=hours&key={WEATHER_KEY}&contentType=csv"
        
    # TODO: Get data from the API instead -- url should be properly done
    ResultBytes = urllib.request.urlopen(url)
    # Parse the results as CSV
    df = pd.read_csv(ResultBytes).sort_index(ascending=False) # latest data is top of the dataframe
    df.drop(["name", "stations", "preciptype", "icon"], inplace=True, axis=1)
    df.set_index("datetime", inplace=True)
    df.to_csv(f"{base_dir}/{filename}")
    return df

def fetch_data(url):
    """Fetch data from the given URL with authentication."""
    response = requests.get(url, auth=(API_KEY, ''))
    response.raise_for_status()  # Raise an exception for HTTP errors
    return response.json()

def fetch_current_agile_standing_charge():
    url = "https://api.octopus.energy/v1/products/AGILE-24-04-03/electricity-tariffs/E-1R-AGILE-24-04-03-A/standing-charges/"
    data = fetch_data(url)
    return data['results'][0]['value_inc_vat']

def fetch_tariff_data(ndays=7):
    now = datetime.utcnow()
    start_date = (now - timedelta(days=ndays)).strftime('%Y-%m-%dT%H:%MZ')
    end_date = now.strftime('%Y-%m-%dT%H:%MZ')
    url = f"https://api.octopus.energy/v1/products/AGILE-24-04-03/electricity-tariffs/E-1R-AGILE-24-04-03-A/standard-unit-rates/?page_size=100&period_from={start_date}&period_to={end_date}&order_by=period"

    all_data = []
    while url:
        data = fetch_data(url)
        all_data.extend(data['results'])
        url = data.get('next')

    df = pd.DataFrame(all_data)
    df['valid_from'] = pd.to_datetime(df['valid_from'], utc=True)
    df['valid_to'] = pd.to_datetime(df['valid_to'], utc=True)
    return df
    
def fetch_usage_data(ndays=7, force_fetch=False):
    if not force_fetch and "consumption.csv" in os.listdir("data"):
        df = pd.read_csv("./data/consumption.csv", index_col=[0], parse_dates=['interval_start', 'interval_end'])
        df['interval_start'] = pd.to_datetime(df['interval_start'], utc=True)
        df['interval_end'] = pd.to_datetime(df['interval_end'], utc=True)
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        if (now - timedelta(days=1)) <= df['interval_start'].max():
            return df

    now = datetime.utcnow()
    start_date = (now - timedelta(days=ndays)).strftime('%Y-%m-%dT%H:%MZ')
    end_date = now.strftime('%Y-%m-%dT%H:%MZ')
    url = f"https://api.octopus.energy/v1/electricity-meter-points/1419872111009/meters/23J0205738/consumption/?page_size=100&period_from={start_date}&period_to={end_date}&order_by=period"

    all_data = []
    while url:
        data = fetch_data(url)
        all_data.extend(data['results'])
        url = data.get('next')

    df = pd.DataFrame(all_data)
    df['interval_start'] = pd.to_datetime(df['interval_start'], utc=True)
    df['interval_end'] = pd.to_datetime(df['interval_end'], utc=True)
    df.to_csv("./data/consumption.csv")
    return df

def process_usage_data(data):
    dates = data['interval_start'] + (data['interval_end'] - data['interval_start']) / 2
    usage = data['consumption']
    return dates, usage

def process_tariff_data(data):
    dates = data['valid_from'] + (data['valid_to'] - data['valid_from']) / 2
    usage = data['value_inc_vat']
    return dates, usage

def create_usage_plot(dates, usage):
    fig = px.line(x=dates, y=usage, title='Energy Usage Over Time', labels={'x': 'Date', 'y': 'Usage (kWh)'})
    fig.update_traces(line=dict(color='#de5cf0'))
    return fig.to_html()

def create_tariff_plot(dates, usage):
    fig = px.line(x=dates, y=usage, title='Agile Energy Price', labels={'x': 'Date', 'y': 'Price (p/kWh)'})
    fig.update_traces(line=dict(color='#de5cf0'))
    return fig.to_html()

def get_usage_for_period(data, days_ago_start, days_ago_end):
    today = datetime.utcnow().replace(tzinfo=timezone.utc)
    period_start = today - timedelta(days=days_ago_start)
    period_end = today - timedelta(days=days_ago_end)
    period_data = data[(data['interval_start'] > period_start) & (data['interval_start'] <= period_end)]
    return np.sum(period_data['consumption'])

def get_price_for_period(usage, tariff, days_ago_start, days_ago_end):
    today = datetime.utcnow().replace(tzinfo=timezone.utc)
    period_start = today - timedelta(days=days_ago_start)
    period_end = today - timedelta(days=days_ago_end)
    usage = usage[(usage['interval_start'] > period_start) & (usage['interval_start'] <= period_end)]
    tariff = tariff[(tariff['valid_from'] > period_start) & (tariff['valid_from'] <= period_end)]
    df = usage.join(tariff.set_index('valid_from'), on='interval_start', how='inner', rsuffix='_tariff').dropna()
    return np.sum(df['value_inc_vat'] * df['consumption']) / 100  # Convert to £

def get_tariff_charge():
    charges = fetch_data("https://api.octopus.energy/v1/products/VAR-22-11-01/electricity-tariffs/E-2R-VAR-22-11-01-E/standing-charges/")['results']
    latest_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=365)
    tariff_charge_value = 0
    for t in charges:
        if (t['payment_method'] == "DIRECT_DEBIT"):
            valid_from = pd.to_datetime(t['valid_from'], utc=True)
            if valid_from > latest_date:
                tariff_charge_value = t['value_inc_vat']
                latest_date = valid_from
    return tariff_charge_value

def get_tariff_rate():
    day_charges = fetch_data("https://api.octopus.energy/v1/products/VAR-22-11-01/electricity-tariffs/E-2R-VAR-22-11-01-E/day-unit-rates/")['results']
    night_charges = fetch_data("https://api.octopus.energy/v1/products/VAR-22-11-01/electricity-tariffs/E-2R-VAR-22-11-01-E/night-unit-rates/")['results']
    latest_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=365)
    tariff_day_rate_value, tariff_night_rate_value = 0, 0
    for t in day_charges:
        if (t['payment_method'] == "DIRECT_DEBIT"):
            valid_from = pd.to_datetime(t['valid_from'], utc=True)
            if valid_from > latest_date:
                tariff_day_rate_value = t['value_inc_vat']
                latest_date = valid_from
    latest_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=365)
    for t in night_charges:
        if (t['payment_method'] == "DIRECT_DEBIT"):
            valid_from = pd.to_datetime(t['valid_from'], utc=True)
            if valid_from > latest_date:
                tariff_night_rate_value = t['value_inc_vat']
                latest_date = valid_from
    return tariff_day_rate_value, tariff_night_rate_value

def get_windspeed_plot(df):
    today = pd.Timestamp('now').normalize()
    filtered_df = df[df.index.normalize() == today]

    fig, ax = plt.subplots(figsize=(8, 2))  # Adjust the figsize as needed
    
    # Plotting the windspeed data
    ax.plot(filtered_df.index.strftime('%H'), filtered_df['windspeed'], color='blue', linewidth=2)

    # Remove background, ticks, and labels
    ax.set_facecolor('none')
    ax.xaxis.set_visible(False)
    ax.yaxis.set_visible(False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)

    # Adjust the plot limits to avoid cropping
    ax.set_xlim(0, 23)
    ax.set_ylim(min(filtered_df['windspeed']) - 1, max(filtered_df['windspeed']) + 1)

    # Save the plot to a BytesIO object
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    
    # Encode the image to base64 for embedding in HTML
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf8')

    return image_base64

@app.route('/')
def index():
    return render_dashboard()

@app.route('/weather')
def weather():
    weather_data = fetch_weather_data() # pd.DataFrame (hourly)
    forecast_data = fetch_weather_forecast() # pd.DataFrame (daily)

    windspeed_plot = 0#get_windspeed_plot(weather_data)

    # Find the row whose timestamp is the closest (hourly)
    current_time = pd.Timestamp('now')
    time_diff = np.abs(weather_data.index - current_time)
    closest_index = time_diff.argmin()
    current_row = weather_data.iloc[closest_index]

    days_5_day_forecast = [forecast_data.iloc[i].name.strftime('%a') for i in range(1, 6)]
    temp_forecast = [f"{forecast_data.iloc[i].tempmax:.0f}" for i in range(1, 6)]

    return render_template(
        'weather.html',
        current_temp=f"{current_row['temp']:.1f}",
        feels_like=f"{current_row['feelslike']:.1f}",
        last_update_time=weather_data.iloc[0].name.strftime('%d/%m/%Y - %H:%M'),
        short_current_day=weather_data.iloc[0].name.strftime('%a'),
        days_forecast=days_5_day_forecast,
        temp_forecast=temp_forecast,
        windspeed_plot=windspeed_plot
    )

@app.route('/refresh', methods=['POST'])
def refresh_data():
    return render_dashboard(force_refresh=True)

def render_dashboard(force_refresh=False):
    tariff_data = fetch_tariff_data(14)
    usage_data = fetch_usage_data(14, force_fetch=force_refresh)
    
    if usage_data.empty:
        return "Error fetching data from the API"
    
    weather_data = fetch_weather_data().iloc[0] # Most recent row of data

    last_usage = get_usage_for_period(usage_data, 14, 7)
    this_usage = get_usage_for_period(usage_data, 7, 0)
    last_price = get_price_for_period(usage_data, tariff_data, 14, 7)
    this_price = get_price_for_period(usage_data, tariff_data, 7, 0)
    current_agile_price = tariff_data.sort_values("valid_from", ascending=False).iloc[0]['value_inc_vat']
    agile_charge = fetch_current_agile_standing_charge()

    usage_dates, usage_values = process_usage_data(usage_data)
    usage_plot = create_usage_plot(usage_dates, usage_values)
    tariff_dates, tariff_values = process_tariff_data(tariff_data)
    tariff_plot = create_tariff_plot(tariff_dates, tariff_values)
    tariff_charge = get_tariff_charge()
    tariff_rate_day, tariff_rate_night = get_tariff_rate()

    return render_template(
        'index.html', 
        usage_plot=usage_plot, 
        tariff_plot=tariff_plot,
        last_week_usage=f"{last_usage:.2f}", 
        this_week_usage=f"{this_usage:.2f}",
        this_price=f"{this_price:.2f}",
        last_price=f"{last_price:.2f}",
        current_agile_price=f"{current_agile_price:.1f}",
        agile_charge=f"{agile_charge:.1f}",
        tariff_charge=f"{tariff_charge:.1f}",
        tariff_rate_day=f"{tariff_rate_day:.1f}",
        tariff_rate_night=f"{tariff_rate_night:.1f}",
        last_temperature=f"{weather_data['temp']:.1f}",
        last_feelslike=f"{weather_data['feelslike']:.1f}",
        last_humidity=f"{weather_data['humidity']:.1f}",
        last_wind_speed=f"{weather_data['windspeed']:.1f}",
        last_windgust=f"{weather_data['windgust']:.1f}",
        last_precip=f"{weather_data['precip']:.1f}"
    )

if __name__ == '__main__':
    app.run(debug=True)
