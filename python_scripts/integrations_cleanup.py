import requests
import yaml
from secret_manager import SecretsManager  # Import the SecretsManager class

# Function to delete a config entry from Home Assistant
def delete_config_entry(entry_id, ha_url, ha_token):
    """
    Deletes a config entry in Home Assistant by its ID.

    Args:
        entry_id (str): The Config Entry ID to delete.
        ha_url (str): Base URL of the Home Assistant instance.
        ha_token (str): Long-lived access token for authentication.

    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    url = f"{ha_url}/api/config/config_entries/entry/{entry_id}"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }

    response = requests.delete(url, headers=headers)
    if response.status_code == 200:
        print(f"Successfully deleted entry {entry_id}.")
        return True
    else:
        print(f"Failed to delete entry {entry_id}: {response.status_code} - {response.text}")
        return False

# Function to interpret user confirmation
def get_confirmation(prompt):
    """
    Prompts the user for confirmation and interprets the response.

    Args:
        prompt (str): The prompt text.

    Returns:
        bool: True for yes, False for no.
    """
    response = input(prompt).strip().lower()
    if response in ["y", "yes", ""]:
        return True
    elif response in ["n", "no"]:
        return False
    else:
        print("Invalid input. Please enter 'y', 'yes', or press Enter for yes; 'n' or 'no' for no.")
        return get_confirmation(prompt)

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

        # Filter for unloaded integrations
        unloaded_integrations = [
            entry for entry in config_entries if entry.get("state") == "not_loaded"
        ]

        print(f"Found {len(unloaded_integrations)} unloaded integrations:")
        for entry in unloaded_integrations:
            print(f"- {entry['domain']} (Config Entry ID: {entry['entry_id']})")

        # Confirm and delete each unloaded integration
        for entry in unloaded_integrations:
            if get_confirmation(f"Do you want to delete {entry['domain']} (ID: {entry['entry_id']})? (y/n): "):
                delete_config_entry(entry["entry_id"], HA_URL, HA_TOKEN)
            else:
                print(f"Skipped {entry['domain']}.")

    else:
        print(f"Failed to fetch config entries: {response.status_code} - {response.text}")

