import os
import re

LOG_BASE = "/config/zigbee2mqtt/log"
TMP_DIR = "/config/tmp"
OUTPUT_PATH = os.path.join(TMP_DIR, "z2m_update_list.txt")

# Ensure tmp dir exists
os.makedirs(TMP_DIR, exist_ok=True)

# Step 1: Get latest log directory
log_dirs = [d for d in os.listdir(LOG_BASE) if os.path.isdir(os.path.join(LOG_BASE, d))]
log_dirs.sort()
if not log_dirs:
    print("❌ No log directories found.")
    exit(1)

latest_dir = log_dirs[-1]
log_dir_path = os.path.join(LOG_BASE, latest_dir)

# Step 2: Use log.log specifically if it exists
log_path = os.path.join(log_dir_path, "log.log")
if not os.path.exists(log_path):
    print(f"❌ log.log not found in: {log_dir_path}")
    exit(1)

print(f"📄 Using log file: {log_path}")

# Step 3: Extract update-available devices
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
                print(f"✅ Found: {entity_id}")

if not entities:
    print("⚠️ No update entities found in log.")

# Step 4: Write output
with open(OUTPUT_PATH, "w") as f_out:
    for eid in sorted(entities):
        f_out.write(f"{eid}\n")

print(f"✅ Written {len(entities)} entries to {OUTPUT_PATH}")
