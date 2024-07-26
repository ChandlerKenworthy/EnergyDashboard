from flask import Flask, render_template, jsonify, render_template_string
import requests
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta, timezone
import numpy as np
import os

with open("api.key", "r") as f:
    API_KEY = f.read()

def fetch_current_agile_standing_charge():
    url = f"https://api.octopus.energy/v1/products/AGILE-24-04-03/electricity-tariffs/E-1R-AGILE-24-04-03-A/standing-charges/"

    response = requests.get(url, auth=(API_KEY, ''))
    if response.status_code == 200:
        json_response = response.json()
        return json_response['results'][0]['value_inc_vat']

def fetch_tarriff_data(ndays=7):
    # Calculate the current date and the date one week ago
    now = datetime.utcnow()
    one_week_ago = now - timedelta(days=ndays)
    
    # Format dates to the required format
    period_from = one_week_ago.strftime('%Y-%m-%dT%H:%MZ')
    period_to = now.strftime('%Y-%m-%dT%H:%MZ')

    url = f"https://api.octopus.energy/v1/products/AGILE-24-04-03/electricity-tariffs/E-1R-AGILE-24-04-03-A/standard-unit-rates/?page_size=100&period_from={period_from}&period_to={period_to}&order_by=period"
    response = requests.get(url, auth=(API_KEY, ''))
    if response.status_code == 200:
        # Build dataframe
        json_response = response.json()
        data = pd.DataFrame(columns=["value_inc_vat", "valid_from", "valid_to"])
        viv, vf, vt = [], [], []
        for entry in json_response['results']:
            viv.append(entry['value_inc_vat'])
            vf.append(entry['valid_from'])
            vt.append(entry['valid_to'])

        while json_response['next']:
            response = requests.get(json_response['next'], auth=(API_KEY, ''))
            if response.status_code != 200:
                break
            json_response = response.json()
            for entry in json_response['results']:
                viv.append(entry['value_inc_vat'])
                vf.append(entry['valid_from'])
                vt.append(entry['valid_to'])

        data['value_inc_vat'] = viv
        data['valid_from'] = pd.to_datetime(vf, utc=True)
        data['valid_to'] = pd.to_datetime(vt, utc=True)
        return data
    else:
        return None
    
def fetch_usage_data(ndays=7, force_fetch=False):    
    # Check to see if data already exists, if it does don't re-send the request
    if ("consumption.csv" in os.listdir("data")) and not force_fetch:
        df = pd.read_csv("./data/consumption.csv", index_col=[0], parse_dates=['interval_start', 'interval_end'])
        df['interval_start'] = pd.to_datetime(df['interval_start'], utc=True)
        df['interval_end'] = pd.to_datetime(df['interval_end'], utc=True)
        
        # Convert datetime.utcnow() to an offset-aware datetime in UTC
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        # If the data is more than 1 day out of date go and fetch new data
        if (now - timedelta(days=1)) > (df['interval_start'].sort_values().iloc[-1]):
            pass
        else:
            return df 

    # Calculate the current date and the date one week ago
    now = datetime.utcnow()
    one_week_ago = now - timedelta(days=ndays)
    
    # Format dates to the required format
    period_from = one_week_ago.strftime('%Y-%m-%dT%H:%MZ')
    period_to = now.strftime('%Y-%m-%dT%H:%MZ')

    # Define endpoint
    url = f"https://api.octopus.energy/v1/electricity-meter-points/1419872111009/meters/23J0205738/consumption/?page_size=100&period_from={period_from}&period_to={period_to}&order_by=period"

    response = requests.get(url, auth=(API_KEY, ''))
    if response.status_code == 200:
        # Port to a nicer dataframe format
        results = response.json()
        data = pd.DataFrame(columns=["consumption", "interval_start", "interval_end"])
        consumption, interval_start, interval_end = [], [], []

        # Only returns 100 data points at a time need to iterate to grab all in the time period
        while results['next']:
            response = requests.get(results['next'], auth=(API_KEY, ''))
            if response.status_code == 200:
                results = response.json()
                for entry in results['results']:
                    consumption.append(entry['consumption'])
                    interval_start.append(entry['interval_start'])
                    interval_end.append(entry['interval_end'])
            else:
                break

        data['consumption'] = consumption
        data['interval_start'] = pd.to_datetime(interval_start, utc=True)
        data['interval_end'] = pd.to_datetime(interval_end, utc=True)

        # Write to file
        data.to_csv("./data/consumption.csv")

        return data
    else:
        return None

def process_usage_data(data):
    # Midpoint of the 30min recording period
    dates = data['interval_start'] + (data['interval_end'] - data['interval_start']) / 2
    usage = data['consumption']
    return dates, usage

def process_tariff_data(data):
    # Midpoint of the 30min recording period
    dates = data['valid_from'] + (data['valid_to'] - data['valid_from']) / 2
    usage = data['value_inc_vat']
    return dates, usage

def create_usage_plot(dates, usage):
    fig = px.line(x=dates, y=usage, title='Energy Usage Over Time', labels={'x': 'Date', 'y': 'Usage (kWh)'})
    return fig.to_html()

def create_tariff_plot(dates, usage):
    fig = px.line(x=dates, y=usage, title='Agile Energy Price', labels={'x': 'Date', 'y': 'Price (p/kWh)'})
    return fig.to_html()

def get_usage_last_week(data):
    today = datetime.utcnow().replace(tzinfo=timezone.utc)
    week_start = today - timedelta(days=14)
    week_end = today - timedelta(days=7)

    data = data[np.logical_and(
        data['interval_start'] > week_start,
        data['interval_start'] < week_end
    )]
    return f"{np.sum(data['consumption']):.2f}"

def get_usage_this_week(data):
    today = datetime.utcnow().replace(tzinfo=timezone.utc)
    week_start = today - timedelta(days=7)
    data = data[data['interval_start'] > week_start]
    return f"{np.sum(data['consumption']):.2f}"

def get_price_this_week(usage, tariff):
    # Calculates an approximate expenditure in GBP (inc. VAT) based on last weeks
    # consumption and agile prices
    today = datetime.utcnow().replace(tzinfo=timezone.utc)
    week_start = today - timedelta(days=7)
    usage = usage[usage['interval_start'] > week_start]
    tariff = tariff[tariff['valid_from'] > week_start]
    df = usage.join(tariff, how='outer').dropna(axis=0)
    return np.sum(df['value_inc_vat'] * df['consumption']) / 100 # Convert to £'s

def get_price_last_week(usage, tariff):
    # Calculates an approximate expenditure in GBP (inc. VAT) based on last weeks
    # consumption and agile prices
    today = datetime.utcnow().replace(tzinfo=timezone.utc)
    week_start = today - timedelta(days=14)
    week_end = today - timedelta(days=7)
    usage = usage[np.logical_and(usage['interval_start'] > week_start, usage['interval_start'] < week_end)]
    tariff = tariff[np.logical_and(tariff['valid_from'] > week_start, tariff['valid_from'] < week_end)]
    df = usage.join(tariff, how='outer').dropna(axis=0)
    return np.sum(df['value_inc_vat'] * df['consumption']) / 100 # Convert to £'s

app = Flask(__name__)

@app.route('/')
def index():
    tariff_data = fetch_tarriff_data(14)
    usage_data = fetch_usage_data(14, force_fetch=False)
    last_usage = get_usage_last_week(usage_data)
    this_usage = get_usage_this_week(usage_data)
    last_price = get_price_last_week(usage_data, tariff_data)
    this_price = get_price_this_week(usage_data, tariff_data)
    agile_price = tariff_data.sort_values("valid_from", ascending=False).iloc[0]['value_inc_vat']
    agile_charge = fetch_current_agile_standing_charge()

    if usage_data.empty:
        return "Error fetching data from the API"

    usage_dates, usage_values = process_usage_data(usage_data)
    usage_plot = create_usage_plot(usage_dates, usage_values)
    tariff_dates, tariff_values = process_tariff_data(tariff_data)
    tariff_plot = create_tariff_plot(tariff_dates, tariff_values)

    return render_template(
        'index.html', 
        usage_plot=usage_plot, 
        tariff_plot=tariff_plot,
        last_week_usage=last_usage, 
        this_week_usage=this_usage,
        this_price=f"{this_price:.2f}",
        last_price=f"{last_price:.2f}",
        current_agile_price=f"{agile_price:.1f}",
        agile_charge=f"{agile_charge:.1f}"
    )

if __name__ == '__main__':
    app.run(debug=True)
