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
excluded_keywords = {"Viaplay", "Discovery", "Ziggo", "Caliente", "Diema"}
base_url = "https://www.livescore.com/football/team/liverpool/3340/fixtures"

# UEFA config
UCL_BASE = "https://compstats.uefa.com/v1/player-ranking"
UCL_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

LIVERPOOL_NAMES = {"Liverpool"}
SURNAME_PARTICLES = {
    "da", "de", "del", "della", "di", "do", "dos", "du", "la", "le", "van", "von",
    "der", "den", "ter", "ten", "bin", "ibn", "al", "el", "st", "st."
}


def normalize_name(name: str) -> str:
    replacements = {
        "ı": "i", "İ": "I",
        "ğ": "g", "Ğ": "G",
        "ş": "s", "Ş": "S",
        "ç": "c", "Ç": "C",
        "ö": "o", "Ö": "O",
        "ü": "u", "Ü": "U",
        "á": "a", "Á": "A",
        "é": "e", "É": "E",
        "ñ": "n", "Ñ": "N",
        "à": "a", "è": "e", "ù": "u",
        "â": "a", "ê": "e", "î": "i", "ô": "o", "û": "u",
        "ã": "a", "õ": "o"
    }
    return "".join(replacements.get(char, char) for char in name)


def extract_surname(full_name: str) -> str:
    if not full_name:
        return ""
    parts = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'.-]+", full_name.strip())
    if not parts:
        return normalize_name(full_name.strip())
    surname_parts = [parts[-1]]
    i = len(parts) - 2
    while i >= 0 and parts[i].lower().strip(".") in SURNAME_PARTICLES:
        surname_parts.insert(0, parts[i])
        i -= 1
    return normalize_name(" ".join(surname_parts))


def post_state(entity_id: str, state: str, attributes=None):
    url = f"{HOME_ASSISTANT_URL}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"state": state}
    if attributes:
        payload["attributes"] = attributes
    r = requests.post(url, json=payload, headers=headers, timeout=(3, 6))
    r.raise_for_status()
    return r.json()


def current_season_year() -> int:
    now = datetime.now()
    return now.year if now.month >= 7 else now.year - 1


def fetch_tv_channel():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0 Safari/537.36"
        }
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
            print("No build ID found, skipping.")
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
                m["eventId"]
                for m in next_game["Media"]["112"]
                if m.get("type") == "TV_CHANNEL"
            ]
            filtered = [ch for ch in tv_channels if not any(k in ch for k in excluded_keywords)]
            result = ", ".join(filtered[:3]) if filtered else "No TV channel listed"
            post_state(ENTITY_ID, result)
        else:
            post_state(ENTITY_ID, "No TV channel information available")
    except Exception as e:
        post_state(ENTITY_ID, f"Error: {e}")


# Premier League
PULSE_BASE = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v2"

def pulselive_headers():
    return {
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://www.premierleague.com",
        "Referer": "https://www.premierleague.com/",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }

def fetch_pl_leaderboard_raw(metric: str, limit: int = 5):
    season = current_season_year()
    url = (
        f"{PULSE_BASE}/competitions/8/seasons/{season}/players/stats/leaderboard"
        f"?_sort={metric}:desc&_limit={limit}"
    )
    try:
        r = requests.get(url, headers=pulselive_headers(), timeout=(3, 6))
        r.raise_for_status()
        return r.json().get("data", [])[:limit]
    except Exception:
        return []

def find_team_top(data: list, team_names=LIVERPOOL_NAMES, metric_key="goals"):
    for x in data:
        md = x.get("playerMetadata", {}) or {}
        tm = md.get("currentTeam", {}) or {}
        team_name = tm.get("shortName") or tm.get("name")
        if team_name in team_names:
            full_name = md.get("name")
            value = int((x.get("stats", {}) or {}).get(metric_key, 0))
            if full_name:
                return {"name": extract_surname(full_name), "team": team_name, "value": value}
    return None

def update_pl_leaders_sensor():
    goals5_raw = fetch_pl_leaderboard_raw("goals", 5)
    assists5_raw = fetch_pl_leaderboard_raw("goal_assists", 5)
    sheets5_raw = fetch_pl_leaderboard_raw("clean_sheets", 20)

    def compact(arr, key, filter_goalkeepers=False):
        out = []
        for x in arr:
            md = x.get("playerMetadata", {}) or {}
            tm = md.get("currentTeam", {}) or {}
            if filter_goalkeepers and md.get("position") != "Goalkeeper":
                continue
            out.append({
                "name": extract_surname(md.get("name", "")),
                "team": tm.get("shortName") or tm.get("name"),
                "value": int((x.get("stats", {}) or {}).get(key, 0)),
            })
            if len(out) >= 5:
                break
        return out

    goals5 = compact(goals5_raw, "goals")
    assists5 = compact(assists5_raw, "goalAssists")
    sheets5 = compact(sheets5_raw, "cleanSheets", filter_goalkeepers=True)

    lfc_scan = fetch_pl_leaderboard_raw("goals", 120)
    lfc_top = find_team_top(lfc_scan, team_names=LIVERPOOL_NAMES, metric_key="goals")
    league_top = goals5[0] if goals5 else None

    def pretty(p): return f"{p['name']}: {p['value']}" if p else "unavailable"

    if lfc_top and league_top and lfc_top["name"] == league_top["name"] and lfc_top["team"] == league_top["team"]:
        second = goals5[1] if len(goals5) > 1 else None
        state = f"{pretty(lfc_top)} (+{max(lfc_top['value'] - second['value'], 0)} {second['name']})" if second else pretty(lfc_top)
    elif league_top and lfc_top:
        state = f"{pretty(league_top)} (-{max(league_top['value'] - lfc_top['value'], 0)} {lfc_top['name']})"
    elif league_top:
        state = f"{pretty(league_top)} (LFC top unknown)"
    elif lfc_top:
        state = f"{pretty(lfc_top)} (2nd unknown)"
    else:
        state = "unavailable"

    attrs = {
        "friendly_name": "Player Stats (EPL)",
        "icon": "mdi:trophy",
        "GOALS": "",
    }
    for i, p in enumerate(goals5, 1):
        attrs[f"g{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
    attrs["ASSISTS"] = ""
    for i, p in enumerate(assists5, 1):
        attrs[f"a{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
    attrs["CLEAN SHEETS"] = ""
    for i, p in enumerate(sheets5, 1):
        attrs[f"c{i}"] = f"{p['name']} – {p['team']} – {p['value']}"

    post_state(EPL_STATS_ENTITY, state, attrs)
    return state


# Champions League
def fetch_ucl_leaderboard(stat_type: str, limit: int = 5, filter_goalkeepers=False):
    season = current_season_year() + 1
    url = (
        f"{UCL_BASE}?competitionId=1&limit=50&offset=0"
        f"&optionalFields=PLAYER%2CTEAM&order=DESC"
        f"&phase=TOURNAMENT&seasonYear={season}&stats={stat_type}"
    )
    try:
        r = requests.get(url, headers=UCL_HEADERS, timeout=10)
        r.raise_for_status()
        raw = r.json()
        out = []
        for entry in raw:
            player = entry.get("player", {})
            team = entry.get("team", {})
            stats = entry.get("statistics", [])
            stat_value = next((int(s["value"]) for s in stats if s["name"] == stat_type), 0)
            full_name = player.get("internationalName") or player.get("clubShirtName") or ""
            team_name = team.get("translations", {}).get("displayName", {}).get("EN") or ""
            if filter_goalkeepers and player.get("position") != "Goalkeeper":
                continue
            if not full_name:
                continue
            out.append({
                "name": extract_surname(full_name),
                "team": team_name,
                "value": stat_value,
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print(f"UCL {stat_type} fetch error: {e}")
        return []

def find_liverpool_top(players: list):
    for p in players:
        if p.get("team") in LIVERPOOL_NAMES:
            return p
    return None

def update_ucl_leaders_sensor():
    goals = fetch_ucl_leaderboard("goals")
    assists = fetch_ucl_leaderboard("assists")
    sheets = fetch_ucl_leaderboard("clean_sheet", filter_goalkeepers=True)

    attrs = {
        "friendly_name": "Player Stats (UCL)",
        "icon": "mdi:soccer",
        "GOALS": "",
    }
    for i, p in enumerate(goals, 1):
        attrs[f"g{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
    attrs["ASSISTS"] = ""
    for i, p in enumerate(assists, 1):
        attrs[f"a{i}"] = f"{p['name']} – {p['team']} – {p['value']}"
    attrs["CLEAN SHEETS"] = ""
    for i, p in enumerate(sheets, 1):
        attrs[f"c{i}"] = f"{p['name']} – {p['team']} – {p['value']}"

    top = goals[0] if goals else None
    lfc_top = find_liverpool_top(goals)

    if top and lfc_top and top["name"] == lfc_top["name"] and top["team"] == lfc_top["team"]:
        second = goals[1] if len(goals) > 1 else None
        state = f"{top['name']}: {top['value']} (+{max(top['value'] - second['value'], 0)} {second['name']})" if second else f"{top['name']}: {top['value']}"
    elif top and lfc_top:
        state = f"{top['name']}: {top['value']} (-{max(top['value'] - lfc_top['value'], 0)} {lfc_top['name']})"
    elif top:
        state = f"{top['name']}: {top['value']} (LFC top unknown)"
    elif lfc_top:
        state = f"{lfc_top['name']}: {lfc_top['value']} (2nd unknown)"
    else:
        state = "unavailable"

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