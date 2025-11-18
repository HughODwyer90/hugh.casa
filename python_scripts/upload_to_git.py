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
YAML_DIRS = [
    "/config",
    "/config/custom_sensors_template",
    "/config/custom_sensors_rest",
    "/config/esphome"
]

PYTHON_SCRIPTS_DIR = "/config/python_scripts"
ASSETS_DIR = "/config/www/community/assets"
HA_BASE_URL = "http://homeassistant.local:8123"

# ✅ Upload Paths
COMMUNITY_DIR = "community/"
YAML_PREVIEWS_DIR = "community/yaml_previews/"
COMMUNITY_ASSETS_DIR = "community/assets/"
PYTHON_SCRIPTS_UPLOAD_DIR = "community/python_scripts/"  # ✅ Python scripts go here

# Load secrets
secrets = SecretsManager()
ha_token = secrets["ha_access_token"]
github_token = secrets["github_token"]
github_repo = secrets["github_repro"]
uploaded_files = []  # ✅ Track uploaded files

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

def upload_python_scripts():
    """Find and upload all Python scripts, ensuring they go to 'community/python_scripts/'."""
    exclusions = load_exclusions()

    if not os.path.exists(PYTHON_SCRIPTS_DIR):
        print(f"⚠️ Warning: Python scripts directory {PYTHON_SCRIPTS_DIR} does not exist. Skipping...")
        return

    python_files = [f for f in os.listdir(PYTHON_SCRIPTS_DIR) if f.endswith(".py") and not should_exclude(f, exclusions)]

    if not python_files:
        print("⚠️ No Python scripts found after applying exclusions.")
        return

    for py_file in python_files:
        local_path = os.path.join(PYTHON_SCRIPTS_DIR, py_file)
        github_py_path = f"{PYTHON_SCRIPTS_UPLOAD_DIR}{py_file}"  # ✅ Correct folder

        try:
            uploader.upload_file(local_path, github_py_path, f"python_scripts/{py_file}")
            uploaded_files.append(github_py_path)  # ✅ Track upload
            print(f"✅ Uploaded Python script: {github_py_path}")
        except Exception as e:
            print(f"❌ Error uploading Python script {py_file}: {e}")

    print("✅ All Python scripts have been uploaded.")

def should_exclude_entity(entity):
    """Check if an entity should be redacted for privacy/security reasons."""
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
    """Fetch, redact, and upload Home Assistant entities."""
    response = requests.get(f"{HA_BASE_URL}/api/states", headers=ha_headers, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"❌ Error retrieving entities: {response.status_code}")

    entities = response.json()
    version = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")

    # ✅ **Apply redaction logic**
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

    print(f"✅ Total entities fetched: {len(entities)}, Redacted: {redacted_count}")

    # ✅ Generate HTML & JSON with redacted entities
    html_content = HTMLGenerator.generate_entities_html(processed_entities, len(entities), version, [], redacted_count)
    json_content = json.dumps(processed_entities, indent=4)

    # ✅ Upload redacted files
    uploader.upload_content(f"{COMMUNITY_DIR}entities.html", html_content, "Update entities HTML")
    uploader.upload_content(f"{COMMUNITY_DIR}entities.json", json_content, "Update entities JSON")
    uploaded_files.append("entities.html")  # ✅ Track uploaded file


def upload_integrations():
    """Fetch and upload Home Assistant integrations."""
    response = requests.get(f"{HA_BASE_URL}/api/config/config_entries/entry", headers=ha_headers)
    if response.status_code != 200:
        raise RuntimeError(f"❌ Error retrieving integrations: {response.status_code}")

    integrations = response.json()
    version = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")

    html_content = HTMLGenerator.generate_integrations_html(integrations, len(integrations), version)
    json_content = json.dumps(integrations, indent=4)

    uploader.upload_content(f"{COMMUNITY_DIR}integrations.html", html_content, "Update integrations HTML")
    uploader.upload_content(f"{COMMUNITY_DIR}integrations.json", json_content, "Update integrations JSON")
    uploaded_files.append("integrations.html")  # ✅ Track uploaded file

def upload_yaml_files():
    """Find, generate previews, and upload all YAML files, respecting exclusions."""
    exclusions = load_exclusions()
    yaml_files = []

    for yaml_dir in YAML_DIRS:
        yaml_files.extend([
            (yaml_dir, f) for f in os.listdir(yaml_dir) 
            if f.endswith(".yaml") and not should_exclude(f, exclusions)
        ])

    if not yaml_files:
        print("⚠️ No YAML files found after applying exclusions.")
        return

    for yaml_dir, yaml_file in yaml_files:
        yaml_file_path = os.path.join(yaml_dir, yaml_file)

        github_yaml_path = f"{COMMUNITY_DIR}{yaml_file}"
        github_yaml_html_path = f"{YAML_PREVIEWS_DIR}{yaml_file}.html"

        with open(yaml_file_path, "r", encoding="utf-8") as file:
            yaml_content = file.read()

        yaml_html = HTMLGenerator.generate_yaml_html(yaml_file, yaml_content)

        try:
            uploader.upload_file(yaml_file_path, github_yaml_path, f"yaml/{yaml_file}")
            uploaded_files.append(yaml_file)  # ✅ Only append if upload succeeds

            uploader.upload_content(github_yaml_html_path, yaml_html, f"{yaml_file}")
            uploaded_files.append(f"yaml_previews/{yaml_file}.html")  # ✅ Only append if upload succeeds

            print(f"✅ Uploaded: {yaml_file} & its HTML preview.")
        
        except Exception as e:
            print(f"❌ Error uploading {yaml_file}: {e}")

    print("✅ All YAML files and their HTML previews have been uploaded.")



def upload_asset_files():
    """Upload all files from the assets directory, ensuring correct placement in 'community/assets/'."""
    exclusions = load_exclusions()

    if not os.path.exists(ASSETS_DIR):
        print(f"⚠️ Warning: Assets directory {ASSETS_DIR} does not exist. Skipping...")
        return

    asset_files = [f for f in os.listdir(ASSETS_DIR) if not should_exclude(f, exclusions)]
    
    if not asset_files:
        print("⚠️ No asset files found after applying exclusions.")
        return

    # ✅ Ensure the upload path is explicitly set to 'community/assets/'
    for asset_file in asset_files:
        local_path = os.path.join(ASSETS_DIR, asset_file)
        github_asset_path = f"community/assets/{asset_file}"  # ✅ Correctly places assets inside 'community/assets/'

        # **🛠 Print full paths to debug placement**
        print(f"🔹 Uploading {local_path} ➝ {github_asset_path}")

        try:
            uploader.upload_file(local_path, github_asset_path, f"{github_asset_path}")  # ✅ Fix commit message
            uploaded_files.append(github_asset_path)  # ✅ Track upload correctly
            print(f"✅ Successfully uploaded: {github_asset_path}")  # ✅ Log correct location
        except Exception as e:
            print(f"❌ Error uploading asset {asset_file}: {e}")

    print("✅ All assets have been uploaded successfully.")




def generate_and_upload_index():
    """Generate and upload index.html based on uploaded files."""
    html_files = [f for f in uploaded_files if f.endswith(".html") and not f.startswith("yaml_previews/")]
    yaml_preview_files = [f for f in uploaded_files if f.startswith("yaml_previews/")]

    if not html_files and not yaml_preview_files:
        print("⚠️ No uploaded HTML files found. Skipping index generation.")
        return

    index_content = HTMLGenerator.generate_index_html(html_files, yaml_preview_files)
    uploader.upload_content(f"{COMMUNITY_DIR}index.html", index_content, "Update index.html")
    print("✅ index.html updated and uploaded successfully.")

if __name__ == "__main__":
    upload_entities()
    upload_integrations()
    upload_yaml_files()
    upload_asset_files()
    upload_python_scripts()
    generate_and_upload_index()
    print(f"✅ All files uploaded successfully. Total files uploaded: {len(uploaded_files) + 1}")  # ✅ +1 for index.html
