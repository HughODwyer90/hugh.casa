import os
import time

MAX_WAIT_MINUTES = 60
POLL_INTERVAL = 60
TMP_DIR = "/config/tmp"
TMP_FILE = f"{TMP_DIR}/z2m_update_list.txt"
LOG_FILE = f"{TMP_DIR}/z2m_update_log.txt"

inside_ha = "hass" in globals()
log_lines = []

def log(msg):
    if inside_ha:
        logger.info(msg)
    else:
        print(msg)
    log_lines.append(msg)

# Read update list
try:
    with open(TMP_FILE, "r") as f:
        entity_ids = [line.strip() for line in f if line.strip()]
except Exception as e:
    msg = f"❌ Could not read update list: {e}"
    log(msg)
    entity_ids = []

if not inside_ha:
    log("ℹ️ Skipping update execution — not running inside Home Assistant.")
else:
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if not state:
            log(f"❌ {entity_id}: Entity not found")
            continue
        if state.state != "on":
            log(f"⏩ {entity_id}: No update available (state = {state.state})")
            continue
        if state.attributes.get("in_progress"):
            log(f"⏳ {entity_id}: Already updating, skipping")
            continue

        log(f"🚀 Starting update: {entity_id}")
        hass.services.call("update", "install", {"entity_id": entity_id}, blocking=True)

        for _ in range(MAX_WAIT_MINUTES):
            state = hass.states.get(entity_id)
            if not state.attributes.get("in_progress", False):
                log(f"✅ Finished: {entity_id}")
                break
            time.sleep(POLL_INTERVAL)
        else:
            log(f"⚠️ Timeout waiting for: {entity_id}")

# Final log file output
try:
    with open(LOG_FILE, "w") as f_out:
        for line in log_lines:
            f_out.write(line + "\n")
except Exception as e:
    err = f"❌ Failed to write update log: {e}"
    if inside_ha:
        logger.error(err)
    else:
        print(err)

# Optional notification inside HA
if inside_ha and log_lines:
    hass.services.call(
        "persistent_notification/create",
        {
            "title": "Z2M Update Summary",
            "message": "\n".join(log_lines),
        }
    )
