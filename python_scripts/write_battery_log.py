import json, os

path = "/config/battery_notification_log.json"
device_id = data.get("device_id")
timestamp = data.get("timestamp")

try:
    with open(path, "r") as f:
        log = json.load(f)
except:
    log = {}

log[device_id] = timestamp

with open(path, "w") as f:
    json.dump(log, f)