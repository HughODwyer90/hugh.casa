import json
import re
import sys
import subprocess
from pathlib import Path
from time import sleep

YAML_PATH = Path("/config/esphome/everything-presence-one-d719b0.yaml")
CORE_ENTRIES_PATH = Path("/config/.storage/core.config_entries")
TARGET_TITLE = "Everything Presence One"

# --- Extract key from ESPHome YAML ---
yaml_text = YAML_PATH.read_text(encoding="utf-8")

pattern = re.compile(
    r"api:\s*(?:#.*\n|\s)*"
    r"encryption:\s*(?:#.*\n|\s)*"
    r"key:\s*[\"']?([^\"'\n]+)[\"']?",
    re.MULTILINE
)

match = pattern.search(yaml_text)
if not match:
    print("[ERROR] Could not extract api.encryption.key from YAML.")
    sys.exit(2)

yaml_key = match.group(1).strip()
print(f"[INFO] ESPHome YAML key: {yaml_key}")

# --- Load Home Assistant storage file ---
core_data = json.loads(CORE_ENTRIES_PATH.read_text(encoding="utf-8"))
entries = core_data.get("data", {}).get("entries", [])

ha_key = None
target_entry = None

for entry in entries:
    if entry.get("domain") == "esphome" and entry.get("title") == TARGET_TITLE:
        ha_key = entry.get("data", {}).get("noise_psk")
        target_entry = entry
        break

if ha_key is None:
    print(f"[ERROR] No ESPHome entry titled '{TARGET_TITLE}'.")
    sys.exit(3)

print(f"[INFO] HA stored PSK: {ha_key}")

# --- If keys match, do nothing ---
if ha_key == yaml_key:
    print("[INFO] Keys already match. No restart or update needed.")
    sys.exit(0)

# --- Keys differ → Update required ---
print("[INFO] Keys differ. Preparing to update Home Assistant...")

# --- Stop Home Assistant Core ---
print("[INFO] Stopping Home Assistant Core...")
subprocess.run(["ha", "core", "stop"])
sleep(2)

# --- Update storage file ---
target_entry["data"]["noise_psk"] = yaml_key

CORE_ENTRIES_PATH.write_text(
    json.dumps(core_data, indent=2, sort_keys=True),
    encoding="utf-8"
)

print("[INFO] Updated PSK in storage file.")

# --- Restart Home Assistant Core ---
print("[INFO] Restarting Home Assistant Core...")
subprocess.run(["ha", "core", "start"])
sleep(2)

print("[INFO] PSK sync complete. Device will reconnect with new key.")
sys.exit(0)
