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
    ha_token = secrets["ha_access_token"]
    github_token = secrets["github_token"]
    github_repo = secrets["github_repro"]

    if not ha_token or not github_token or not github_repo:
        print("Error: Missing required secrets in secrets.yaml.")
        exit(1)

    # Initialize GitHubUploader
    uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)

    # Fetch integrations from Home Assistant
    ha_base_url = "http://homeassistant.local:8123"
    ha_headers = {"Authorization": f"Bearer {ha_token}"}
    config_entries_url = f"{ha_base_url}/api/config/config_entries/entry"
    response = requests.get(config_entries_url, headers=ha_headers)

    if response.status_code == 200:
        config_entries = response.json()
        integrations_data = [
            {
                "Integration ID": entry.get("domain", "N/A"),
                "Config Entry ID": entry.get("entry_id", "N/A"),
                "Title": entry.get("title", "N/A"),
                "State": entry.get("state", "unknown"),
                "Source": entry.get("source", "unknown"),
            }
            for entry in config_entries
        ]
        integrations_data.sort(key=lambda x: x["Integration ID"])

        # Generate version timestamp
        version = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")

        # Generate HTML using HTMLGenerator
        html_content = HTMLGenerator.generate_integrations_html(
            integrations_data, len(integrations_data), version
        )

        # Save JSON file
        json_file_path = "/config/www/community/integrations.json"
        with open(json_file_path, "w", encoding="utf-8") as json_file:
            json.dump(integrations_data, json_file, indent=4)

        # Debug: Print timestamp before writing the file
        print(f"Generating integrations.html with timestamp: {version}")

        # Save HTML file
        html_file_path = "/config/www/community/integrations.html"
        with open(html_file_path, "w", encoding="utf-8") as html_file:
            html_file.write(html_content)

        # Debug: Confirm file was written successfully
        print(f"File saved: {html_file_path}")


        # Upload files to GitHub
        try:
            uploader.upload_file(
                local_file_path=html_file_path,
                github_file_path="community/integrations.html",
                commit_message="Update Home Assistant integrations HTML"
            )
            uploader.upload_file(
                local_file_path=json_file_path,
                github_file_path="community/integrations.json",
                commit_message="Update Home Assistant integrations JSON"
            )
        except Exception as e:
            print(f"Error uploading files to GitHub: {e}")

    else:
        print(f"Error fetching integrations: {response.status_code}")

except Exception as e:
    print(f"An unexpected error occurred: {e}")
