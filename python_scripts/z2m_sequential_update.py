import os
import re
import yaml
import time
import requests
import traceback

# === Configuration ===
LOG_BASE = "/config/zigbee2mqtt/log"
TMP_DIR = "/config/tmp"
LOG_FILE = os.path.join(TMP_DIR, "z2m_update_log.txt")
SECRETS_FILE = "/config/secrets.yaml"
HA_URL = "http://homeassistant.local:8123"

MAX_WAIT_MINUTES = 60
POLL_INTERVAL = 60  # seconds

# === Ensure tmp dir exists ===
os.makedirs(TMP_DIR, exist_ok=True)

# === Initialize log file ===
with open(LOG_FILE, "w") as f:
    f.write("🟢 Z2M update script started\n")

def log(msg):
    print(msg)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(msg + "\n")
    except Exception as e:
        print(f"❌ Failed to write log: {e}")

# === Load HA token from secrets.yaml ===
try:
    with open(SECRETS_FILE, "r") as f:
        secrets = yaml.safe_load(f)
        TOKEN = secrets.get("ha_access_token")
        if not TOKEN:
            raise ValueError("ha_access_token not found in secrets.yaml")
except Exception as e:
    log(f"❌ Failed to load token: {e}")
    exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def get_state(entity_id):
    try:
        resp = requests.get(f"{HA_URL}/api/states/{entity_id}", headers=HEADERS)
        if resp.status_code == 200:
            return resp.json()
        else:
            log(f"⚠️ Failed to fetch state for {entity_id}: {resp.status_code}")
            log(f"🔍 Response: {resp.text}")
    except Exception as e:
        log(f"⚠️ Exception while fetching state for {entity_id}: {e}")
    return None

def main():
    # === Step 1: Find latest Zigbee2MQTT log ===
    log_dirs = [d for d in os.listdir(LOG_BASE) if os.path.isdir(os.path.join(LOG_BASE, d))]
    log_dirs.sort()
    if not log_dirs:
        log("❌ No log directories found.")
        return

    latest_dir = log_dirs[-1]
    log_path = os.path.join(LOG_BASE, latest_dir, "log.log")
    if not os.path.exists(log_path):
        log(f"❌ log.log not found in: {log_path}")
        return

    log(f"📄 Using log file: {log_path}")

    # === Step 2: Parse log for update-available devices ===
    topic_re = re.compile(r"zigbee2mqtt/([^']+)")
    entities = set()

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if "zigbee2mqtt/" in line and '"state":"available"' in line:
                topic_match = topic_re.search(line)
                if topic_match:
                    name = topic_match.group(1).strip().lower().replace(" ", "_")
                    entity_id = f"update.{name}"
                    entities.add(entity_id)

    for eid in sorted(entities):
        log(f"✅ Found update candidate: {eid}")

    if not entities:
        log("⚠️ No update entities found in log.")
        return

    # === Step 3: Trigger updates one at a time ===
    for entity_id in sorted(entities):
        log("─" * 40)
        log(f"🔧 Processing: {entity_id}")
        
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

        def trigger_update():
            return requests.post(
                f"{HA_URL}/api/services/update/install",
                headers=HEADERS,
                json={"entity_id": entity_id}
            )

        # Try once, then retry after 5s if needed
        resp = trigger_update()
        if resp.status_code != 200:
            log(f"⚠️ First attempt failed: {resp.status_code} — retrying...")
            time.sleep(5)
            resp = trigger_update()

        if resp.status_code != 200:
            log(f"❌ Failed to start update for {entity_id}: {resp.text}")
            continue

        log(f"📤 Update triggered for {entity_id}")

        # Wait for update to complete
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

            if minute == 0 or (minute + 1) % 5 == 0:
                log(f"⏳ Still updating {entity_id} (minute {minute + 1}) — state={current_state}")
        else:
            log(f"⚠️ Timeout: {entity_id} did not finish after {MAX_WAIT_MINUTES} minutes")

# === Run Main Safely ===
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"💥 Script crashed with exception: {e}")
        tb = traceback.format_exc()
        log(tb)
