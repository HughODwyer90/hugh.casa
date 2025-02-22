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
        redacted_count = 0  # Counter for redacted entities

        # Process entities: Keep full data for some, redact attributes for others
        processed_entities = []
        for entity in entities:
            entity_id = entity["entity_id"]
            attributes = entity.get("attributes", {})

            # Check if the entity falls into the redacted category
            if (
                entity_id.startswith("device_tracker.")  # Previously excluded device_tracker entities
                or any("device_tracker." in str(value) for value in attributes.values())  # References to device_tracker
                or "gps" in entity_id.lower()  # Previously excluded GPS-related entities
                or entity_id.startswith("zone.")  # Previously excluded zone entities
                or (
                    entity_id.startswith("input_text.") 
                    and attributes.get("mode", "").lower() == "password"
                )  # Previously excluded input_text with mode=password
            ):
                # Keep only entity_id, redact state, and use empty attributes dictionary
                processed_entities.append({
                    "entity_id": entity_id, 
                    "state": "REDACTED", 
                    "attributes": {}
                })
                redacted_count += 1  # Increment redacted counter
            else:
                # Keep full entity data
                processed_entities.append(entity)

        print(f"Total entities fetched: {total_entities}")
        print(f"Total entities after processing: {len(processed_entities)}")
        print(f"Total entities redacted: {redacted_count}")  # Display redacted count

        # Generate prefixes dynamically from processed entities
        prefixes = sorted(set(entity['entity_id'].split('.')[0] for entity in processed_entities))

        version = datetime.utcnow().strftime('%Y-%m-%d-%H%M%S')

        # Generate HTML using HTMLGenerator
        html_content = HTMLGenerator.generate_entities_html(
            processed_entities, total_entities, version, prefixes, redacted_count
        )

        # Save the processed HTML content
        local_html_path = "/config/www/community/entities.html"
        with open(local_html_path, "w", encoding="utf-8") as file:
            file.write(html_content)

        # Save the processed JSON file
        local_json_path = "/config/www/community/entities.json"
        with open(local_json_path, "w", encoding="utf-8") as json_file:
            json.dump(processed_entities, json_file, indent=4)

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
