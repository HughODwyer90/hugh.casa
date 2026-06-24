import json, sys, os

path = "/config/battery_notification_log.json"
device_id = sys.argv[1]
cooldown = 86400  # 24 hours

try:
    with open(path, "r") as f:
        log = json.load(f)
except:
    log = {}

import time
now = int(time.time())
last_sent = log.get(device_id, 0)

if now - last_sent > cooldown:
    log[device_id] = now
    with open(path, "w") as f:
        json.dump(log, f)
    print("notify")
else:
    print("skip")