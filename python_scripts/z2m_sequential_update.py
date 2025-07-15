MAX_WAIT_MINUTES = 60  # total timeout per device
POLL_INTERVAL = 60     # check every 60 seconds

try:
    with open("/config/tmp/z2m_update_list.txt", "r") as f:
        entity_ids = [line.strip() for line in f if line.strip()]
except Exception as e:
    logger.error(f"Could not read update list: {e}")
    entity_ids = []

for entity_id in entity_ids:
    state = hass.states.get(entity_id)
    if not state or state.state != "on" or state.attributes.get("in_progress"):
        continue

    logger.info(f"🚀 Installing update for: {entity_id}")
    hass.services.call("update", "install", {"entity_id": entity_id}, blocking=True)

    for _ in range(MAX_WAIT_MINUTES):
        state = hass.states.get(entity_id)
        if not state.attributes.get("in_progress", False):
            logger.info(f"✅ Update complete for: {entity_id}")
            break
        time.sleep(POLL_INTERVAL)
    else:
        logger.warning(f"⏳ Timeout waiting for {entity_id} to finish updating.")
