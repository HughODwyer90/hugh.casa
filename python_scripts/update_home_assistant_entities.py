import requests
import json
from datetime import datetime
from secret_manager import SecretsManager  # Import the SecretsManager class
from git_uploader import GitHubUploader  # Import the GitHubUploader class
from html_generator import HTMLGenerator  # Import the HTMLGenerator class

# Main script logic
try:
    # Load secrets
    secrets = SecretsManager()

    # Retrieve secrets from the SecretsManager
    ha_token = secrets["long_live_lucifer"]
    github_token = secrets["github_token"]
    github_repo = secrets["github_repro"]

    if not ha_token or not github_token or not github_repo:
        print("Error: Missing required tokens or repository in secrets.yaml.")
        exit(1)

    # Initialize GitHubUploader
    uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)

    # Home Assistant API details
    ha_url = "http://homeassistant.local:8123/api/states"
    ha_headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json"
    }

    # Fetch entities from Home Assistant
    print("Sending request to Home Assistant API...")
    response = requests.get(ha_url, headers=ha_headers, timeout=30)
    print("Response received.")

    if response.status_code == 200:
        entities = response.json()
        total_entities = len(entities)
        print(f"Total entities fetched: {total_entities}")

        # Generate prefixes dynamically from entity IDs
        prefixes = sorted(set(entity['entity_id'].split('.')[0] for entity in entities))

        version = datetime.utcnow().strftime('%Y-%m-%d-%H%M%S')

        # Generate HTML using HTMLGenerator
        html_content = HTMLGenerator.generate_entities_html(entities, total_entities, version, prefixes)

        # Save the HTML content
        local_html_path = "/config/www/community/entities.html"
        with open(local_html_path, "w", encoding="utf-8") as file:
            file.write(html_content)

        # Save JSON file
        local_json_path = "/config/www/community/entities.json"
        with open(local_json_path, "w", encoding="utf-8") as json_file:
            json.dump(entities, json_file, indent=4)

        # Upload HTML to GitHub
        try:
            uploader.upload_file(
                local_file_path=local_html_path,
                github_file_path="community/entities.html",
                commit_message="Update Home Assistant entities list"
            )
        except Exception as e:
            print(f"Error uploading HTML to GitHub: {e}")

        # Upload JSON to GitHub
        try:
            uploader.upload_file(
                local_file_path=local_json_path,
                github_file_path="community/entities.json",
                commit_message="Update Home Assistant entities JSON list"
            )
        except Exception as e:
            print(f"Error uploading JSON to GitHub: {e}")

    else:
        print(f"Error retrieving data from Home Assistant: {response.status_code}")

except Exception as e:
    print(f"An unexpected error occurred: {e}")
