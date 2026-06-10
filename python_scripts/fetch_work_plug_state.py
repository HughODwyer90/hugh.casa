import requests
import json
from secret_manager import SecretsManager

secrets = SecretsManager()

# ---- Home Assistant
HOME_ASSISTANT_URL = "http://homeassistant.local:8123"
ENTITY_ID = "input_text.work_plug_state"
HA_ACCESS_TOKEN = secrets["ha_access_token"]

# ---- TP-Link Cloud
CLOUD_USERNAME = secrets["ha_email"].strip()          # strip spaces
CLOUD_PASSWORD = secrets["ha_pass"]
TERMINAL_UUID  = secrets["terminal_uuid"]
TP_API_URL     = secrets["tp_api_url"]
DEVICE_ID      = secrets["tp_device_work"]

def _post(url, payload, timeout=15):
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"Non-JSON response from {url}: {r.text[:300]}")

def _login():
    payload = {
        "method": "login",
        "params": {
            "appType": "Tapo_Ios",          # required now
            "cloudUserName": CLOUD_USERNAME,
            "cloudPassword": CLOUD_PASSWORD,
            "terminalUUID": TERMINAL_UUID,
            "locale": "en_US",
        }
    }
    data = _post(TP_API_URL, payload)
    if data.get("error_code") != 0:
        raise RuntimeError(f"Login failed: {data}")
    token = data["result"]["token"]
    print(f"New token: {token}")
    # cache token into HA (optional but handy)
    headers = {"Authorization": f"Bearer {HA_ACCESS_TOKEN}", "Content-Type": "application/json"}
    update_url = f"{HOME_ASSISTANT_URL}/api/states/input_text.kasa_token"
    requests.post(update_url, json={"state": token}, headers=headers, timeout=10).raise_for_status()
    print("Updated token in Home Assistant.")
    return token

def fetch_plug_state(token, retry=True):
    payload = {
        "method": "passthrough",
        "params": {
            "deviceId": DEVICE_ID,
            "requestData": json.dumps({"system": {"get_sysinfo": {}}})
        }
    }
    url = f"{TP_API_URL}/?token={token}"
    data = _post(url, payload)

    # Handle token expiry gracefully (some backends use error_code 9999 / or msg contains 'Token expired')
    if data.get("error_code") and retry:
        msg = str(data)
        if "Token" in msg and "expire" in msg.lower():
            print("Token expired, re-authenticating…")
            return fetch_plug_state(_login(), retry=False)
        raise RuntimeError(f"passthrough error: {data}")

    try:
        rd = data["result"]["responseData"]
        sysinfo = json.loads(rd)["system"]["get_sysinfo"]
        rs = sysinfo.get("relay_state", -1)
        return "On" if rs == 1 else "Off" if rs == 0 else "Unavailable"
    except KeyError as e:
        raise RuntimeError(f"Malformed response (missing {e}): {data}")
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"Bad responseData JSON: {e}; outer={data}")

def update_home_assistant(state):
    url = f"{HOME_ASSISTANT_URL}/api/states/{ENTITY_ID}"
    headers = {"Authorization": f"Bearer {HA_ACCESS_TOKEN}", "Content-Type": "application/json"}
    requests.post(url, json={"state": state}, headers=headers, timeout=10).raise_for_status()
    print(f"Successfully updated {ENTITY_ID} to: {state}")

def main():
    try:
        print("Authenticating with TP-Link Kasa cloud…")
        token = _login()
        print(f"Successfully retrieved token: {token}")

        print("Fetching plug state…")
        state = fetch_plug_state(token)
        print(f"Plug state: {state}")

        print("Updating Home Assistant…")
        update_home_assistant(state)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
