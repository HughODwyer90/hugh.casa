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

ENTITY_QTY = "input_number.ibkr_vwce_quantity"
ENTITY_COST = "input_number.ibkr_vwce_cost_basis"
ENTITY_UPDATED = "input_datetime.ibkr_last_update"

YAHOO_PRICE_ENTITY = "sensor.yahoofinance_vwce_de"

IBKR_TOKEN = secrets["ibkr_flex_token"]
IBKR_QUERY_ID = secrets["ibkr_flex_query_id"]

POLL_SECONDS = 3600

SEND_REQUEST_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
GET_STATEMENT_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"

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

    r = requests.get(SEND_REQUEST_URL, params=params, timeout=30)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    status = (root.findtext("Status") or "").lower()

    if status != "success":
        code = root.findtext("ErrorCode")
        msg = root.findtext("ErrorMessage")
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
# MAIN PARSER
# ======================

def update_vwce_from_flex():
    xml = get_flex_xml()
    root = ET.fromstring(xml)

    stmt = root.find(".//FlexStatement")
    when_generated = stmt.attrib.get("whenGenerated") if stmt is not None else ""

    dt_obj = None
    date_str = None
    time_str = None

    if when_generated:
        date_str, time_str, dt_obj = parse_ibkr_time(when_generated)

    pos = next(
        (p for p in root.findall(".//OpenPosition") if p.attrib.get("symbol") == "VWCE"),
        None
    )

    print("HOME ASSISTANT (before)")
    print(fmt_entity(ENTITY_QTY))
    print(fmt_entity(ENTITY_COST))
    print(fmt_entity(ENTITY_UPDATED))
    print("")

    if pos is None:
        print("No VWCE position found")

        set_input_number_if_changed(ENTITY_QTY, 0.0, QTY_EPSILON)
        set_input_number_if_changed(ENTITY_COST, 0.0, MONEY_EPSILON)

        if date_str and time_str:
            set_input_datetime_if_changed(ENTITY_UPDATED, date_str, time_str)

        return

    # ======================
    # PARSE FLEX VALUES
    # ======================

    # Keep quantity at 4 decimals if that matches your holdings precision.
    # If IBKR ever gives more and you want to preserve it, increase this.
    qty = round(float(pos.attrib.get("position", 0) or 0), 4)

    # Money values at 2 decimals
    mark_price = round(float(pos.attrib.get("markPrice", 0) or 0), 2)
    position_value = round(float(pos.attrib.get("positionValue", 0) or 0), 2)
    cost_basis_money = round(float(pos.attrib.get("costBasisMoney", 0) or 0), 2)
    unrealized = round(float(pos.attrib.get("fifoPnlUnrealized", 0) or 0), 2)

    # ======================
    # UPDATE HA
    # ======================

    set_input_number_if_changed(ENTITY_QTY, qty, QTY_EPSILON)
    set_input_number_if_changed(ENTITY_COST, cost_basis_money, MONEY_EPSILON)

    if date_str and time_str:
        set_input_datetime_if_changed(ENTITY_UPDATED, date_str, time_str)

    print("")
    print("HOME ASSISTANT (after)")
    print(fmt_entity(ENTITY_QTY))
    print(fmt_entity(ENTITY_COST))
    print(fmt_entity(ENTITY_UPDATED))
    print("")

    # ======================
    # FLEX OUTPUT
    # ======================

    print("IBKR FLEX RESULT")
    print("----------------------------")
    print("Symbol:", "VWCE")
    print("Shares:", qty)
    print("Mark Price (IBKR): €", mark_price)
    print("Position Value: €", position_value)
    print("Cost Basis: €", cost_basis_money)
    print("Unrealized P/L: €", unrealized)
    print(
        "Report Generated (Irish Time):",
        dt_obj.strftime("%Y-%m-%d %H:%M:%S") if dt_obj else "unknown"
    )
    print("----------------------------")
    print("")

    # ======================
    # LIVE PRICE CHECK
    # ======================

    yahoo_price = get_ha_float(YAHOO_PRICE_ENTITY)

    if yahoo_price > 0:
        live_value = round(qty * yahoo_price, 2)
        live_profit = round(live_value - cost_basis_money, 2)

        print("LIVE VALUE (via Yahoo Finance)")
        print("----------------------------")
        print("Yahoo Price: €", yahoo_price)
        print("Value (qty * price): €", live_value)
        print("Profit (value - cost): €", live_profit)
        print("----------------------------")
        print("")
    else:
        print("Yahoo price sensor unavailable")
        print("")


# ======================
# RUN
# ======================

if __name__ == "__main__":
    update_vwce_from_flex()

    # continuous mode if desired
    # while True:
    #     update_vwce_from_flex()
    #     time.sleep(POLL_SECONDS)