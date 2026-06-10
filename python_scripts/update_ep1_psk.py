import json
import re
import sys
import requests
from pathlib import Path
from secret_manager import SecretsManager

secrets = SecretsManager()
HA_URL   = secrets["ha_url"].rstrip("/")
HA_TOKEN = secrets["ha_access_token"]


TEST_NOTIFY = False  # Set True to send a test notification regardless of updates

CORE_ENTRIES_PATH = Path("/config/.storage/core.config_entries")
ESPHOME_DIR = Path("/config/esphome")
SECRETS_PATH = Path("/config/esphome/secrets.yaml")

# Matches api.encryption.key (handles indentation and optional quotes)
KEY_PATTERN = re.compile(
    r"api:\s*(?:#.*\n|\s)*"
    r"encryption:\s*(?:#.*\n|\s)*"
    r"key:\s*[\"']?([^\"'\n]+)[\"']?",
    re.MULTILINE,
)

TITLE_PATTERN = re.compile(
    r"^\s*friendly_name:\s*[\"']?(.+?)[\"']?\s*$",
    re.MULTILINE,
)


def load_esphome_secrets() -> dict:
    """Load ESPHome secrets.yaml as a plain key: value dict."""
    if not SECRETS_PATH.exists():
        print(f"[WARN] ESPHome secrets file not found: {SECRETS_PATH}")
        return {}
    esphome_secrets = {}
    for line in SECRETS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            esphome_secrets[k.strip()] = v.strip()
    return esphome_secrets


def resolve_secret(value: str, esphome_secrets: dict) -> str:
    """If value is a !secret reference, resolve it. Otherwise return as-is."""
    m = re.match(r"!secret\s+(\S+)", value)
    if m:
        key = m.group(1)
        if key not in esphome_secrets:
            print(f"[WARN] Secret '{key}' not found in secrets.yaml")
        return esphome_secrets.get(key, value)
    return value


def extract_yaml_key(yaml_path: Path, esphome_secrets: dict) -> str | None:
    """Return the api.encryption.key value (resolved from secrets), or None if not present."""
    text = yaml_path.read_text(encoding="utf-8")
    m = KEY_PATTERN.search(text)
    if not m:
        return None
    return resolve_secret(m.group(1).strip(), esphome_secrets)


def extract_yaml_title(yaml_path: Path) -> str:
    """Return friendly_name if set, otherwise derive from filename."""
    text = yaml_path.read_text(encoding="utf-8")
    m = TITLE_PATTERN.search(text)
    if m:
        return m.group(1).strip()
    return yaml_path.stem.replace("-", " ").title()


def discover_devices(esphome_dir: Path) -> list[dict]:
    """Find all YAML files in the ESPHome dir that contain an encryption key."""
    esphome_secrets = load_esphome_secrets()
    devices = []
    for yaml_path in sorted(esphome_dir.glob("*.yaml")):
        key = extract_yaml_key(yaml_path, esphome_secrets)
        if key is None:
            continue
        title = extract_yaml_title(yaml_path)
        devices.append({"yaml_path": yaml_path, "title": title, "yaml_key": key})
    return devices


def load_core_entries():
    if not CORE_ENTRIES_PATH.exists():
        raise FileNotFoundError(f"HA core entries not found: {CORE_ENTRIES_PATH}")
    core_data = json.loads(CORE_ENTRIES_PATH.read_text(encoding="utf-8"))
    entries = core_data.get("data", {}).get("entries", [])
    return core_data, entries


def find_esphome_entry(entries: list, title: str):
    """Return the HA config entry matching the given title, or None."""
    for entry in entries:
        if entry.get("domain") == "esphome" and entry.get("title") == title:
            return entry
    return None


def dump_ha_esphome_titles(entries: list):
    """Print all ESPHome entry titles found in HA storage, for diagnostics."""
    esphome_entries = [e for e in entries if e.get("domain") == "esphome"]
    if not esphome_entries:
        print("[DIAG] No ESPHome entries found in HA config entries at all.")
        return
    print(f"[DIAG] All ESPHome entry titles in HA storage ({len(esphome_entries)}):")
    for e in esphome_entries:
        print(f"  - \"{e.get('title')}\"  (entry_id={e.get('entry_id', '?')})")


def notify_updates(updates: list[dict]):
    """Send a persistent HA notification listing which devices were updated."""
    count = len(updates)
    device_lines = "\n".join(
        f"• {u['title']}\n"
        f"  HA:   {u['old_key'] or '(none)'}\n"
        f"  YAML: {u['new_key']}"
        for u in updates
    )
    message = f"{count} ESP device(s) updated. Restart HA to apply.\n\n{device_lines}"
    try:
        requests.post(
            f"{HA_URL}/api/services/notify/notifications",
            headers={"Authorization": f"Bearer {HA_TOKEN}"},
            json={
                "message": message,
                "data": {
                    "notification_icon": "mdi:restart",
                    "actions": [
                        {"action": "RESTART_HA", "title": "Restart HA"}
                    ],
                },
            },
            timeout=10,
        )
        print("[INFO] Notification sent.")
    except Exception as e:
        print(f"[WARN] Failed to send notification: {e}")


def main():
    if TEST_NOTIFY:
        print("[INFO] TEST_NOTIFY is True, sending test notification.")
        notify_updates([{"title": "Test Device A", "old_key": "old123", "new_key": "new456"}])
        sys.exit(0)

    if not ESPHOME_DIR.exists():
        print(f"[ERROR] ESPHome directory not found: {ESPHOME_DIR}")
        sys.exit(1)

    devices = discover_devices(ESPHOME_DIR)
    if not devices:
        print("[INFO] No ESPHome YAML files with encryption keys found.")
        sys.exit(0)

    print(f"\n[INFO] Discovered {len(devices)} device(s) with encryption keys:")
    for d in devices:
        print(f"  - {d['title']} ({d['yaml_path'].name})")

    core_data, entries = load_core_entries()

    print()
    dump_ha_esphome_titles(entries)
    print()

    esphome_secrets = load_esphome_secrets()
    updates = []
    skipped = []

    for d in devices:
        title = d["title"]
        yaml_key = d["yaml_key"].strip()

        entry = find_esphome_entry(entries, title)
        if not entry:
            skipped.append({"file": d["yaml_path"].name, "title": title})
            continue

        ha_key = (entry.get("data", {}).get("noise_psk") or "").strip()
        ha_key = resolve_secret(ha_key, esphome_secrets)

        if ha_key == yaml_key:
            print(f"[INFO] {title!r}: keys match, skipping.")
            continue

        updates.append({
            "title": title,
            "old_key": ha_key,
            "new_key": yaml_key,
        })
        entry.setdefault("data", {})["noise_psk"] = yaml_key

    print()

    if skipped:
        print(f"[WARN] {len(skipped)} device(s) skipped (no HA match found):")
        for s in skipped:
            print(f"  - {s['file']}  title={s['title']!r}")
        print(
            "\n  [HINT] Compare the title values above against the HA storage\n"
            "  titles in the [DIAG] block. They must match exactly.\n"
        )

    if not updates:
        print("[INFO] All matched keys are already in sync. No changes written.")
        sys.exit(0)

    print(f"[INFO] {len(updates)} key(s) will be updated:")
    for u in updates:
        print(
            f"  - {u['title']!r}\n"
            f"    HA  key: {u['old_key']}\n"
            f"    YAML key: {u['new_key']}"
        )

    CORE_ENTRIES_PATH.write_text(
        json.dumps(core_data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print("\n[INFO] Updated PSK(s) written to storage file.")
    notify_updates(updates)

    print("[INFO] PSK sync complete. Restart Home Assistant Core to apply changes.")
    if skipped:
        print(f"[WARN] {len(skipped)} device(s) were skipped. Review the [WARN] output above.")
    sys.exit(0)


if __name__ == "__main__":
    main()