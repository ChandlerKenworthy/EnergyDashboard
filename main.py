import requests
import json
from datetime import datetime, timedelta

url = now = datetime.utcnow()
one_week_ago = now - timedelta(days=7)

# Format dates to the required format
period_from = one_week_ago.strftime('%Y-%m-%dT%H:%MZ')
period_to = now.strftime('%Y-%m-%dT%H:%MZ')

url = f"https://api.octopus.energy/v1/products/AGILE-24-04-03/electricity-tariffs/E-1R-AGILE-24-04-03-A/standing-charges/"


with open("api.key", "r") as f:
    API_KEY = f.read()
#url = "https://api.octopus.energy/v1/accounts/A-50183C21/"

response = requests.get(url, auth=(API_KEY, ''))
if response.status_code == 200:
    print(response.json())

"""
def fetch_usage_data():    
    # Calculate the current date and the date one week ago
    now = datetime.utcnow()
    one_week_ago = now - timedelta(days=7)
    
    # Format dates to the required format
    period_from = one_week_ago.strftime('%Y-%m-%dT%H:%MZ')
    period_to = now.strftime('%Y-%m-%dT%H:%MZ')

    # Define endpoint
    url = f"https://api.octopus.energy/v1/electricity-meter-points/1419872111009/meters/23J0205738/consumption/?page_size=100&period_from={period_from}&period_to={period_to}&order_by=period"

    response = requests.get(url, auth=(API_KEY, ''))
    if response.status_code == 200:
        return response.json()
    else:
        return None


data = fetch_usage_data()
print(data)


# Check if the request was successful
if response.status_code == 200:
    # Convert the response to JSON
    data = response.json()
    print(data)
else:
    print(f"Request failed with status code {response.status_code}")

# Write response to file
with open('data/AccountData.json', 'w') as file:
        json.dump(data, file, indent=4)  # indent=4 for pretty formatting


#for tarrif in data['results']:
#    # tarrif['code']
#    print(tarrif['code'], tarrif['full_name'], tarrif['links'])
"""