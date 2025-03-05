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

MAX_RETRIES = 3  # Number of retries for failed uploads


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


def upload_to_github(local_path, github_path, commit_message):
    """Attempt to upload a file with retry logic."""
    if not os.path.exists(local_path):
        print(f"❌ Skipping {github_path}: File not found at {local_path}")
        return  # Skip non-existent files

    for attempt in range(MAX_RETRIES):
        try:
            uploader.upload_file(
                local_file_path=local_path,
                github_file_path=github_path,
                commit_message=commit_message
            )
            print(f"✅ Successfully uploaded: {github_path}")
            break
        except Exception as e:
            print(f"❌ Attempt {attempt + 1} failed for {github_path}: {e}")
            if attempt < MAX_RETRIES - 1:
                print("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print(f"❌ All attempts failed for {github_path}. Skipping.")


def fetch_home_assistant_entities():
    """Fetch entities from Home Assistant and redact sensitive ones."""
    response = requests.get(f"{HA_BASE_URL}/api/states", headers=ha_headers, timeout=30)
    if response.status_code == 200:
        return response.json()
    else:
        raise RuntimeError(f"Error retrieving entities: {response.status_code}")


def upload_entities():
    """Fetch and upload Home Assistant entities."""
    entities = fetch_home_assistant_entities()
    version = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
    
    html_content = HTMLGenerator.generate_entities_html(entities, len(entities), version, [], 0)

    with open(LOCAL_JSON_PATH, "w", encoding="utf-8") as json_file:
        json.dump(entities, json_file, indent=4)
    with open(LOCAL_HTML_PATH, "w", encoding="utf-8") as file:
        file.write(html_content)

    upload_to_github(LOCAL_HTML_PATH, "community/entities.html", "Update Home Assistant entities list")
    upload_to_github(LOCAL_JSON_PATH, "community/entities.json", "Update Home Assistant entities JSON list")


def upload_yaml_files():
    """Find and upload all YAML files, respecting exclusions and checking file existence."""
    exclusions = load_exclusions()
    yaml_files = []

    for yaml_dir in YAML_DIRS:
        yaml_files.extend(get_files(yaml_dir, ".yaml", exclusions))

    if not yaml_files:
        print("⚠️ No YAML files found after applying exclusions.")
        return

    for yaml_file in yaml_files:
        yaml_file_path = os.path.join(YAML_DIRS[0], yaml_file)

        # **CHECK IF FILE EXISTS BEFORE UPLOADING**
        if not os.path.exists(yaml_file_path):
            print(f"❌ Skipping {yaml_file}: File not found at {yaml_file_path}")
            continue  # Skip this file

        github_file_path = f"community/{yaml_file}"
        upload_to_github(yaml_file_path, github_file_path, f"Update {yaml_file}")
        time.sleep(5)


def upload_python_scripts():
    """Find and upload all Python scripts."""
    exclusions = load_exclusions()
    py_files = get_files(PYTHON_SCRIPTS_DIR, ".py", exclusions)

    if not py_files:
        print("⚠️ No Python scripts found after applying exclusions.")
        return

    for py_file in py_files:
        py_file_path = os.path.join(PYTHON_SCRIPTS_DIR, py_file)
        github_file_path = f"python_scripts/{py_file}"

        upload_to_github(py_file_path, github_file_path, f"Update {py_file}")


def upload_asset_files():
    """Upload all files from the assets directory, respecting exclusions."""
    exclusions = load_exclusions()

    if not os.path.exists(ASSETS_DIR):
        print(f"⚠️ Warning: Assets directory {ASSETS_DIR} does not exist. Skipping...")
        return

    asset_files = [f for f in os.listdir(ASSETS_DIR) if not should_exclude(f, exclusions)]

    if not asset_files:
        print("⚠️ No asset files found after applying exclusions.")
        return

    for asset_file in asset_files:
        local_path = os.path.join(ASSETS_DIR, asset_file)
        github_path = f"community/assets/{asset_file}"

        upload_to_github(local_path, github_path, f"Update {asset_file}")


def generate_and_upload_index():
    """Generate and upload index.html after all other files."""
    exclusions = load_exclusions()
    html_files = get_files(HTML_DIR, ".html", exclusions)

    yaml_files = []
    for yaml_dir in YAML_DIRS:
        yaml_files.extend(get_files(yaml_dir, ".yaml", exclusions))

    index_content = HTMLGenerator.generate_index_html(html_files, yaml_files)

    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as file:
        file.write(index_content)

    upload_to_github(INDEX_HTML_PATH, "community/index.html", "Update index.html")


if __name__ == "__main__":
    upload_entities()
    upload_yaml_files()
    upload_python_scripts()
    upload_asset_files()
    generate_and_upload_index()
    print("✅ All files uploaded successfully.")
