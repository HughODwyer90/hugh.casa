import requests
import re
import time
from datetime import datetime
from secret_manager import SecretsManager  # Import the SecretsManager class

secrets = SecretsManager()

# Home Assistant
HOME_ASSISTANT_URL = "http://homeassistant.local:8123"
ENTITY_ID = "input_text.liverpool_tv_channel"  # input_text target for TV channel
ACCESS_TOKEN = secrets["ha_access_token"]

# Livescore (TV channel) config
excluded_keywords = {"Viaplay", "Discovery", "Ziggo", "Caliente", "Diema"}
base_url = "https://www.livescore.com/football/team/liverpool/3340/fixtures"

def post_state(entity_id: str, state: str, attributes: dict | None = None):
    """Create/update an entity state in Home Assistant via the REST API."""
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

def fetch_tv_channel():
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }

        # Get main page
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()

        # Extract build ID
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

        # API URL
        api_url = (
            f"https://www.livescore.com/_next/data/{build_id}"
            f"/en/football/team/liverpool/3340/fixtures.json"
            f"?sport=football&teamName=liverpool&teamId=3340"
        )

        # Fetch JSON
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Extract TV channel information
        if (
            data
            and "pageProps" in data
            and "initialData" in data["pageProps"]
            and "eventsByMatchType" in data["pageProps"]["initialData"]
            and data["pageProps"]["initialData"]["eventsByMatchType"]
        ):
            events = data["pageProps"]["initialData"]["eventsByMatchType"][0]["Events"]
            if events:
                now_ms = time.time() * 1000
                next_game = next((e for e in events if e.get("Esd") > now_ms), None)
                if next_game and "Media" in next_game and "112" in next_game["Media"]:
                    tv_channels = [
                        m["eventId"]
                        for m in next_game["Media"]["112"]
                        if m.get("type") == "TV_CHANNEL"
                    ]
                    if tv_channels:
                        filtered = [
                            ch
                            for ch in tv_channels
                            if not any(k in ch for k in excluded_keywords)
                        ]
                        result = ", ".join(filtered[:3]) if filtered else "No TV channel listed"

                        # Update input_text with channel(s)
                        post_state(ENTITY_ID, result)
                        print(f"TV channels: {result}")
                    else:
                        post_state(ENTITY_ID, "No TV channel listed")
                        print("No TV channel listed for the next game.")
                else:
                    post_state(ENTITY_ID, "No TV channel information available")
                    print("No TV channel information available for the next game.")
            else:
                post_state(ENTITY_ID, "No upcoming games found")
                print("No upcoming games found.")
        else:
            post_state(ENTITY_ID, "API data unavailable")
            print("API data unavailable.")
    except Exception as e:
        post_state(ENTITY_ID, f"Error: {e}")
        print(f"Error: {e}")

# ---------------- Premier League leaders (Top 5) ---------------- #

PULSE_BASE = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v2"
VERBOSE = True

LIVERPOOL_TEAM_ID = "14"
LIVERPOOL_TEAM_NAMES = {"Liverpool"}  # belt & braces

def print_pl_leaders(goals, assists, sheets, season):
    g_top = f"{goals[0]['name']} ({goals[0]['value']})" if goals else "unavailable"
    a_top = f"{assists[0]['name']} ({assists[0]['value']})" if assists else "unavailable"
    c_top = f"{sheets[0]['name']} ({sheets[0]['value']})" if sheets else "unavailable"
    print(f"PL leaders [{season}]: Goals={g_top} | Assists={a_top} | Clean sheets={c_top}")
    if VERBOSE:
        def lines(title, items):
            print(title)
            if not items:
                print("  (none)")
                return
            for i, x in enumerate(items[:5], 1):
                print(f"  {i}. {x['name']} – {x.get('team') or ''} ({x['value']})")
        lines("Top 5 – Goals:", goals)
        lines("Top 5 – Assists:", assists)
        lines("Top 5 – Clean sheets:", sheets)

def current_pl_season_year() -> int:
    now = datetime.now()
    return now.year if now.month >= 7 else now.year - 1

def pulselive_headers():
    return {
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://www.premierleague.com",
        "Referer": "https://www.premierleague.com/",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }

def fetch_pl_leaderboard_raw(metric: str, limit: int = 5):
    season = current_pl_season_year()
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

def find_team_top(data: list, team_id=LIVERPOOL_TEAM_ID, team_names=LIVERPOOL_TEAM_NAMES, metric_key="goals"):
    """Return {'name','team','value'} for the first (highest) entry matching the team."""
    for x in data:
        md = x.get("playerMetadata", {}) or {}
        tm = md.get("currentTeam", {}) or {}
        if tm.get("id") == team_id or tm.get("shortName") in team_names or tm.get("name") in team_names:
            name = md.get("name")
            team = tm.get("shortName") or tm.get("name")
            value = int((x.get("stats", {}) or {}).get(metric_key, 0))
            if name:
                return {"name": name, "team": team, "value": value}
    return None

def fmt_lines(items):
    return [f"{i+1}. {x['name']} – {x['team']} ({x['value']})" for i, x in enumerate(items[:5])]

def update_pl_leaders_sensor():
    # League leaders for attributes (top 5)
    goals5_raw   = fetch_pl_leaderboard_raw("goals", 5)
    assists5_raw = fetch_pl_leaderboard_raw("goal_assists", 5)
    sheets5_raw  = fetch_pl_leaderboard_raw("clean_sheets", 5)

    # Map raw -> compact dicts for formatting
    def compact(arr, key):
        out = []
        for x in arr:
            md = x.get("playerMetadata", {}) or {}
            tm = md.get("currentTeam", {}) or {}
            out.append({
                "name": md.get("name"),
                "team": tm.get("shortName") or tm.get("name"),
                "value": int((x.get("stats", {}) or {}).get(key, 0)),
            })
        return out

    goals5   = compact(goals5_raw,   "goals")
    assists5 = compact(assists5_raw, "goalAssists")
    sheets5  = compact(sheets5_raw,  "cleanSheets")

    # Find Liverpool's top scorer (scan a deeper list to be safe)
    lfc_scan = fetch_pl_leaderboard_raw("goals", 120)
    lfc_top  = find_team_top(lfc_scan, metric_key="goals")

    # Fallback: league top if LFC not found
    league_top = goals5[0] if goals5 else None
    season = current_pl_season_year()
    if lfc_top:
        state = f"{lfc_top['name']} ({lfc_top['value']})"
        if league_top:
            print(f"Top Scorer (EPL) [{season}]: LFC {state} | League {league_top['name']} ({league_top['value']})")
        else:
            print(f"Top Scorer (EPL) [{season}]: LFC {state}")
    else:
        state = f"{league_top['name']} ({league_top['value']})" if league_top else "unavailable"
        print(f"Top Scorer (EPL) [{season}]: League {state} (LFC not found in scan)")

    attrs = {
        "friendly_name": "Top Scorer (EPL)",
        "icon": "mdi:trophy",
        "season": season,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "goals_top5": fmt_lines(goals5),
        "assists_top5": fmt_lines(assists5),
        "clean_sheets_top5": fmt_lines(sheets5),
    }

    # Push sensor
    post_state("sensor.top_scorer_epl", state, attrs)

    # Console summary (fix: use correct variables)
    print_pl_leaders(goals5, assists5, sheets5, season)

# Run
fetch_tv_channel()
update_pl_leaders_sensor()
