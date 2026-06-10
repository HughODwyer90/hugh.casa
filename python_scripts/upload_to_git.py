import os
import re
import json
import requests
from fnmatch import fnmatch
from secret_manager import SecretsManager
from git_uploader import GitHubUploader

CONFIG_ROOT = "/config"
EXCLUDE_FILE_PATH = "/config/text_files/excluded_files.txt"
HA_BASE_URL = "http://homeassistant.local:8123"

EXCLUDED_DIRS = {
    ".storage",
    ".vscode",
    ".cloud",
    ".cache",
    "deps",
    "tts",
    "blueprints",
    "custom_components",
}

HARDCODED_EXCLUSIONS = {"secrets.yaml.bak"}

SENSITIVE_JSON_FILES = {"SERVICE_ACCOUNT.JSON"}

SENSITIVE_JSON_FIELDS = {
    "private_key",
    "private_key_id",
    "client_id",
    "client_email",
    "client_x509_cert_url",
}

secrets = SecretsManager()
ha_token = secrets["ha_access_token"]
github_token = secrets["github_token"]
github_repo = secrets["github_repro"]
uploaded_files = []

if not ha_token or not github_token or not github_repo:
    raise ValueError("Missing required tokens or repository in secrets.yaml.")

uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)
ha_headers = {"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"}

KEY_PATTERN = re.compile(
    r"api:\s*(?:#.*\n|\s)*"
    r"encryption:\s*(?:#.*\n|\s)*"
    r"key:\s*[\"']?([^\"'\n]+)[\"']?",
    re.MULTILINE,
)

SECRET_VALUE_PATTERN = re.compile(r'^(\s*(?!#)\w[\w\s]*:\s*)(.+)$', re.MULTILINE)


def load_exclusions():
    if os.path.exists(EXCLUDE_FILE_PATH):
        with open(EXCLUDE_FILE_PATH, "r") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    return []


def should_exclude(filename, exclusions):
    if filename in HARDCODED_EXCLUSIONS:
        return True
    return any(fnmatch(filename, pattern) for pattern in exclusions)


def has_encryption_key(file_path: str) -> bool:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = KEY_PATTERN.search(content)
        if not match:
            return False
        key_value = match.group(1).strip()
        return not key_value.startswith("!secret")
    except Exception:
        return False


def redact_secrets_file(content: str) -> str:
    """Replace all values in secrets.yaml with ****."""
    return SECRET_VALUE_PATTERN.sub(r'\1****', content)


def redact_json_file(content: str) -> str:
    """Redact sensitive fields in a JSON file."""
    try:
        data = json.loads(content)
        for field in SENSITIVE_JSON_FIELDS:
            if field in data:
                data[field] = "****"
        return json.dumps(data, indent=2)
    except Exception:
        return content


def read_file(local_path: str):
    """Read a file as binary or text depending on extension."""
    is_binary = local_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico"))
    with open(local_path, "rb" if is_binary else "r", encoding=None if is_binary else "utf-8") as f:
        return f.read()


def upload_config_files():
    exclusions = load_exclusions()

    for root, dirs, files in os.walk(CONFIG_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for filename in files:
            if should_exclude(filename, exclusions):
                continue

            local_path = os.path.join(root, filename)

            if filename.endswith(".yaml") and has_encryption_key(local_path):
                print(f"🔒 Skipping {local_path} (contains hardcoded encryption key)")
                continue

            rel_path = os.path.relpath(local_path, CONFIG_ROOT)
            github_path = rel_path.replace(os.sep, "/")

            try:
                content = read_file(local_path)

                if filename == "secrets.yaml":
                    content = redact_secrets_file(content)
                    print(f"🔒 Uploading redacted: {github_path}")

                if filename in SENSITIVE_JSON_FILES:
                    content = redact_json_file(content)
                    print(f"🔒 Uploading redacted: {github_path}")

                uploader.upload_file(
                    content=content,
                    github_file_path=github_path,
                    commit_message=f"backup: {filename}"
                )
                uploaded_files.append(github_path)
                print(f"✅ Uploaded: {github_path}")
            except Exception as e:
                print(f"❌ Error uploading {filename}: {e}")

    print("✅ All config files uploaded.")


def should_exclude_entity(entity):
    entity_id = entity["entity_id"]
    entity_id_lower = entity_id.lower()
    attributes = entity.get("attributes", {})

    sensitive_ids = {
        "input_text.kasa_token",
        "input_text.payslip_sender",
    }

    return (
        (entity_id_lower.startswith("device_tracker.") and "toothbrush" not in entity_id_lower) or
        any("device_tracker." in str(value) for value in attributes.values()) or
        "gps" in entity_id_lower or
        entity_id_lower.startswith("zone.") or
        (entity_id_lower.startswith("input_text.") and attributes.get("mode", "").lower() == "password") or
        entity_id in sensitive_ids
    )


def upload_entities():
    response = requests.get(f"{HA_BASE_URL}/api/states", headers=ha_headers, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"❌ Error retrieving entities: {response.status_code}")

    entities = response.json()
    redacted_count = 0
    processed_entities = []

    for entity in entities:
        if should_exclude_entity(entity):
            processed_entities.append({
                "entity_id": entity["entity_id"],
                "state": "REDACTED",
                "attributes": {"friendly_name": "REDACTED"}
            })
            redacted_count += 1
        else:
            processed_entities.append(entity)

    print(f"✅ Total entities: {len(entities)}, Redacted: {redacted_count}")

    uploader.upload_content("entities.json", json.dumps(processed_entities, indent=4), "backup: entities")
    uploaded_files.append("entities.json")


def upload_integrations():
    response = requests.get(f"{HA_BASE_URL}/api/config/config_entries/entry", headers=ha_headers)
    if response.status_code != 200:
        raise RuntimeError(f"❌ Error retrieving integrations: {response.status_code}")

    integrations = response.json()
    uploader.upload_content("integrations.json", json.dumps(integrations, indent=4), "backup: integrations")
    uploaded_files.append("integrations.json")


if __name__ == "__main__":
    upload_entities()
    upload_integrations()
    upload_config_files()
    print(f"✅ Backup complete. Total files uploaded: {len(uploaded_files)}")