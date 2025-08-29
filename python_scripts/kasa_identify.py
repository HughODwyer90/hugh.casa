import requests, json
from secret_manager import SecretsManager

secrets = SecretsManager()
EMAIL = secrets["ha_email"].strip()
PASS  = secrets["ha_pass"]
UUID  = secrets["terminal_uuid"]
BASE  = "https://eu-wap.tplinkcloud.com"  # EU region

def kasa_login():
    payload = {
        "method": "login",
        "params": {
            "appType": "Tapo_Ios",   # required for API to work
            "cloudUserName": EMAIL,
            "cloudPassword": PASS,
            "terminalUUID": UUID,
            "locale": "en_US",
        }
    }
    r = requests.post(BASE, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("error_code") != 0:
        raise RuntimeError(f"Login failed: {data}")
    token = data["result"]["token"]
    print(f"\n== Login successful ==")
    print("Token:", token)
    return token

def api(token, payload):
    url = f"{BASE}/?token={token}"
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def get_device_list(token):
    data = api(token, {"method": "getDeviceList"})
    if data.get("error_code") != 0:
        raise RuntimeError(f"getDeviceList error: {data}")
    return data["result"]["deviceList"]

def check_fw(token, device_id):
    payload = {
        "method": "passthrough",
        "params": {
            "deviceId": device_id,
            "requestData": json.dumps({
                "system": {"get_sysinfo": {}},
                "cnCloud": {"getFirmwareList": {}}
            })
        }
    }
    data = api(token, payload)
    res = data.get("result", {})
    if "responseData" not in res:
        return None
    inner = json.loads(res["responseData"])
    return inner  # full dump (contains sysinfo + fw info)

def main():
    token = kasa_login()
    devices = get_device_list(token)

    if not devices:
        print("No devices found.")
        return

    print(f"\n== Devices found ({len(devices)}) ==")
    for d in devices:
        alias = d.get("alias")
        dev_id = d.get("deviceId")
        dtype  = d.get("deviceType")
        model  = d.get("deviceModel") or dtype
        status = "Online" if d.get("status") == 1 else "Offline"
        ip     = d.get("ip", "Unknown")

        print(f"\n{alias} [{model}]")
        print(f"  Device ID : {dev_id}")
        print(f"  Type      : {dtype}")
        print(f"  Status    : {status}")
        print(f"  IP        : {ip}")

        try:
            fwdata = check_fw(token, dev_id)
            if not fwdata:
                print("  Firmware  : not available (offline or unsupported)")
                continue
            sysinfo = fwdata.get("system", {}).get("get_sysinfo", {})
            fwinfo  = fwdata.get("cnCloud", {}).get("getFirmwareList", {})
            cur = sysinfo.get("sw_ver")
            latest = fwinfo.get("fwList", [{}])[0].get("version") if fwinfo else None
            notes  = fwinfo.get("fwList", [{}])[0].get("release_note") if fwinfo else None
            print(f"  Current FW: {cur}")
            print(f"  Latest FW : {latest or '—'}")
            print(f"  Update?   : {'YES' if latest and latest != cur else 'No'}")
            if notes:
                print(f"  Notes     : {notes[:150]}{'…' if len(notes) > 150 else ''}")
            # dump raw JSON too
            print("  Raw fwdata:", json.dumps(fwdata, indent=2)[:600], "...")
        except Exception as e:
            print(f"  Firmware check failed: {e}")

if __name__ == "__main__":
    main()
