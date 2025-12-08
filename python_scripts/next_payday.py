from datetime import date, timedelta
import requests
from secret_manager import SecretsManager

# --- Home Assistant setup ---
secrets = SecretsManager()
HOME_ASSISTANT_URL = "http://homeassistant.local:8123"
ACCESS_TOKEN = secrets["ha_access_token"]

INPUT_DATETIME_ENTITY = "input_datetime.next_pay_day"
OVERRIDE_ENTITY = "input_datetime.override_pay_day"


def get_input_datetime(entity_id: str):
    """Retrieve input_datetime value (returns None if empty/unset)."""
    url = f"{HOME_ASSISTANT_URL}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

    r = requests.get(url, headers=headers, timeout=5)
    r.raise_for_status()
    data = r.json()

    val = data.get("state")
    if val in ["unknown", "unavailable", "none", "", None]:
        return None

    try:
        return date.fromisoformat(val)
    except Exception:
        return None


def set_input_datetime(entity_id: str, dt: date):
    url = f"{HOME_ASSISTANT_URL}/api/services/input_datetime/set_datetime"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"entity_id": entity_id, "date": dt.strftime("%Y-%m-%d")}
    r = requests.post(url, json=payload, headers=headers, timeout=5)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------
# HOLIDAY RULES
# ---------------------------------------------------------------------

def october_bank_holiday(year: int) -> date:
    d = date(year, 10, 31)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return d


def december_holidays(year: int):
    d25 = date(year, 12, 25)
    d26 = date(year, 12, 26)

    hols = {d25, d26}

    # Observed Christmas
    if d25.weekday() == 5:
        hols.add(d25 + timedelta(days=2))
    elif d25.weekday() == 6:
        hols.add(d25 + timedelta(days=1))

    # Observed St Stephen's Day
    if d26.weekday() == 5:
        hols.add(d26 + timedelta(days=2))
    elif d26.weekday() == 6:
        hols.add(d26 + timedelta(days=1))

    return hols


# ---------------------------------------------------------------------
# WORKING DAY CALCULATIONS
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

    return days


def third_last_working_day(year: int, month: int):
    days = working_days_for_month(year, month)
    if len(days) < 3:
        return None
    return days[-3]


# ---------------------------------------------------------------------
# DECEMBER SPECIAL RULE
# ---------------------------------------------------------------------

def december_override_payday(year: int) -> date:
    """
    Return the last Friday on or before December 23.
    Companies usually pay on this day before Christmas break.
    """
    d = date(year, 12, 23)
    while d.weekday() != 4:  # Friday
        d -= timedelta(days=1)
    return d


# ---------------------------------------------------------------------
# MAIN PAYDAY LOGIC
# ---------------------------------------------------------------------

def compute_next_payday():
    today = date.today()

    # --- 1. Check Home Assistant override ---
    override = get_input_datetime(OVERRIDE_ENTITY)
    if override and override >= today:
        return override

    # --- 2. December special rule ---
    if today.month == 12:
        dec_pd = december_override_payday(today.year)
        if today <= dec_pd:
            return dec_pd
        else:
            # Move to January logic
            return third_last_working_day(today.year + 1, 1)

    # --- 3. Normal rule (Jan–Nov): 3rd last working day ---
    y, m = today.year, today.month
    payday = third_last_working_day(y, m)

    if payday is None or today > payday:
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
        payday = third_last_working_day(y, m)

    return payday


# ---------------------------------------------------------------------
# EXECUTE
# ---------------------------------------------------------------------

payday = compute_next_payday()

if payday is None:
    # Emergency fallback
    set_input_datetime(INPUT_DATETIME_ENTITY, date.today())
else:
    set_input_datetime(INPUT_DATETIME_ENTITY, payday)

print(f"Next pay day set to {payday}")
