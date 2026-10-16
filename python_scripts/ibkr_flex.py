import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
from secret_manager import SecretsManager

secrets = SecretsManager()

# ======================
# VARIABLES
# ======================

HOME_ASSISTANT_URL = "http://homeassistant.local:8123"
ACCESS_TOKEN = secrets["ha_access_token"]

ENTITY_UPDATED = "input_datetime.ibkr_last_update"

# One entry per holding: IBKR symbol -> HA entities
HOLDINGS = {
    "VWCE": {
        "qty": "input_number.ibkr_vwce_quantity",
        "cost": "input_number.ibkr_vwce_cost_basis",
        "price": "sensor.yahoofinance_vwce_de",
    },
    "RBOT": {
        "qty": "input_number.ibkr_rbot_quantity",
        "cost": "input_number.ibkr_rbot_cost_basis",
        "price": "sensor.yahoofinance_rbot_mi",
    },
    "URNU": {
        "qty": "input_number.ibkr_urnu_quantity",
        "cost": "input_number.ibkr_urnu_cost_basis",
        "price": "sensor.yahoofinance_urnu_mi",
    },
}

IBKR_TOKEN = secrets["ibkr_flex_token"]
IBKR_QUERY_ID = secrets["ibkr_flex_query_id"]

POLL_SECONDS = 3600

SEND_REQUEST_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
GET_STATEMENT_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"

# Tolerances to avoid tiny floating-point rewrites
QTY_EPSILON = 0.00001
MONEY_EPSILON = 0.005


# ======================
# HOME ASSISTANT HELPERS
# ======================

def get_headers():
    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }


def call_service(domain: str, service: str, data: dict):
    url = f"{HOME_ASSISTANT_URL}/api/services/{domain}/{service}"
    r = requests.post(url, json=data, headers=get_headers(), timeout=(3, 10))
    r.raise_for_status()


def get_state(entity_id: str):
    url = f"{HOME_ASSISTANT_URL}/api/states/{entity_id}"
    r = requests.get(url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, timeout=(3, 10))
    r.raise_for_status()
    return r.json()


def fmt_entity(entity_id: str):
    try:
        j = get_state(entity_id)
        return f"{entity_id} = {j.get('state')} (last_changed: {j.get('last_changed')}, last_updated: {j.get('last_updated')})"
    except Exception as e:
        return f"{entity_id} = <error> ({e})"


def get_ha_float(entity_id: str) -> float:
    try:
        j = get_state(entity_id)
        return float(j.get("state") or 0)
    except Exception:
        return 0.0


def set_input_number_if_changed(entity_id: str, new_value: float, epsilon: float):
    current_value = get_ha_float(entity_id)

    if abs(current_value - new_value) > epsilon:
        call_service(
            "input_number",
            "set_value",
            {
                "entity_id": entity_id,
                "value": new_value
            }
        )
        print(f"Updated {entity_id}: {current_value} -> {new_value}")
    else:
        print(f"Skipped {entity_id}: no meaningful change ({current_value} ~= {new_value})")


def set_input_datetime_if_changed(entity_id: str, date_str: str, time_str: str):
    existing = get_state(entity_id).get("state")
    new_state = f"{date_str} {time_str}"

    if existing != new_state:
        call_service(
            "input_datetime",
            "set_datetime",
            {
                "entity_id": entity_id,
                "date": date_str,
                "time": time_str
            }
        )
        print(f"Updated {entity_id}: {existing} -> {new_state}")
    else:
        print(f"Skipped {entity_id}: unchanged ({new_state})")


# ======================
# TIME PARSER
# ======================

def parse_ibkr_time(ts: str):
    """
    IBKR example: 20260304;122721
    Source timezone assumed America/New_York
    Converted to Europe/Dublin
    """
    ibkr_dt = datetime.strptime(ts, "%Y%m%d;%H%M%S").replace(
        tzinfo=ZoneInfo("America/New_York")
    )

    dublin_dt = ibkr_dt.astimezone(ZoneInfo("Europe/Dublin"))

    return (
        dublin_dt.date().isoformat(),
        dublin_dt.time().strftime("%H:%M:%S"),
        dublin_dt
    )


# ======================
# IBKR FLEX
# ======================

def get_flex_xml() -> str:
    params = {
        "t": IBKR_TOKEN,
        "q": IBKR_QUERY_ID,
        "v": 3
    }

    # IBKR temporary errors: 1001 (could not generate), 1018 (too many requests),
    # 1019 (generation in progress). Retry these a few times before giving up.
    RETRYABLE = {"1001", "1018", "1019"}
    attempts = 5

    for attempt in range(1, attempts + 1):
        r = requests.get(SEND_REQUEST_URL, params=params, timeout=30)
        r.raise_for_status()

        root = ET.fromstring(r.text)
        status = (root.findtext("Status") or "").lower()

        if status == "success":
            break

        code = root.findtext("ErrorCode")
        msg = root.findtext("ErrorMessage")

        if code in RETRYABLE and attempt < attempts:
            wait = 30 * attempt
            print(f"Flex request failed ({code} - {msg}), retrying in {wait}s "
                  f"[{attempt}/{attempts}]")
            time.sleep(wait)
            continue

        raise RuntimeError(f"Flex request failed: {code} - {msg}")

    ref = root.findtext("ReferenceCode")
    if not ref:
        raise RuntimeError("Flex request succeeded but no ReferenceCode returned")

    for _ in range(30):
        r = requests.get(
            GET_STATEMENT_URL,
            params={"t": IBKR_TOKEN, "q": ref, "v": 3},
            timeout=30
        )
        r.raise_for_status()

        if "<FlexStatement" in r.text:
            return r.text

        time.sleep(2)

    raise RuntimeError("Flex statement not ready")


# ======================
# PER-HOLDING UPDATE
# ======================

def update_holding(symbol: str, entities: dict, pos):
    print(f"===== {symbol} =====")
    print("HOME ASSISTANT (before)")
    print(fmt_entity(entities["qty"]))
    print(fmt_entity(entities["cost"]))
    print("")

    if pos is None:
        # Not held yet (e.g. URNU before its first buy) or fully sold
        print(f"No {symbol} position found, setting to 0")
        set_input_number_if_changed(entities["qty"], 0.0, QTY_EPSILON)
        set_input_number_if_changed(entities["cost"], 0.0, MONEY_EPSILON)
        print("")
        return

    qty = round(float(pos.attrib.get("position", 0) or 0), 4)
    mark_price = round(float(pos.attrib.get("markPrice", 0) or 0), 2)
    position_value = round(float(pos.attrib.get("positionValue", 0) or 0), 2)
    cost_basis_money = round(float(pos.attrib.get("costBasisMoney", 0) or 0), 2)
    unrealized = round(float(pos.attrib.get("fifoPnlUnrealized", 0) or 0), 2)

    set_input_number_if_changed(entities["qty"], qty, QTY_EPSILON)
    set_input_number_if_changed(entities["cost"], cost_basis_money, MONEY_EPSILON)

    print("")
    print("IBKR FLEX RESULT")
    print("----------------------------")
    print("Shares:", qty)
    print("Mark Price (IBKR): €", mark_price)
    print("Position Value: €", position_value)
    print("Cost Basis: €", cost_basis_money)
    print("Unrealized P/L: €", unrealized)
    print("----------------------------")

    yahoo_price = get_ha_float(entities["price"])
    if yahoo_price > 0:
        live_value = round(qty * yahoo_price, 2)
        live_profit = round(live_value - cost_basis_money, 2)
        print("LIVE (Yahoo): price €", yahoo_price,
              "| value €", live_value,
              "| profit €", live_profit)
    else:
        print(f"Yahoo price sensor unavailable ({entities['price']})")
    print("")


# ======================
# MAIN
# ======================

def update_from_flex():
    xml = get_flex_xml()
    root = ET.fromstring(xml)

    stmt = root.find(".//FlexStatement")
    when_generated = stmt.attrib.get("whenGenerated") if stmt is not None else ""

    dt_obj = date_str = time_str = None
    if when_generated:
        date_str, time_str, dt_obj = parse_ibkr_time(when_generated)

    positions = {p.attrib.get("symbol"): p for p in root.findall(".//OpenPosition")}

    unknown = set(positions) - set(HOLDINGS)
    if unknown:
        print(f"Note: Flex has positions not tracked in HOLDINGS: {', '.join(sorted(unknown))}")
        print("")

    for symbol, entities in HOLDINGS.items():
        try:
            update_holding(symbol, entities, positions.get(symbol))
        except Exception as e:
            # One failing holding shouldn't stop the others
            print(f"Error updating {symbol}: {e}")
            print("")

    if date_str and time_str:
        set_input_datetime_if_changed(ENTITY_UPDATED, date_str, time_str)

    print(
        "Report Generated (Irish Time):",
        dt_obj.strftime("%Y-%m-%d %H:%M:%S") if dt_obj else "unknown"
    )


# ======================
# RUN
# ======================

if __name__ == "__main__":
    update_from_flex()

    # continuous mode if desired
    # while True:
    #     update_from_flex()
    #     time.sleep(POLL_SECONDS)