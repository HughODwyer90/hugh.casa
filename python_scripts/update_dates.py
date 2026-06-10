#!/usr/bin/env python3
import sys
import requests
from datetime import datetime
import calendar
from secret_manager import SecretsManager

secrets = SecretsManager()

# -----------------------------
# Read CLI arguments
# -----------------------------
entity_id = sys.argv[1]
years = int(sys.argv[2])
months = int(sys.argv[3])

# -----------------------------
# CONFIG — keep BASE_URL as-is
# -----------------------------
BASE_URL = "http://homeassistant.local:8123"
TOKEN = secrets["ha_access_token"]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# -----------------------------
# Read current value from HA
# -----------------------------
resp = requests.get(f"{BASE_URL}/api/states/{entity_id}", headers=HEADERS)
resp.raise_for_status()
data = resp.json()

raw = data["state"]

# Parse date or datetime
try:
    dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
except:
    dt = datetime.strptime(raw, "%Y-%m-%d")

# -----------------------------
# Add years
# -----------------------------
new_year = dt.year + years
try:
    dt = dt.replace(year=new_year)
except:
    # Handle Feb 29 → Feb 28
    dt = dt.replace(year=new_year, day=28)

# -----------------------------
# Add months properly
# -----------------------------
year = dt.year
month = dt.month + months

# Normalize month rollover
while month > 12:
    month -= 12
    year += 1
while month < 1:
    month += 12
    year -= 1

# Clamp day to month's max
last_day = calendar.monthrange(year, month)[1]
day = min(dt.day, last_day)

final_dt = datetime(year, month, day)

final_date = final_dt.strftime("%Y-%m-%d")
final_time = datetime.now().strftime("%H:%M:%S")

# -----------------------------
# Send update to HA
# -----------------------------
payload = {
    "entity_id": entity_id,
    "date": final_date,
    "time": final_time,
}

resp2 = requests.post(
    f"{BASE_URL}/api/services/input_datetime/set_datetime",
    headers=HEADERS,
    json=payload,
)
resp2.raise_for_status()

print(f"Updated {entity_id} → {final_date} {final_time}")
