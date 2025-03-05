import os
import json
import time
import requests
from datetime import datetime
from fnmatch import fnmatch
from secret_manager import SecretsManager
from git_uploader import GitHubUploader
from html_generator import HTMLGenerator

# File paths
EXCLUDE_FILE_PATH = "/config/text_files/excluded_files.txt"
HTML_DIR = "/config/www/community/"
YAML_DIRS = ["/config", "/config/esphome"]
PYTHON_SCRIPTS_DIR = "/config/python_scripts"
ASSETS_DIR = "/config/www/community/assets"
HA_BASE_URL = "http://homeassistant.local:8123"
LOCAL_JSON_PATH = "/config/www/community/entities.json"
LOCAL_HTML_PATH = "/config/www/community/entities.html"
INTEGRATIONS_JSON_PATH = "/config/www/community/integrations.json"
INTEGRATIONS_HTML_PATH = "/config/www/community/integrations.html"
INDEX_HTML_PATH = "/config/www/community/index.html"

# Load secrets
secrets = SecretsManager()
ha_token = secrets["ha_access_token"]
github_token = secrets["github_token"]
github_repo = secrets["github_repro"]

if not ha_token or not github_token or not github_repo:
    raise ValueError("Missing required tokens or repository in secrets.yaml.")

# Initialize GitHubUploader
uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)

# Headers for Home Assistant API
ha_headers = {"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"}


def load_exclusions():
    """Load excluded files and patterns from a text file."""
    if os.path.exists(EXCLUDE_FILE_PATH):
        with open(EXCLUDE_FILE_PATH, "r") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    return []


def should_exclude(filename, exclusions):
    """Check if a file should be excluded based on patterns."""
    return any(fnmatch(filename, pattern) for pattern in exclusions)


def get_files(directory, file_type, exclusions):
    """Retrieve all files of a given type from a directory, excluding specified ones."""
    return [f for f in os.listdir(directory) if f.endswith(file_type) and not should_exclude(f, exclusions)]


def fetch_home_assistant_entities():
    """Fetch entities from Home Assistant and redact sensitive ones."""
    response = requests.get(f"{HA_BASE_URL}/api/states", headers=ha_headers, timeout=30)
    if response.status_code == 200:
        entities = response.json()
        processed_entities = []
        redacted_count = 0

        for entity in entities:
            entity_id = entity["entity_id"]
            attributes = entity.get("attributes", {})

            if (
                (entity_id.startswith("device_tracker.") and "toothbrush" not in entity_id.lower()) or
                any("device_tracker." in str(value) for value in attributes.values()) or
                "gps" in entity_id.lower() or
                entity_id.startswith("zone.") or
                (entity_id.startswith("input_text.") and attributes.get("mode", "").lower() == "password")
            ):
                processed_entities.append({
                    "entity_id": entity_id,
                    "state": "REDACTED",
                    "attributes": {"friendly_name": "REDACTED"}
                })
                redacted_count += 1
            else:
                processed_entities.append(entity)

        print(f"Total entities fetched: {len(entities)} | Redacted: {redacted_count}")
        return processed_entities, redacted_count
    else:
        raise RuntimeError(f"Error retrieving entities: {response.status_code}")


def fetch_home_assistant_integrations():
    """Fetch integrations from Home Assistant."""
    response = requests.get(f"{HA_BASE_URL}/api/config/config_entries/entry", headers=ha_headers)
    if response.status_code == 200:
        integrations = response.json()
        return [
            {
                "Integration ID": entry.get("domain", "N/A"),
                "Config Entry ID": entry.get("entry_id", "N/A"),
                "Title": entry.get("title", "N/A"),
                "State": entry.get("state", "unknown"),
                "Source": entry.get("source", "unknown"),
            }
            for entry in integrations
        ]
    else:
        raise RuntimeError(f"Error fetching integrations: {response.status_code}")


def generate_and_upload_files():
    """Generate and upload all necessary files, with index.html done last."""
    exclusions = load_exclusions()

    # Fetch Entities and Process Data
    entities, redacted_count = fetch_home_assistant_entities()
    version = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
    prefixes = sorted(set(entity['entity_id'].split('.')[0] for entity in entities))

    # Generate and Save JSON/HTML for Entities
    html_content = HTMLGenerator.generate_entities_html(entities, len(entities), version, prefixes, redacted_count)
    with open(LOCAL_JSON_PATH, "w", encoding="utf-8") as json_file:
        json.dump(entities, json_file, indent=4)
    with open(LOCAL_HTML_PATH, "w", encoding="utf-8") as file:
        file.write(html_content)

    # Fetch and Save Integrations
    integrations = fetch_home_assistant_integrations()
    integrations_html = HTMLGenerator.generate_integrations_html(integrations, len(integrations), version)
    with open(INTEGRATIONS_JSON_PATH, "w", encoding="utf-8") as json_file:
        json.dump(integrations, json_file, indent=4)
    with open(INTEGRATIONS_HTML_PATH, "w", encoding="utf-8") as file:
        file.write(integrations_html)

    # Upload JSON and HTML Files
    files_to_upload = {
        LOCAL_HTML_PATH: "community/entities.html",
        LOCAL_JSON_PATH: "community/entities.json",
        INTEGRATIONS_HTML_PATH: "community/integrations.html",
        INTEGRATIONS_JSON_PATH: "community/integrations.json"
    }
    
    for local_path, github_path in files_to_upload.items():
        try:
            uploader.upload_file(local_path, github_path, f"Update {os.path.basename(local_path)}")
            print(f"✅ Uploaded {os.path.basename(local_path)}")
        except Exception as e:
            print(f"❌ Error uploading {os.path.basename(local_path)}: {e}")

    # Upload YAML Files
    yaml_files = [os.path.join(dir, f) for dir in YAML_DIRS for f in get_files(dir, ".yaml", exclusions)]
    for yaml_file in yaml_files:
        try:
            uploader.upload_file(yaml_file, f"community/{os.path.basename(yaml_file)}", f"Update {yaml_file}")
            print(f"✅ Uploaded {os.path.basename(yaml_file)}")
        except Exception as e:
            print(f"❌ Error uploading {os.path.basename(yaml_file)}: {e}")
        time.sleep(5)

    # Upload Python Scripts
    py_files = [os.path.join(PYTHON_SCRIPTS_DIR, f) for f in get_files(PYTHON_SCRIPTS_DIR, ".py", exclusions)]
    for py_file in py_files:
        try:
            uploader.upload_file(py_file, f"python_scripts/{os.path.basename(py_file)}", f"Update {py_file}")
            print(f"✅ Uploaded {os.path.basename(py_file)}")
        except Exception as e:
            print(f"❌ Error uploading {os.path.basename(py_file)}: {e}")

    # **Index Generation Last**
    html_files = get_files(HTML_DIR, ".html", exclusions)
    yaml_files = get_files(YAML_DIRS[0], ".yaml", exclusions)
    index_content = HTMLGenerator.generate_index_html(html_files, yaml_files)
    
    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as file:
        file.write(index_content)

    try:
        uploader.upload_file(INDEX_HTML_PATH, "community/index.html", "Update index.html with latest file listings")
        print("✅ Index file updated and uploaded last.")
    except Exception as e:
        print(f"❌ Error uploading index.html: {e}")

    print("✅ All files have been updated and uploaded successfully.")


if __name__ == "__main__":
    generate_and_upload_files()
