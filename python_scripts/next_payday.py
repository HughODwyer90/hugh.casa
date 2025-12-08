from datetime import date, timedelta
import requests
from secret_manager import SecretsManager

# --- Home Assistant setup ---
secrets = SecretsManager()
HOME_ASSISTANT_URL = "http://homeassistant.local:8123"
ACCESS_TOKEN = secrets["ha_access_token"]

INPUT_DATETIME_ENTITY = "input_datetime.next_pay_day"
OVERRIDE_ENTITY = "input_datetime.override_pay_day"


# ---------------------------------------------------------------------
# Helper: Read HA input_datetime
# ---------------------------------------------------------------------
def get_input_datetime(entity_id: str):
    url = f"{HOME_ASSISTANT_URL}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        raw = data.get("state")
        print(f"[DEBUG] Read {entity_id}: raw='{raw}'")

        if raw in ["unknown", "unavailable", "none", "", None]:
            print(f"[DEBUG] {entity_id} is empty/unset.")
            return None

        parsed = date.fromisoformat(raw)
        print(f"[DEBUG] Parsed {entity_id}: {parsed}")
        return parsed
    except Exception as e:
        print(f"[ERROR] Failed to read {entity_id}: {e}")
        return None


def set_input_datetime(entity_id: str, dt: date):
    url = f"{HOME_ASSISTANT_URL}/api/services/input_datetime/set_datetime"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"entity_id": entity_id, "date": dt.strftime("%Y-%m-%d")}
    print(f"[DEBUG] Writing {entity_id} = {dt}")

    r = requests.post(url, json=payload, headers=headers, timeout=5)
    try:
        r.raise_for_status()
        print(f"[DEBUG] Successfully updated {entity_id}.")
    except Exception as e:
        print(f"[ERROR] Failed to update {entity_id}: {e}")
    return r.json() if r.text else None


# ---------------------------------------------------------------------
# HOLIDAY RULES
# ---------------------------------------------------------------------

def october_bank_holiday(year: int) -> date:
    d = date(year, 10, 31)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    print(f"[DEBUG] October bank holiday {year}: {d}")
    return d


def december_holidays(year: int):
    d25 = date(year, 12, 25)
    d26 = date(year, 12, 26)
    hols = {d25, d26}

    if d25.weekday() == 5:
        hols.add(d25 + timedelta(days=2))
    elif d25.weekday() == 6:
        hols.add(d25 + timedelta(days=1))

    if d26.weekday() == 5:
        hols.add(d26 + timedelta(days=2))
    elif d26.weekday() == 6:
        hols.add(d26 + timedelta(days=1))

    print(f"[DEBUG] December holidays {year}: {sorted(hols)}")
    return hols


# ---------------------------------------------------------------------
# WORKING DAYS
# ---------------------------------------------------------------------

def working_days_for_month(year: int, month: int):
    first = date(year, month, 1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    hols = set()
    if month == 10:
        hols.add(october_bank_holiday(year))
    if month == 12:
        hols |= december_holidays(year)

    days = []
    d = first
    while d <= last:
        if d.weekday() < 5 and d not in hols:
            days.append(d)
        d += timedelta(days=1)

    print(f"[DEBUG] Working days for {year}-{month:02d}: {days}")
    return days


def third_last_working_day(year: int, month: int):
    days = working_days_for_month(year, month)
    if len(days) < 3:
        print(f"[WARN] Less than 3 working days in {year}-{month:02d}")
        return None
    result = days[-3]
    print(f"[DEBUG] Third-last working day for {year}-{month:02d}: {result}")
    return result


# ---------------------------------------------------------------------
# DECEMBER SPECIAL RULE
# ---------------------------------------------------------------------

def december_override_payday(year: int) -> date:
    d = date(year, 12, 23)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    print(f"[DEBUG] December override payday {year}: {d}")
    return d


# ---------------------------------------------------------------------
# MAIN LOGIC
# ---------------------------------------------------------------------

def compute_next_payday():
    today = date.today()
    print(f"[DEBUG] Today: {today}")

    # --- 1. Try override in HA ---
    override = get_input_datetime(OVERRIDE_ENTITY)
    if override:
        print(f"[DEBUG] Found override: {override}")
        if override >= today:
            print("[DEBUG] Using override payday.")
            return override
        else:
            print("[DEBUG] Override exists but is in the past. Ignoring.")

    # --- 2. December special rule ---
    if today.month == 12:
        dec_pd = december_override_payday(today.year)
        if today <= dec_pd:
            print(f"[DEBUG] Using December override payday: {dec_pd}")
            return dec_pd
        else:
            print("[DEBUG] December payday passed, moving to January…")
            return third_last_working_day(today.year + 1, 1)

    # --- 3. Normal rule (Jan–Nov): third-last working day ---
    y, m = today.year, today.month
    payday = third_last_working_day(y, m)
    print(f"[DEBUG] Normal payday computed: {payday}")

    if payday is None or today > payday:
        print("[DEBUG] Payday passed or missing → shifting to next month.")
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
        payday = third_last_working_day(y, m)
        print(f"[DEBUG] Next-month payday: {payday}")

    return payday


# ---------------------------------------------------------------------
# EXECUTE
# ---------------------------------------------------------------------

payday = compute_next_payday()

if payday is None:
    print("[ERROR] Payday computation failed. Setting fallback date = today.")
    set_input_datetime(INPUT_DATETIME_ENTITY, date.today())
else:
    print(f"[INFO] Final computed next payday: {payday}")
    set_input_datetime(INPUT_DATETIME_ENTITY, payday)

print(f"[INFO] Script completed. Next pay day set to {payday}")
