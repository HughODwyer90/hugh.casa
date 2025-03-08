import requests
import yaml
from secret_manager import SecretsManager  # Import the SecretsManager class

secrets = SecretsManager()
# TP-Link Kasa cloud credentials
CLOUD_USERNAME = secrets["ha_email"]
CLOUD_PASSWORD = secrets["ha_pass"]
TERMINAL_UUID = secrets["terminal_uuid"]
API_URL = secrets["tp_api_url"]

def get_token():
    """Authenticate with TP-Link cloud and retrieve the token."""
    payload = {
        "method": "login",
        "params": {
            "appType": "Kasa_Android",
            "cloudPassword": CLOUD_PASSWORD,
            "cloudUserName": CLOUD_USERNAME,
            "terminalUUID": TERMINAL_UUID,
        }
    }
    response = requests.post(API_URL, json=payload)
    response_data = response.json()
    if response_data.get("error_code") == 0:
        return response_data["result"]["token"]
    else:
        raise Exception(f"Error during login: {response_data.get('msg', 'Unknown error')}")

def list_devices():
    """Ensure token is always up-to-date and list all devices linked to the TP-Link account."""
    token = get_token()
    list_payload = {
        "method": "getDeviceList"
    }
    url_with_token = f"{API_URL}/?token={token}"
    response = requests.post(url_with_token, json=list_payload)
    response_data = response.json()
    if response_data.get("error_code") == 0:
        devices = response_data["result"]["deviceList"]
        print(f"Token: {token}")
        print("Devices found:")
        for device in devices:
            print(f"Name: {device['alias']}")
            print(f"Device ID: {device['deviceId']}")
            print(f"Type: {device['deviceType']}")
            print(f"Status: {'Online' if device['status'] == 1 else 'Offline'}")
            print(f"IP Address: {device.get('ip', 'Unknown')}")
            print("=" * 40)
    else:
        raise Exception(f"Error retrieving device list: {response_data.get('msg', 'Unknown error')}")

def main():
    try:
        print("Logging into TP-Link Kasa cloud and fetching device list...")
        list_devices()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
