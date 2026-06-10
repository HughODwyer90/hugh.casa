import requests
import re
import time
from datetime import datetime
from secret_manager import SecretsManager

secrets = SecretsManager()

# Home Assistant
HOME_ASSISTANT_URL = "http://homeassistant.local:8123"
ENTITY_ID = "input_text.liverpool_tv_channel"
EPL_STATS_ENTITY = "input_text.epl_player_stats"
UCL_STATS_ENTITY = "input_text.ucl_player_stats"
ACCESS_TOKEN = secrets["ha_access_token"]

# Livescore config
excluded_keywords = {"Viaplay", "Discovery", "Ziggo", "Caliente", "Diema", "HBO", "Amazon"}
base_url = "https://www.livescore.com/football/team/liverpool/3340/fixtures"

# UEFA config
UCL_BASE = "https://compstats.uefa.com/v1/player-ranking"
UCL_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

LIVERPOOL_NAMES = {"Liverpool"}
SURNAME_PARTICLES = {
    "da", "de", "del", "della", "di", "do", "dos", "du",
    "la", "le", "van", "von", "der", "den", "ter", "ten",
    "bin", "ibn", "al", "el", "st", "st."
}

# --- Helpers ---
def extract_surname(full_name: str) -> str:
    """Extract surname (with particles) from a full name (Unicode-safe)."""
    if not full_name:
        return ""
    parts = re.findall(r"\w+['.-]?", full_name.strip(), flags=re.UNICODE)
    if not parts:
        return full_name.strip()
    surname_parts = [parts[-1]]
    i = len(parts) - 2
    while i >= 0 and parts[i].lower().strip(".") in SURNAME_PARTICLES:
        surname_parts.insert(0, parts[i])
        i -= 1
    return " ".join(surname_parts)


def post_state(entity_id: str, state: str, attributes=None):
    url = f"{HOME_ASSISTANT_URL}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"state": state}
    if attributes:
        payload["attributes"] = attributes
    r = requests.post(url, json=payload, headers=headers, timeout=(3, 6))
    r.raise_for_status()
    return r.json()


def current_season_year() -> int:
    now = datetime.now()
    return now.year if now.month >= 7 else now.year - 1


# --- TV channel fetch ---
def fetch_tv_channel():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        build_id = None
        script_tags = re.findall(r"<script.*?>(.*?)</script>", response.text, re.DOTALL)
        for script_content in script_tags:
            match = re.search(r"['\"]([\w\-]+)['\"],\s*'prod'", script_content)
            if match:
                build_id = match.group(1)
                break
        if not build_id:
            return
        api_url = (
            f"https://www.livescore.com/_next/data/{build_id}/en/football/team/liverpool/3340/fixtures.json"
            "?sport=football&teamName=liverpool&teamId=3340"
        )
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        events = data.get("pageProps", {}).get("initialData", {}).get("eventsByMatchType", [{}])[0].get("Events", [])
        now_ms = time.time() * 1000
        next_game = next((e for e in events if e.get("Esd") > now_ms), None)
        if next_game and "Media" in next_game and "112" in next_game["Media"]:
            tv_channels = [
                m["eventId"] for m in next_game["Media"]["112"] if m.get("type") == "TV_CHANNEL"
            ]
            filtered = [ch for ch in tv_channels if not any(k in ch for k in excluded_keywords)]
            result = ", ".join(filtered[:3]) if filtered else "No TV channel listed"
            post_state(ENTITY_ID, result)
        else:
            post_state(ENTITY_ID, "No TV channel information available")
    except Exception as e:
        post_state(ENTITY_ID, f"Error: {e}")


# --- Premier League ---
PULSE_BASE = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v2"

def pulselive_headers():
    return {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def fetch_pl_leaderboard_raw(metric: str, limit: int = 50, offset: int = 0):
    season = current_season_year()
    url = (
        f"{PULSE_BASE}/competitions/8/seasons/{season}/players/stats/leaderboard"
        f"?_sort={metric}:desc&_limit={limit}&_offset={offset}"
    )
    try:
        r = requests.get(url, headers=pulselive_headers(), timeout=(3, 6))
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception:
        return []


def fetch_goalkeepers(metric: str, needed: int = 5, batch: int = 50):
    collected, offset = [], 0
    while len(collected) < needed:
        data = fetch_pl_leaderboard_raw(metric, limit=batch, offset=offset)
        if not data:
            break
        for x in data:
            md = x.get("playerMetadata", {}) or {}
            tm = md.get("currentTeam", {}) or {}
            if md.get("position") != "Goalkeeper":
                continue
            collected.append({
                "name": extract_surname(md.get("name", "")),
                "team": tm.get("shortName") or tm.get("name"),
                "value": int((x.get("stats", {}) or {}).get("cleanSheets", 0)),
            })
            if len(collected) >= needed:
                break
        offset += batch
    return collected


def fetch_lfc_top(metric: str, batch: int = 50):
    """Keep paging until a Liverpool player is found for the given metric."""
    offset = 0
    while True:
        data = fetch_pl_leaderboard_raw(metric, limit=batch, offset=offset)
        if not data:
            return None
        for x in data:
            md = x.get("playerMetadata", {}) or {}
            tm = md.get("currentTeam", {}) or {}
            if (tm.get("shortName") or tm.get("name")) in LIVERPOOL_NAMES:
                return {
                    "name": extract_surname(md.get("name", "")),
                    "team": tm.get("shortName") or tm.get("name"),
                    "value": int((x.get("stats", {}) or {}).get(metric, 0)),
                }
        offset += batch


def update_pl_leaders_sensor():
    goals_raw = fetch_pl_leaderboard_raw("goals", 50)
    assists_raw = fetch_pl_leaderboard_raw("goal_assists", 50)
    sheets5 = fetch_goalkeepers("clean_sheets", needed=5)

    goals = [{
        "name": extract_surname(x["playerMetadata"]["name"]),
        "team": x["playerMetadata"]["currentTeam"]["shortName"],
        "value": int(x["stats"]["goals"])
    } for x in goals_raw[:5]]

    assists = [{
        "name": extract_surname(x["playerMetadata"]["name"]),
        "team": x["playerMetadata"]["currentTeam"]["shortName"],
        "value": int(x["stats"]["goalAssists"])
    } for x in assists_raw[:5]]

    league_top = goals[0] if goals else None
    lfc_top = fetch_lfc_top("goals")

    state = "unavailable"
    if league_top and lfc_top:
        if league_top["team"] in LIVERPOOL_NAMES:
            second = goals[1] if len(goals) > 1 else None
            if second:
                diff = league_top["value"] - second["value"]
                state = f"{league_top['name']}: {league_top['value']} (+{diff} {second['name']})"
            else:
                state = f"{league_top['name']}: {league_top['value']} (no 2nd)"
        else:
            diff = league_top["value"] - lfc_top["value"]
            state = f"{league_top['name']}: {league_top['value']} (-{diff} {lfc_top['name']})"
    elif league_top:
        state = f"{league_top['name']}: {league_top['value']} (LFC top unknown)"
    elif lfc_top:
        state = f"{lfc_top['name']}: {lfc_top['value']} (2nd unknown)"

    attrs = {"friendly_name": "Player Stats (EPL)", "icon": "mdi:trophy", "GOALS": ""}
    for i in range(1, 6):
        if i <= len(goals):
            p = goals[i-1]
            attrs[f"g{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
        else:
            attrs[f"g{i}"] = "N/A"

    attrs["ASSISTS"] = ""
    for i in range(1, 6):
        if i <= len(assists):
            p = assists[i-1]
            attrs[f"a{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
        else:
            attrs[f"a{i}"] = "N/A"

    attrs["CLEAN SHEETS"] = ""
    for i in range(1, 6):
        if i <= len(sheets5):
            p = sheets5[i-1]
            attrs[f"c{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
        else:
            attrs[f"c{i}"] = "N/A"

    post_state(EPL_STATS_ENTITY, state, attrs)
    return state


# --- Champions League ---
def fetch_ucl_goalkeepers(stat_type: str = "clean_sheet", needed: int = 5, batch: int = 50):
    season = current_season_year() + 1
    collected, offset = [], 0
    while len(collected) < needed:
        url = (
            f"{UCL_BASE}?competitionId=1&limit={batch}&offset={offset}"
            f"&optionalFields=PLAYER%2CTEAM&order=DESC"
            f"&phase=TOURNAMENT&seasonYear={season}&stats={stat_type}"
        )
        try:
            r = requests.get(url, headers=UCL_HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        if not data:
            break
        for entry in data:
            player, team = entry.get("player", {}), entry.get("team", {})
            stats = entry.get("statistics", [])
            stat_value = next((int(s["value"]) for s in stats if s["name"] == stat_type), 0)
            if player.get("fieldPosition") != "GOALKEEPER":
                continue
            full_name = player.get("internationalName") or player.get("clubShirtName") or ""
            if not full_name:
                continue
            team_name = team.get("translations", {}).get("displayName", {}).get("EN") or ""
            collected.append({"name": extract_surname(full_name), "team": team_name, "value": stat_value})
            if len(collected) >= needed:
                break
        offset += batch
    return collected


def fetch_ucl_leaderboard(stat_type: str, batch: int = 50, limit: int = 200):
    season = current_season_year() + 1
    out, offset = [], 0
    while offset < limit:
        url = (
            f"{UCL_BASE}?competitionId=1&limit={batch}&offset={offset}"
            f"&optionalFields=PLAYER%2CTEAM&order=DESC"
            f"&phase=TOURNAMENT&seasonYear={season}&stats={stat_type}"
        )
        try:
            r = requests.get(url, headers=UCL_HEADERS, timeout=10)
            r.raise_for_status()
            raw = r.json()
        except Exception:
            break
        if not raw:
            break
        for entry in raw:
            player, team = entry.get("player", {}), entry.get("team", {})
            stats = entry.get("statistics", [])
            stat_value = next((int(s["value"]) for s in stats if s["name"] == stat_type), 0)
            full_name = player.get("internationalName") or player.get("clubShirtName") or ""
            team_name = team.get("translations", {}).get("displayName", {}).get("EN") or ""
            if not full_name:
                continue
            out.append({"name": extract_surname(full_name), "team": team_name, "value": stat_value})
        offset += batch
    return out


def fetch_ucl_lfc_top(stat_type: str = "goals", batch: int = 50):
    """Keep paging until Liverpool player is found."""
    season = current_season_year() + 1
    offset = 0
    while True:
        url = (
            f"{UCL_BASE}?competitionId=1&limit={batch}&offset={offset}"
            f"&optionalFields=PLAYER%2CTEAM&order=DESC"
            f"&phase=TOURNAMENT&seasonYear={season}&stats={stat_type}"
        )
        try:
            r = requests.get(url, headers=UCL_HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None
        if not data:
            return None
        for entry in data:
            player, team = entry.get("player", {}), entry.get("team", {})
            if not team.get("translations"):
                continue
            team_name = team["translations"].get("displayName", {}).get("EN")
            if team_name in LIVERPOOL_NAMES:
                stats = entry.get("statistics", [])
                stat_value = next((int(s["value"]) for s in stats if s["name"] == stat_type), 0)
                full_name = player.get("internationalName") or player.get("clubShirtName") or ""
                return {"name": extract_surname(full_name), "team": team_name, "value": stat_value}
        offset += batch


def update_ucl_leaders_sensor():
    goals = fetch_ucl_leaderboard("goals", 50)
    assists = fetch_ucl_leaderboard("assists", 50)
    sheets = fetch_ucl_goalkeepers(needed=5)

    top = goals[0] if goals else None
    lfc_top = fetch_ucl_lfc_top("goals")

    state = "unavailable"
    if top and lfc_top:
        if top["team"] in LIVERPOOL_NAMES:
            second = goals[1] if len(goals) > 1 else None
            if second:
                diff = top["value"] - second["value"]
                state = f"{top['name']}: {top['value']} (+{diff} {second['name']})"
            else:
                state = f"{top['name']}: {top['value']} (no 2nd)"
        else:
            diff = top["value"] - lfc_top["value"]
            state = f"{top['name']}: {top['value']} (-{diff} {lfc_top['name']})"
    elif top:
        state = f"{top['name']}: {top['value']} (LFC top unknown)"
    elif lfc_top:
        state = f"{lfc_top['name']}: {lfc_top['value']} (2nd unknown)"

    attrs = {"friendly_name": "Player Stats (UCL)", "icon": "mdi:soccer", "GOALS": ""}
    for i in range(1, 6):
        if i <= len(goals):
            p = goals[i-1]
            attrs[f"g{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
        else:
            attrs[f"g{i}"] = "N/A"

    attrs["ASSISTS"] = ""
    for i in range(1, 6):
        if i <= len(assists):
            p = assists[i-1]
            attrs[f"a{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
        else:
            attrs[f"a{i}"] = "N/A"

    attrs["CLEAN SHEETS"] = ""
    for i in range(1, 6):
        if i <= len(sheets):
            p = sheets[i-1]
            attrs[f"c{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
        else:
            attrs[f"c{i}"] = "N/A"

    post_state(UCL_STATS_ENTITY, state, attrs)
    return state


# --- RUN ---
print("🔎 Fetching TV channel info...")
fetch_tv_channel()
print("📊 Updating Premier League player stats...")
pl_state = update_pl_leaders_sensor()
print(f"✅ Premier League state: {pl_state}")
print("🌍 Updating Champions League player stats...")
ucl_state = update_ucl_leaders_sensor()
print(f"✅ Champions League state: {ucl_state}")
print("🎯 All updates completed.")