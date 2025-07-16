import yaml
import time
import requests

# === Configuration ===
TMP_FILE = "/config/tmp/z2m_update_list.txt"
LOG_FILE = "/config/tmp/z2m_update_log.txt"
SECRETS_FILE = "/config/secrets.yaml"
HA_URL = "http://homeassistant.local:8123"  # Replace with your actual HA address

MAX_WAIT_MINUTES = 60
POLL_INTERVAL = 60  # seconds

# === Load token from secrets.yaml ===
try:
    with open(SECRETS_FILE, "r") as f:
        secrets = yaml.safe_load(f)
        TOKEN = secrets.get("ha_access_token")
        if not TOKEN:
            raise ValueError("ha_access_token not found in secrets.yaml")
except Exception as e:
    print(f"❌ Failed to load token: {e}")
    exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

log_lines = []

def log(msg):
    print(msg)
    log_lines.append(msg)

def get_state(entity_id):
    try:
        resp = requests.get(f"{HA_URL}/api/states/{entity_id}", headers=HEADERS)
        if resp.status_code == 200:
            return resp.json()
        else:
            log(f"⚠️ Failed to fetch state for {entity_id}: {resp.text}")
    except Exception as e:
        log(f"⚠️ Exception while fetching state for {entity_id}: {e}")
    return None

# === Load entity list ===
try:
    with open(TMP_FILE, "r") as f:
        entity_ids = [line.strip() for line in f if line.strip()]
    log(f"✅ Loaded {len(entity_ids)} update entities.")
except Exception as e:
    log(f"❌ Failed to read update list: {e}")
    entity_ids = []

# === Process updates one-by-one ===
for entity_id in entity_ids:
    state = get_state(entity_id)
    if not state:
        log(f"❌ Skipping {entity_id}: state not found")
        continue

    if state["state"] != "on":
        log(f"⏩ Skipping {entity_id}: no update available (state = {state['state']})")
        continue

    attrs = state.get("attributes", {})
    installed = attrs.get("installed_version")
    latest = attrs.get("latest_version")

    log(f"🚀 Starting update: {entity_id} (installed: {installed}, latest: {latest})")

    # Trigger the update
    resp = requests.post(
        f"{HA_URL}/api/services/update/install",
        headers=HEADERS,
        json={"entity_id": entity_id}
    )

    if resp.status_code != 200:
        log(f"❌ Failed to start update for {entity_id}: {resp.text}")
        continue
    else:
        log(f"📤 Update triggered for {entity_id}")

    # Wait until update completes
    for minute in range(MAX_WAIT_MINUTES):
        time.sleep(POLL_INTERVAL)
        state = get_state(entity_id)
        if not state:
            continue

        current_state = state.get("state")
        attrs = state.get("attributes", {})
        installed_now = attrs.get("installed_version")
        latest_now = attrs.get("latest_version")

        if current_state == "off" or installed_now == latest_now:
            log(f"✅ Update complete for {entity_id} (installed: {installed_now})")
            break

        log(f"⏳ Still updating {entity_id} (minute {minute + 1}): state={current_state}")
    else:
        log(f"⚠️ Timeout: {entity_id} did not finish after {MAX_WAIT_MINUTES} minutes")

# === Write log file ===
try:
    with open(LOG_FILE, "w") as f:
        for line in log_lines:
            f.write(line + "\n")
    log(f"📄 Log written to {LOG_FILE}")
except Exception as e:
    print(f"❌ Failed to write log file: {e}")
