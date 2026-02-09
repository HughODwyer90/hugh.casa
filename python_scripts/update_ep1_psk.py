import json
import re
import sys
import subprocess
from pathlib import Path
from time import sleep

CORE_ENTRIES_PATH = Path("/config/.storage/core.config_entries")

DEVICES = [
    {
        "yaml_path": Path("/config/esphome/everything-presence-one-d719b0.yaml"),
        "title": "Everything Presence One",
    },
    {
        "yaml_path": Path("/config/esphome/everything-presence-pro-cfbaf0.yaml"),
        "title": "Everything Presence Pro",
    },
]

KEY_PATTERN = re.compile(
    r"api:\s*(?:#.*\n|\s)*"
    r"encryption:\s*(?:#.*\n|\s)*"
    r"key:\s*[\"']?([^\"'\n]+)[\"']?",
    re.MULTILINE,
)

def extract_yaml_key(yaml_path: Path) -> str:
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML not found: {yaml_path}")
    text = yaml_path.read_text(encoding="utf-8")
    m = KEY_PATTERN.search(text)
    if not m:
        raise ValueError(f"Could not extract api.encryption.key from: {yaml_path}")
    return m.group(1).strip()

def load_core_entries():
    if not CORE_ENTRIES_PATH.exists():
        raise FileNotFoundError(f"HA core entries not found: {CORE_ENTRIES_PATH}")
    core_data = json.loads(CORE_ENTRIES_PATH.read_text(encoding="utf-8"))
    entries = core_data.get("data", {}).get("entries", [])
    return core_data, entries

def find_esphome_entry(entries, title: str):
    for entry in entries:
        if entry.get("domain") == "esphome" and entry.get("title") == title:
            return entry
    return None

def stop_ha():
    print("[INFO] Stopping Home Assistant Core...")
    subprocess.run(["ha", "core", "stop"], check=False)
    sleep(2)

def start_ha():
    print("[INFO] Restarting Home Assistant Core...")
    subprocess.run(["ha", "core", "start"], check=False)
    sleep(2)

def main():
    core_data, entries = load_core_entries()

    updates = []  # list of (title, old_psk, new_psk)
    for d in DEVICES:
        title = d["title"]
        yaml_path = d["yaml_path"]

        try:
            yaml_key = extract_yaml_key(yaml_path)
        except Exception as e:
            print(f"[ERROR] {title}: {e}")
            sys.exit(2)

        print(f"[INFO] {title} YAML key: {yaml_key}")

        entry = find_esphome_entry(entries, title)
        if not entry:
            print(f"[ERROR] No ESPHome entry titled '{title}'.")
            sys.exit(3)

        ha_key = entry.get("data", {}).get("noise_psk")
        print(f"[INFO] {title} HA stored PSK: {ha_key}")

        if ha_key != yaml_key:
            updates.append((title, ha_key, yaml_key))
            entry.setdefault("data", {})["noise_psk"] = yaml_key

    if not updates:
        print("[INFO] All keys already match. No restart or update needed.")
        sys.exit(0)

    print("[INFO] Keys differ for:")
    for title, old_psk, new_psk in updates:
        print(f"  - {title}: HA={old_psk} -> YAML={new_psk}")

    stop_ha()

    CORE_ENTRIES_PATH.write_text(
        json.dumps(core_data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print("[INFO] Updated PSK(s) in storage file.")

    start_ha()

    print("[INFO] PSK sync complete. Device(s) will reconnect with new key(s).")
    sys.exit(0)

if __name__ == "__main__":
    main()