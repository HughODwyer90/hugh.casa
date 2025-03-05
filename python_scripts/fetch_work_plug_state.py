import requests
import json
import yaml
from secret_manager import SecretsManager  # Import the SecretsManager class

secrets = SecretsManager()
# Home Assistant Details
HOME_ASSISTANT_URL = "http://homeassistant.local:8123"  # Your Home Assistant URL
ENTITY_ID = "input_text.work_plug_state"  # Your input_text entity ID
HA_ACCESS_TOKEN = secrets["ha_access_token"]

# TP-Link Kasa Cloud Credentials
CLOUD_USERNAME = secrets["ha_email"]
CLOUD_PASSWORD = secrets["ha_pass"]
TERMINAL_UUID = secrets["terminal_uuid"]
TP_API_URL = secrets["tp_api_url"]
DEVICE_ID = secrets["tp_device_work"]

def get_token():
    """Retrieve a fresh TP-Link Kasa cloud token and update Home Assistant."""
    payload = {
        "method": "login",
        "params": {
            "appType": "Kasa_Android",
            "cloudPassword": CLOUD_PASSWORD,
            "cloudUserName": CLOUD_USERNAME,
            "terminalUUID": TERMINAL_UUID,
        }
    }
    response = requests.post(TP_API_URL, json=payload, timeout=10)
    response_data = response.json()
    
    if response_data.get("error_code") == 0:
        token = response_data["result"]["token"]
        print(f"New token: {token}")

        # Store token in Home Assistant
        headers = {
            "Authorization": f"Bearer {HA_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        update_url = f"{HOME_ASSISTANT_URL}/api/states/input_text.kasa_token"
        update_payload = {"state": token}

        ha_response = requests.post(update_url, json=update_payload, headers=headers, timeout=10)
        ha_response.raise_for_status()
        print("Updated token in Home Assistant.")

        return token
    else:
        raise Exception(f"Error during login: {response_data.get('msg', 'Unknown error')}")


def fetch_plug_state(token):
    """Fetch the current state of the TP-Link plug."""
    payload = {
        "method": "passthrough",
        "params": {
            "deviceId": DEVICE_ID,
            "requestData": json.dumps({ "system": { "get_sysinfo": {} } })
        }
    }
    url_with_token = f"{TP_API_URL}/?token={token}"
    response = requests.post(url_with_token, json=payload, timeout=10)
    response.raise_for_status()
    data = response.json()
    if "result" in data and "responseData" in data["result"]:
        response_data = json.loads(data["result"]["responseData"])
        relay_state = response_data["system"]["get_sysinfo"].get("relay_state", -1)
        return "On" if relay_state == 1 else "Off" if relay_state == 0 else "Unavailable"
    else:
        raise Exception("Malformed response data from TP-Link API.")

def update_home_assistant(state):
    """Update the state in Home Assistant."""
    url = f"{HOME_ASSISTANT_URL}/api/states/{ENTITY_ID}"
    headers = {
        "Authorization": f"Bearer {HA_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"state": state}
    response = requests.post(url, json=data, headers=headers, timeout=10)
    response.raise_for_status()
    print(f"Successfully updated Home Assistant entity '{ENTITY_ID}' to: {state}")

def main():
    try:
        print("Authenticating with TP-Link Kasa cloud...")
        token = get_token()
        print(f"Successfully retrieved token: {token}")

        print("Fetching plug state...")
        state = fetch_plug_state(token)
        print(f"Plug state: {state}")

        print("Updating Home Assistant...")
        update_home_assistant(state)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
