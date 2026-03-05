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


# ======================
# HOME ASSISTANT HELPERS
# ======================

def post_state(entity_id: str, state, attributes=None):
    url = f"{HOME_ASSISTANT_URL}/api/states/{entity_id}"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {"state": str(state)}

    if attributes:
        payload["attributes"] = attributes

    r = requests.post(url, json=payload, headers=headers, timeout=(3, 10))
    r.raise_for_status()


def call_service(domain: str, service: str, data: dict):
    url = f"{HOME_ASSISTANT_URL}/api/services/{domain}/{service}"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    r = requests.post(url, json=data, headers=headers, timeout=(3, 10))
    r.raise_for_status()


def get_state(entity_id: str):
    url = f"{HOME_ASSISTANT_URL}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

    r = requests.get(url, headers=headers, timeout=(3, 10))
    r.raise_for_status()

    return r.json()


def fmt_entity(entity_id: str):
    try:
        j = get_state(entity_id)
        return f"{entity_id} = {j.get('state')} (last_changed: {j.get('last_changed')})"
    except Exception as e:
        return f"{entity_id} = <error> ({e})"


def get_ha_float(entity_id: str) -> float:
    try:
        j = get_state(entity_id)
        return float(j.get("state") or 0)
    except Exception:
        return 0


# ======================
# TIME PARSER
# ======================

def parse_ibkr_time(ts: str):
    """
    IBKR: 20260304;122721 (US/Eastern)
    Convert to Europe/Dublin
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

    for _ in range(30):

        r = requests.get(
            GET_STATEMENT_URL,
            params={"t": IBKR_TOKEN, "q": ref, "v": 3},
            timeout=30
        )

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
    if when_generated:
        _, _, dt_obj = parse_ibkr_time(when_generated)

    pos = next(
        (p for p in root.findall(".//OpenPosition") if p.attrib.get("symbol") == "VWCE"),
        None
    )

    if pos is None:

        print("No VWCE position found")

        post_state(ENTITY_QTY, 0)
        post_state(ENTITY_COST, 0)

        if when_generated:
            d, t, _ = parse_ibkr_time(when_generated)

            existing = get_state(ENTITY_UPDATED).get("state")
            new_state = f"{d} {t}"

            if existing != new_state:
                call_service(
                    "input_datetime",
                    "set_datetime",
                    {"entity_id": ENTITY_UPDATED, "date": d, "time": t}
                )
            else:
                print("IBKR last update unchanged; skipping input_datetime update")

        return

    qty = float(pos.attrib.get("position", 0))
    mark_price = float(pos.attrib.get("markPrice", 0))
    position_value = float(pos.attrib.get("positionValue", 0))
    cost_basis_money = float(pos.attrib.get("costBasisMoney", 0))
    unrealized = float(pos.attrib.get("fifoPnlUnrealized", 0))

    # ======================
    # HA STATE BEFORE
    # ======================

    print("HOME ASSISTANT (before)")
    print(fmt_entity(ENTITY_QTY))
    print(fmt_entity(ENTITY_COST))
    print(fmt_entity(ENTITY_UPDATED))
    print("")

    # ======================
    # UPDATE HA
    # ======================

    post_state(ENTITY_QTY, qty)

    post_state(ENTITY_COST, round(cost_basis_money, 2))

    if when_generated:

        d, t, _ = parse_ibkr_time(when_generated)

        existing = get_state(ENTITY_UPDATED).get("state")
        new_state = f"{d} {t}"

        if existing != new_state:
            call_service(
                "input_datetime",
                "set_datetime",
                {"entity_id": ENTITY_UPDATED, "date": d, "time": t}
            )
        else:
            print("IBKR last update unchanged; skipping input_datetime update")

    # ======================
    # HA STATE AFTER
    # ======================

    print("HOME ASSISTANT (after)")
    print(fmt_entity(ENTITY_QTY))
    print(fmt_entity(ENTITY_COST))
    print(fmt_entity(ENTITY_UPDATED))
    print("")

    # ======================
    # FLEX OUTPUT
    # ======================

    print("")
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

        live_value = qty * yahoo_price
        live_profit = live_value - cost_basis_money

        print("LIVE VALUE (via Yahoo Finance)")
        print("----------------------------")
        print("Yahoo Price: €", yahoo_price)
        print("Value (qty * price): €", round(live_value, 2))
        print("Profit (value - cost): €", round(live_profit, 2))
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