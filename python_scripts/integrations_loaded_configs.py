import requests
from secret_manager import SecretsManager  # Import the SecretsManager class

# Main script
if __name__ == "__main__":
    # Load secrets
    secrets = SecretsManager()
    HA_TOKEN = secrets["ha_access_token"]
    HA_URL = "http://homeassistant.local:8123"  # Update with your Home Assistant URL

    if not HA_TOKEN:
        print("Error: Missing token in secrets.yaml.")
        exit(1)

    # Fetch all config entries
    config_entries_url = f"{HA_URL}/api/config/config_entries/entry"
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    response = requests.get(config_entries_url, headers=headers)

    if response.status_code == 200:
        config_entries = response.json()

        # Filter for loaded integrations
        loaded_integrations = [
            entry for entry in config_entries if entry.get("state") == "loaded"
        ]

        # Sort alphabetically by domain
        loaded_integrations.sort(key=lambda e: e.get("domain", "").lower())

        print(f"Found {len(loaded_integrations)} loaded integrations:\n")
        for entry in loaded_integrations:
            domain = entry.get("domain", "unknown")
            title = entry.get("title", "N/A")
            source = entry.get("source", "N/A")
            entry_id = entry.get("entry_id")
            print(f"- {domain} | Title: {title} | Source: {source} | ID: {entry_id}")

    else:
        print(f"Failed to fetch config entries: {response.status_code} - {response.text}")
