#!/usr/bin/env python3
"""
Quarter Dashboard — multi-project HTML Dashboard generator
Discovers sprints for the current quarter across configured projects, pulls live
KPIs from Jira, generates narrative via Claude API, then writes a single
self-contained HTML dashboard with a project toggle in the navbar.
"""

import sys
import json
import os
import glob
import pathlib
import calendar
import base64
import argparse
import urllib.request
import urllib.parse
import concurrent.futures
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
from secret_manager import SecretsManager

# Force UTF-8 output so Unicode characters (em dashes, ellipsis, etc.) print correctly
# on Windows terminals that default to Windows-1252.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TESTING_MODE  = False   # Skip Claude API calls; preserve any existing notes
FORCE_NOTES   = False  # Force regeneration of ALL notes even for backfill quarters
PREVIEW_MODE  = True   # DEV: always on. Set to False when copying to live. — live page untouched
ANTHROPIC_MODEL     = "claude-sonnet-4-5"  # Update here when model is retired
ANTHROPIC_API_URL   = "https://api.anthropic.com/v1/messages"

secrets = SecretsManager()

JIRA_BASE_URL     = secrets["jira_base_url"].rstrip("/")
JIRA_EMAIL        = secrets["jira_username"]
JIRA_API_TOKEN    = secrets["jira_api_token"]
ANTHROPIC_API_KEY = secrets["anthropic_api_key"]
JIRA_CLOUD_ID     = secrets["jira_cloud_id"]

# Webhook URL that the dashboard's "Refresh" button will POST to (full data + notes run).
# Store as "refresh_webhook_url" in your secrets manager. Leave absent to hide the button.
REFRESH_WEBHOOK_URL         = secrets.get("refresh_webhook_url", "")
REFRESH_DATA_WEBHOOK_URL    = secrets.get("refresh_data_webhook_url", "")
REFRESH_REQUEST_WEBHOOK_URL = secrets.get("refresh_request_webhook_url", "")

# Dashboard branding — store in secrets or edit here directly.
# dashboard_title : shown in the browser tab before JS loads (JS sets it per-quarter afterwards).
# logo_alt        : alt text for the header logo image.
# dashboard_base_url : base URL printed to console after a successful run (cosmetic only).
DASHBOARD_TITLE        = secrets.get("dashboard_title",        "Quarter Dashboard")
LOGO_ALT               = secrets.get("logo_alt",               "")
DASHBOARD_BASE_URL     = secrets.get("dashboard_base_url",     "")
DASHBOARD_FILENAME     = secrets.get("dashboard_filename",     "index.html")
DASHBOARD_PREVIEW_FILE = secrets.get("dashboard_preview_file", "test.html")

# When the daily full Claude-notes run fires. Shown in the dashboard converted to each
# viewer's local timezone. Use IANA timezone names (https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).
# Set to None to omit the "next AI refresh" line from the staleness notice.
NOTES_REFRESH_TIME = {"hour": 17, "minute": 0, "tz": "Europe/Dublin"}

# To backfill past quarters for ALL projects, uncomment the list below.
# Comment it out again when done — the empty list above takes effect automatically.
BACKFILL_QUARTERS = []
#BACKFILL_QUARTERS = ["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024", "Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025", "Q1 2026"]

# ---------------------------------------------------------------------------
# Project configuration
# ---------------------------------------------------------------------------
# Add a project dict for each Jira project you want to track.
# team_file: JSON mapping accountId → Display Name (same dir as this script).
#            Format: { "accountId": "Display Name", ... }
#            Missing file = no team-member flagging for that project.

def _load_team(filename):
    """Load team members file. Supports both legacy flat format {id: name}
    and new object format {id: {name, since?}}.
    Returns {id: {name, since}} where since is a date string or None."""
    p = pathlib.Path(__file__).with_name(filename)
    if not p.exists():
        print(f"WARNING: {p} not found — no team members will be flagged.")
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    result = {}
    for aid, val in raw.items():
        if isinstance(val, str):
            result[aid] = {"name": val}
        else:
            entry = {"name": val.get("name", "")}
            if "periods" in val:
                entry["periods"] = val["periods"]
            else:
                if "since" in val: entry["since"] = val["since"]
                if "until" in val: entry["until"] = val["until"]
            result[aid] = entry
    return result

def _is_team_member(team_map, account_id, quarter_start_str, quarter_end_str=None):
    """Return True if account_id is a team member during the given quarter.
    A person is a team member if their membership period overlaps the quarter at all.
    Supports three formats:
      - no since/periods: always a member
      - since (+ optional until): single period
      - periods: [{since, until?}, ...] list of membership periods
    """
    entry = team_map.get(account_id)
    if not entry:
        return False
    q_end = quarter_end_str or "9999-12-31"
    periods = entry.get("periods")
    if periods:
        for p in periods:
            s = p.get("since") or ""
            u = p.get("until") or "9999-12-31"
            # Overlap: membership starts before quarter ends AND ends after quarter starts
            if (not s or s <= q_end) and u >= quarter_start_str:
                return True
        return False
    # Simple since/until format
    since = entry.get("since") or ""
    until = entry.get("until") or "9999-12-31"
    return (not since or since <= q_end) and until >= quarter_start_str

def _load_projects(filename="team_projects.json"):
    """Load project configuration from a JSON file beside this script.
    Each entry needs: key, display, board_id, team_file, reports_dir.
    Optional: notes_context (injected into Claude prompts for project-specific guidance)."""
    p = pathlib.Path(__file__).with_name(filename)
    if not p.exists():
        raise FileNotFoundError(
            f"Project config not found: {p}\n"
            f"Create {filename} beside this script — see team_projects.json for the format."
        )
    return json.loads(p.read_text(encoding="utf-8"))

PROJECTS = _load_projects("team_projects_test.json" if PREVIEW_MODE else "team_projects.json")

def _load_admins(filename="team_admins.json"):
    p = pathlib.Path(__file__).with_name(filename)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

WLOG_ADMINS = _load_admins()

# Resolve derived paths and load team members for each project
for _p in PROJECTS:
    _p["data_dir"]    = os.path.join(_p["reports_dir"], "data")
    _p["archive_dir"] = os.path.join(_p["reports_dir"], "archive")
    _p["team_map"]    = _load_team(_p["team_file"])

# Where the combined HTML is written. Defaults to the first project's reports_dir
# if not set in secrets. Set "dashboard_output_dir" in secrets to use a dedicated folder
# (e.g. /config/www/quarters) — the script will create it automatically on first run.
DASHBOARD_OUTPUT_DIR = secrets.get("dashboard_output_dir", PROJECTS[0]["reports_dir"])

# Module-level active project key/sp-field — set before each project run so
# helpers that can't easily take a proj param (e.g. _issue_row) work correctly.
_ACTIVE_PROJECT_KEY = PROJECTS[0]["key"]
_ACTIVE_SP_FIELD    = PROJECTS[0].get("story_points_field") or "customfield_10016"

# ---------------------------------------------------------------------------
# Developer roster — auto-maintained across all projects
# ---------------------------------------------------------------------------
# all_developers.json lives next to this script and is the master list of every
# person ever seen as a Jira assignee across any configured project.
# It is never shrunk automatically — people who leave a team stay in the file
# so their account ID is always available for reference.
# To assign someone to a project team, copy their entry into the relevant
# dlk_team_members.json / nda_team_members.json file.
_ALL_DEVS_FILE = pathlib.Path(__file__).with_name("team_members_all.json")


def _update_developer_roster(assignee_stats):
    """Merge newly seen assignees into all_developers.json. Adds only, never removes."""
    try:
        roster = json.loads(_ALL_DEVS_FILE.read_text(encoding="utf-8")) if _ALL_DEVS_FILE.exists() else {}
    except Exception:
        roster = {}

    added = []
    for a in assignee_stats:
        aid  = a.get("account_id", "")
        name = a.get("name", "")
        if aid and name and name != "Unassigned" and aid not in roster:
            roster[aid] = name
            added.append(name)

    if added:
        _ALL_DEVS_FILE.write_text(
            json.dumps(roster, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"      Developer roster updated — added: {', '.join(added)} ({len(roster)} total)")
    else:
        print(f"      Developer roster unchanged ({len(roster)} developers)")
    return roster


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _auth_header():
    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def http_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Quarter helpers
# ---------------------------------------------------------------------------

def current_quarter_start(ref=None):
    today = ref or date.today()
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    return date(today.year, quarter_month, 1)


def quarter_label(ref=None):
    today = ref or date.today()
    q = ((today.month - 1) // 3) + 1
    return f"Q{q} {today.year}"


def quarter_file_key(label):
    return label.replace(" ", "_")


# ---------------------------------------------------------------------------
# Sprint discovery
# ---------------------------------------------------------------------------

def fetch_sprints_in_quarter(proj, ref=None):
    headers = _auth_header()
    quarter_start = current_quarter_start(ref)
    today = ref or date.today()
    project_key = proj["key"]
    board_id_cfg = proj["board_id"]

    board_url = f"{JIRA_BASE_URL}/rest/agile/1.0/board?projectKeyOrId={project_key}&maxResults=50"
    board_data = http_get(board_url, headers)
    boards = board_data.get("values", [])
    if not boards:
        raise RuntimeError(f"No boards found for project {project_key}")

    preferred = next(
        (b for b in boards if str(b["id"]) == str(board_id_cfg)),
        boards[0]
    )
    board_id = preferred["id"]
    print(f"      Using board: {preferred['name']} (id={board_id})")

    seen = {}
    for state in ("active", "closed"):
        start_at = 0
        while True:
            params = urllib.parse.urlencode({
                "state": state,
                "startAt": start_at,
                "maxResults": 50,
            })
            url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint?{params}"
            data = http_get(url, headers)
            sprints = data.get("values", [])
            if not sprints:
                break

            for sprint in sprints:
                sid = sprint["id"]
                if sid in seen:
                    continue

                start_str = sprint.get("startDate", "")
                if not start_str:
                    continue
                try:
                    sprint_start = datetime.fromisoformat(
                        start_str.replace("Z", "+00:00")
                    ).date()
                except Exception:
                    continue

                end_str = sprint.get("endDate", "")
                end_date = None
                if end_str:
                    try:
                        end_date = datetime.fromisoformat(
                            end_str.replace("Z", "+00:00")
                        ).date()
                    except Exception:
                        pass

                sprint_end = end_date or today
                # Assign sprint to whichever quarter contains its midpoint,
                # so a sprint is never double-counted and a sprint that only
                # touches a quarter boundary by one day goes to the right place.
                # Use sprint_start <= today (not midpoint) to exclude future
                # sprints, since an active sprint's midpoint may not have
                # arrived yet.
                sprint_mid = sprint_start + timedelta(days=(sprint_end - sprint_start).days // 2)
                quarter_end_month = quarter_start.month + 2
                quarter_end = date(quarter_start.year, quarter_end_month,
                                   calendar.monthrange(quarter_start.year, quarter_end_month)[1])
                if not (sprint_start <= today and quarter_start <= sprint_mid <= quarter_end):
                    continue

                seen[sid] = {
                    "id": sid,
                    "name": sprint["name"],
                    "state": sprint["state"],
                    "start_date": str(sprint_start),
                    "end_date": str(end_date) if end_date else None,
                }

            if data.get("isLast", True):
                break
            start_at += len(sprints)

    return sorted(seen.values(), key=lambda s: s["start_date"])


def classify_sprints(sprints):
    result = []
    for sprint in sprints:
        state = sprint["state"].lower()
        if state == "active":
            label, color = "Current", "blue"
        elif state == "closed":
            label, color = "Closed", "neutral"
        else:
            label, color = "Upcoming", "yellow"
        result.append({**sprint, "status_label": label, "status_color": color})
    return result


# ---------------------------------------------------------------------------
# Jira search
# ---------------------------------------------------------------------------

def jira_search(jql, fields="key,summary,status,issuetype,assignee,fixVersions,labels,priority,customfield_10016",
                max_results=500, expand=None):
    headers = _auth_header()
    all_issues = []
    next_page_token = None

    while True:
        params = {
            "jql": jql,
            "fields": fields,
            "maxResults": 100,
        }
        if expand:
            params["expand"] = expand
        if next_page_token:
            params["nextPageToken"] = next_page_token

        url = f"{JIRA_BASE_URL}/rest/api/3/search/jql?{urllib.parse.urlencode(params)}"
        data = http_get(url, headers)
        issues = data.get("issues", [])
        all_issues.extend(issues)

        if data.get("isLast", True) or not issues or len(all_issues) >= max_results:
            break
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return all_issues


# Cache so we only hit the statuses endpoint once per run (keyed by project key)
_IN_PROGRESS_STATUSES: dict[str, set] = {}


def fetch_in_progress_statuses(project_key=None):
    """Return the set of status names that belong to the In Progress category."""
    global _IN_PROGRESS_STATUSES
    if project_key is None:
        project_key = _ACTIVE_PROJECT_KEY
    if project_key in _IN_PROGRESS_STATUSES:
        return _IN_PROGRESS_STATUSES[project_key]
    headers = _auth_header()
    url = f"{JIRA_BASE_URL}/rest/api/3/project/{project_key}/statuses"
    try:
        data = http_get(url, headers)
        names: set = set()
        for issue_type in data:
            for status in issue_type.get("statuses", []):
                if status.get("statusCategory", {}).get("key") == "indeterminate":
                    names.add(status["name"])
        _IN_PROGRESS_STATUSES[project_key] = names
        print(f"  In-progress statuses ({project_key}): {names}")
    except Exception as exc:
        print(f"  WARNING: Could not fetch project statuses ({exc}) — using defaults")
        _IN_PROGRESS_STATUSES[project_key] = {"In Progress", "In Development", "In Review", "In Testing"}
    return _IN_PROGRESS_STATUSES[project_key]


def _resolution_quarter(date_str):
    """Return a quarter label like 'Q2 2026' for a YYYY-MM-DD date string."""
    d = date.fromisoformat(date_str[:10])
    return f"Q{((d.month - 1) // 3) + 1} {d.year}"


def _sprint_added_date(issue, sprint_id_str, sprint_name):
    """Return the ISO date (YYYY-MM-DD) when a sprint was first added to the issue,
    by scanning the changelog for sprint field changes.  Returns None if not found.
    Matches by sprint ID string in the 'to' field or sprint name in 'toString'."""
    for history in sorted(
        issue.get("changelog", {}).get("histories", []),
        key=lambda h: h.get("created", "")
    ):
        for item in history.get("items", []):
            if item.get("field") == "Sprint" or item.get("fieldId") == "customfield_10020":
                to_ids  = str(item.get("to")       or "")
                to_str  = str(item.get("toString") or "")
                frm_ids = str(item.get("from")     or "")
                frm_str = str(item.get("fromString") or "")
                added_by_id   = sprint_id_str in to_ids.split(",") and sprint_id_str not in frm_ids.split(",")
                added_by_name = sprint_name in to_str and sprint_name not in frm_str
                if added_by_id or added_by_name:
                    return history["created"][:10]
    return None


def _earliest_in_progress_date(issue, in_progress_statuses):
    """Scan the changelog for the first date the issue entered an In Progress status.
    Returns an ISO date string (YYYY-MM-DD) or None if not found."""
    histories = issue.get("changelog", {}).get("histories", [])
    earliest = None
    for history in sorted(histories, key=lambda h: h.get("created", "")):
        for item in history.get("items", []):
            if item.get("field") == "status" and item.get("toString") in in_progress_statuses:
                d = history.get("created", "")[:10]
                if d and (earliest is None or d < earliest):
                    earliest = d
                break
    return earliest


# ---------------------------------------------------------------------------
# KPI calculation
# ---------------------------------------------------------------------------

def _sprint_date_map(board_id=None):
    """Return list of (start_date_str, end_date_str, sprint_name) from the Agile board API.
    Used to match a resolution date to the sprint it fell within."""
    if board_id is None:
        board_id = next(p["board_id"] for p in PROJECTS if p["key"] == _ACTIVE_PROJECT_KEY)
    headers = _auth_header()
    entries = []
    for state in ("active", "closed"):
        try:
            start_at = 0
            while True:
                params = urllib.parse.urlencode({"state": state, "startAt": start_at, "maxResults": 50})
                data = http_get(
                    f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint?{params}",
                    headers,
                )
                for s in data.get("values", []):
                    sd = (s.get("startDate") or "")[:10]
                    ed = (s.get("endDate")   or "")[:10]
                    nm = s.get("name", "")
                    if sd and ed and nm:
                        entries.append((sd, ed, nm))
                if data.get("isLast", True):
                    break
                start_at += len(data.get("values", []))
        except Exception as exc:
            print(f"      WARNING: sprint date map fetch failed ({exc})")
            break
    return entries


def _sprint_for_date(sprint_map, resolved_date_str):
    """Return the sprint name whose date range contains resolved_date_str."""
    rd = resolved_date_str[:10]
    for sd, ed, nm in sprint_map:
        if sd <= rd <= ed:
            return nm
    return ""


def _build_inprogress_rows(in_progress, all_issues, qe_date, in_progress_statuses):
    """Build the in-progress issue list, enriched with cross-quarter carry-over info.

    Items currently in-progress are shown as normal rows.
    Items that were started during/before this quarter but completed AFTER its end
    (i.e. they carried across the quarter boundary) get resolved_date / resolved_quarter
    fields and a _rowCls marker so the UI can display an info icon and green tint.
    """
    # Quarter start date — used to detect items carried in from a previous quarter
    qs_date = date(qe_date.year, qe_date.month - 2, 1)
    qs_str  = str(qs_date)
    qe_str  = str(qe_date)

    rows = []
    for i in in_progress:
        row = _issue_row(i)
        ip_date = _earliest_in_progress_date(i, in_progress_statuses)
        if ip_date and ip_date < qs_str:
            # Item was started before this quarter — flag as a carry-in
            ip_d   = date.fromisoformat(ip_date)
            orig_q = ((ip_d.month - 1) // 3) + 1
            cur_q  = ((qe_date.month - 1) // 3) + 1
            quarters_carried = (qe_date.year - ip_d.year) * 4 + (cur_q - orig_q)
            row["origin_quarter"]   = _resolution_quarter(ip_date)
            row["ip_date"]          = ip_date
            row["quarters_carried"] = quarters_carried
            row["_rowCls"]          = "carried-in-long" if quarters_carried >= 2 else "carried-in"
        rows.append(row)

    cross_candidates = []
    for i in all_issues:
        if i["fields"]["status"]["statusCategory"]["key"] != "done":
            continue
        rd = (i["fields"].get("resolutiondate") or "")[:10]
        if not rd or rd <= qe_str:
            continue
        ip_date = _earliest_in_progress_date(i, in_progress_statuses)
        if not ip_date or ip_date > qe_str:
            continue
        cross_candidates.append((i, rd))

    if cross_candidates:
        smap = _sprint_date_map(board_id=_ACTIVE_PROJECT_KEY and next(
            (p["board_id"] for p in PROJECTS if p["key"] == _ACTIVE_PROJECT_KEY), None))
        for i, rd in cross_candidates:
            row = _issue_row(i)
            row["resolved_date"]    = rd
            row["resolved_quarter"] = _resolution_quarter(rd)
            row["resolved_sprint"]  = _sprint_for_date(smap, rd)
            row["_rowCls"]          = "resolved-carried"
            rows.append(row)

    return rows


def _issue_row(issue):
    assignee   = issue["fields"].get("assignee")
    logged_s   = issue["fields"].get("timespent") or 0
    est_s      = issue["fields"].get("timeoriginalestimate") or 0
    sp_raw     = issue["fields"].get(_ACTIVE_SP_FIELD)
    story_pts  = int(sp_raw) if sp_raw is not None else 0
    resolved_s = (issue["fields"].get("resolutiondate") or "")[:10]
    # Use earliest In Progress transition as cycle start; fall back to created date
    ip_date    = _earliest_in_progress_date(issue, fetch_in_progress_statuses())
    start_s    = ip_date or (issue["fields"].get("created") or "")[:10]
    cycle_days = None
    if start_s and resolved_s:
        try:
            cycle_days = max(0, (date.fromisoformat(resolved_s) - date.fromisoformat(start_s)).days)
        except Exception:
            pass
    return {
        "key":            issue["key"],
        "url":            f"{JIRA_BASE_URL}/browse/{issue['key']}",
        "summary":        issue["fields"]["summary"],
        "type":           issue["fields"]["issuetype"]["name"],
        "status":         issue["fields"]["status"]["name"],
        "status_cat":     issue["fields"]["status"]["statusCategory"]["key"],
        "assignee":       assignee["displayName"] if assignee else "Unassigned",
        "priority":       (issue["fields"].get("priority") or {}).get("name", "") or "",
        "fix_versions":   [v["name"] for v in issue["fields"].get("fixVersions", [])],
        "labels":         issue["fields"].get("labels", []),
        "logged_h":       round(logged_s / 3600, 1),
        "estimated_h":    round(est_s   / 3600, 1),
        "has_estimate":   est_s > 0,
        "has_log":        logged_s > 0,
        "story_points":   story_pts,
        "cycle_days":     cycle_days,
    }


def _compute_per_sprint(sprints, all_issues, in_progress_statuses, proj,
                        version_release_dates, issue_sprint_ids_fn,
                        prev_q_sprint_id=None, prev_q_sprint_end=None,
                        quarter_start_str=None, excl_issues=None):
    """Compute per-sprint KPIs and assignee stats for sprint-level filtering and trends."""
    _excl_done_sp_st  = set(proj.get("excluded_done_statuses", []))
    _excl_done_sp_lbl = set(proj.get("excluded_done_labels",   []))
    sp_field          = proj.get("story_points_field") or "customfield_10016"
    use_oos           = proj.get("use_oos", True)
    def _is_done_sp(issue):
        if issue["fields"]["status"]["statusCategory"]["key"] != "done":
            return False
        if issue["fields"]["status"]["name"] in _excl_done_sp_st:
            return False
        if _excl_done_sp_lbl & set(issue["fields"].get("labels", [])):
            return False
        return True

    per_sprint = {}
    for sprint_idx, sprint in enumerate(sprints):
        sid = str(sprint["id"])
        # ID + end date of the sprint immediately before this one.
        # For the first sprint use the previous quarter's last sprint (if known).
        if sprint_idx > 0:
            prev_sid      = str(sprints[sprint_idx - 1]["id"])
            prev_end_date = sprints[sprint_idx - 1].get("end_date") or ""
        else:
            prev_sid      = prev_q_sprint_id
            prev_end_date = prev_q_sprint_end or ""
        s_issues = [i for i in all_issues if sid in issue_sprint_ids_fn(i)]
        if not s_issues:
            continue
        s_total     = len(s_issues)
        s_completed = [i for i in s_issues if _is_done_sp(i)]
        s_bugs      = sum(1 for i in s_issues if i["fields"]["issuetype"]["name"] == "Bug")
        s_stories   = sum(1 for i in s_issues if i["fields"]["issuetype"]["name"] == "Story")
        s_tasks     = sum(1 for i in s_issues if i["fields"]["issuetype"]["name"] == "Task")
        s_logged_s  = sum(i["fields"].get("timespent") or 0 for i in s_issues)
        s_est_s     = sum(i["fields"].get("timeoriginalestimate") or 0 for i in s_issues)
        s_sp_total     = sum(int(i["fields"].get(sp_field) or 0) for i in s_issues)
        s_sp_completed = sum(int(i["fields"].get(sp_field) or 0) for i in s_completed)
        if use_oos:
            s_oos_issues = [i for i in s_issues if "Out_Of_Sprint" in i["fields"].get("labels", [])]
            s_oos        = len(s_oos_issues)
            s_oos_open   = sum(1 for i in s_oos_issues
                               if i["fields"]["status"]["statusCategory"]["key"] != "done")
        else:
            s_oos_issues = []
            s_oos        = 0
            s_oos_open   = 0
        # Rollover = was in the immediately preceding sprint AND was added to the current
        # sprint AFTER the previous sprint ended.  If the current sprint was added before
        # the previous sprint closed, it was an early start (planned for this sprint),
        # not a rollover — exclude it.
        s_rollover = 0
        if prev_sid:
            for i in s_issues:
                if prev_sid not in issue_sprint_ids_fn(i):
                    continue
                if prev_end_date:
                    added = _sprint_added_date(i, sid, sprint["name"])
                    if added and added < prev_end_date:
                        continue  # added to this sprint before prev closed → early start
                s_rollover += 1
        s_cycle = []
        for i in s_completed:
            rs = (i["fields"].get("resolutiondate") or "")[:10]
            ip = _earliest_in_progress_date(i, in_progress_statuses)
            cs = ip or (i["fields"].get("created") or "")[:10]
            if rs and cs:
                try:
                    s_cycle.append(max(0, (date.fromisoformat(rs) - date.fromisoformat(cs)).days))
                except Exception:
                    pass
        sd = sprint.get("start_date") or ""
        ed = sprint.get("end_date") or str(date.today())
        s_releases = sum(1 for rd in version_release_dates.values() if sd <= rd <= ed)
        s_amap = {}
        for i in s_issues:
            af  = i["fields"].get("assignee") or {}
            a   = af.get("displayName", "Unassigned")
            aid = af.get("accountId", "")
            if a not in s_amap:
                s_amap[a] = {"account_id": aid, "total": 0, "completed": 0,
                             "logged_s": 0, "estimated_s": 0, "sp_total": 0, "sp_completed": 0}
            sp_val = int(i["fields"].get(sp_field) or 0)
            s_amap[a]["total"]       += 1
            s_amap[a]["sp_total"]    += sp_val
            if _is_done_sp(i):
                s_amap[a]["completed"]   += 1
                s_amap[a]["sp_completed"] += sp_val
            s_amap[a]["logged_s"]    += i["fields"].get("timespent") or 0
            s_amap[a]["estimated_s"] += i["fields"].get("timeoriginalestimate") or 0
        s_assignee_stats = sorted([{
            "name":            a,
            "account_id":      v["account_id"],
            "is_team":         _is_team_member(proj["team_map"], v["account_id"], quarter_start_str or "", sprint.get("end_date") or quarter_start_str or ""),
            "total":           v["total"],
            "completed":       v["completed"],
            "logged_h":        round(v["logged_s"] / 3600, 1),
            "estimated_h":     round(v["estimated_s"] / 3600, 1),
            "sp_total":        v["sp_total"],
            "sp_completed":    v["sp_completed"],
            "completion_rate": round(v["completed"] / v["total"] * 100) if v["total"] else 0,
        } for a, v in s_amap.items()], key=lambda x: (x["is_team"], x["total"]), reverse=True)
        # Per-sprint stats for excluded-summary issues so the dashboard
        # can adjust sprint-level KPIs when the "show excluded" checkbox is on.
        se_issues = [i for i in (excl_issues or []) if sid in issue_sprint_ids_fn(i)]
        se_logged_s    = sum(i["fields"].get("timespent")            or 0 for i in se_issues)
        se_estimated_s = sum(i["fields"].get("timeoriginalestimate") or 0 for i in se_issues)
        se_rows  = [_issue_row(i) for i in se_issues]
        se_cycle = [r["cycle_days"] for r in se_rows if r.get("cycle_days") is not None]
        se_by_dev = {}
        for _i in se_issues:
            _af = _i["fields"].get("assignee") or {}
            _a  = _af.get("displayName", "Unassigned")
            if _a not in se_by_dev:
                se_by_dev[_a] = {"logged_h": 0.0, "estimated_h": 0.0, "total": 0, "completed": 0}
            se_by_dev[_a]["total"]       += 1
            se_by_dev[_a]["logged_h"]    += round((_i["fields"].get("timespent")            or 0) / 3600, 2)
            se_by_dev[_a]["estimated_h"] += round((_i["fields"].get("timeoriginalestimate") or 0) / 3600, 2)
            if _i["fields"]["status"]["statusCategory"]["key"] == "done":
                se_by_dev[_a]["completed"] += 1
        s_excl_stats = {
            "item_count":        len(se_issues),
            "completed_count":   sum(1 for i in se_issues
                                     if i["fields"]["status"]["statusCategory"]["key"] == "done"),
            "bug_count":         sum(1 for i in se_issues
                                     if i["fields"]["issuetype"]["name"] == "Bug"),
            "story_count":       sum(1 for i in se_issues
                                     if i["fields"]["issuetype"]["name"] == "Story"),
            "task_count":        sum(1 for i in se_issues
                                     if i["fields"]["issuetype"]["name"] == "Task"),
            "oos_count":         sum(1 for i in se_issues
                                     if "Out_Of_Sprint" in i["fields"].get("labels", [])),
            "oos_open_count":    sum(1 for i in se_issues
                                     if "Out_Of_Sprint" in i["fields"].get("labels", [])
                                     and i["fields"]["status"]["statusCategory"]["key"] != "done"),
            "avg_cycle_days":    round(sum(se_cycle) / len(se_cycle), 1) if se_cycle else 0,
            "med_cycle_days":    round(sorted(se_cycle)[len(se_cycle) // 2], 1) if se_cycle else 0,
            "logged_h":          round(se_logged_s    / 3600, 1),
            "estimated_h":       round(se_estimated_s / 3600, 1),
            "no_estimate_count": sum(1 for i in se_issues if not i["fields"].get("timeoriginalestimate")),
            "no_log_count":      sum(1 for i in se_issues if not i["fields"].get("timespent")),
            "by_dev":            se_by_dev,
        } if se_issues else {}

        per_sprint[sid] = {
            "sprint_name":           sprint["name"],
            "sprint_state":          sprint["state"],
            "total":                 s_total,
            "completed":             len(s_completed),
            "completion_rate":       round(len(s_completed) / s_total * 100) if s_total else 0,
            "bugs":                  s_bugs,
            "stories":               s_stories,
            "tasks":                 s_tasks,
            "bug_pct":               round(s_bugs / s_total * 100) if s_total else 0,
            "rollover_count":        s_rollover,
            "rollover_pct":          round(s_rollover / s_total * 100) if s_total else 0,
            "avg_cycle_days":        round(sum(s_cycle) / len(s_cycle), 1) if s_cycle else 0,
            "med_cycle_days":        round(sorted(s_cycle)[len(s_cycle) // 2], 1) if s_cycle else 0,
            "time_logged_h":         round(s_logged_s / 3600, 1),
            "time_estimated_h":      round(s_est_s / 3600, 1),
            "estimate_accuracy_pct": (round(min(s_logged_s, s_est_s) / max(s_logged_s, s_est_s) * 100)
                                      if s_logged_s and s_est_s else 0),
            "oos_total":             s_oos,
            "oos_open":              s_oos_open,
            "releases_shipped":      s_releases,
            "sp_total":              s_sp_total,
            "sp_completed":          s_sp_completed,
            "assignee_stats":        s_assignee_stats,
            "excl_summary_stats":    s_excl_stats,
        }
    return per_sprint


def fetch_worklogs_for_quarter(issues, qs_date, qe_date):
    """Fetch per-day worklog breakdowns for issues that have time logged.
    Returns {accountId: {name, days: {date_str: {issue_key: {s: seconds, t: summary}}}}}
    Only hits the API for issues with timespent > 0 to minimise call count."""
    headers  = _auth_header()
    logged   = [i for i in issues if (i["fields"].get("timespent") or 0) > 0]
    qs_str, qe_str = str(qs_date), str(qe_date)
    print(f"      Fetching worklogs for {len(logged)} issues "
          f"({len(issues) - len(logged)} skipped — no time logged)...")
    def _fetch_issue_worklogs(issue):
        key     = issue["key"]
        summary = issue["fields"]["summary"][:80]
        entries = []
        try:
            start_at, worklogs = 0, []
            while True:
                url  = (f"{JIRA_BASE_URL}/rest/api/3/issue/{key}/worklog"
                        f"?maxResults=100&startAt={start_at}")
                data = http_get(url, headers)
                page = data.get("worklogs", data.get("values", []))
                worklogs.extend(page)
                total = data.get("total", 0)
                if not page or (start_at + len(page)) >= total:
                    break
                start_at += len(page)
        except Exception as exc:
            print(f"      WARNING: worklog fetch failed for {key}: {exc}")
            return entries
        for wl in worklogs:
            started = (wl.get("started") or "")[:10]
            if not (qs_str <= started <= qe_str):
                continue
            author = wl.get("author") or {}
            aid    = author.get("accountId", "")
            name   = author.get("displayName", "Unknown")
            secs   = wl.get("timeSpentSeconds", 0)
            if not aid or not secs:
                continue
            entries.append((aid, name, started, key, summary, secs))
        return entries

    by_person: dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for entries in ex.map(_fetch_issue_worklogs, logged):
            for aid, name, started, key, summary, secs in entries:
                by_person.setdefault(aid, {"name": name, "days": {}})
                days = by_person[aid]["days"]
                days.setdefault(started, {})
                entry = days[started].setdefault(key, {"s": 0, "t": summary})
                entry["s"] += secs
    print(f"      Worklog data: {len(by_person)} people with logged time")
    return by_person


def fetch_kpis(sprints, proj, ref=None, prev_sprint_id=None, prev_sprint_end=None):
    project_key   = proj["key"]
    use_sp        = proj.get("use_story_points", False)
    sp_field      = proj.get("story_points_field") or "customfield_10016"
    use_oos       = proj.get("use_oos", True)
    excl_summ     = [s.lower() for s in proj.get("excluded_summary_contains", [])]
    sprint_ids    = [str(s["id"]) for s in sprints]
    sprint_clause = ", ".join(sprint_ids)
    base_jql      = f"project = {project_key} AND sprint in ({sprint_clause})"

    in_progress_statuses = fetch_in_progress_statuses(project_key)

    print(f"  Querying: {base_jql[:90]}...")
    all_issues = jira_search(
        base_jql,
        fields=f"key,summary,status,issuetype,assignee,fixVersions,labels,priority,"
               f"timespent,timeoriginalestimate,{sp_field},created,resolutiondate",
        expand="changelog",
    )

    # Exclude issues whose summary contains any of the configured strings (case-insensitive)
    # Keep a separate list so the dashboard can optionally show them.
    excl_summ_issues = []
    if excl_summ:
        excl_summ_issues = [i for i in all_issues
                            if any(x in i["fields"]["summary"].lower() for x in excl_summ)]
        all_issues = [i for i in all_issues
                      if not any(x in i["fields"]["summary"].lower() for x in excl_summ)]

    # Time/assignee stats for excluded-summary issues, stored so the dashboard
    # can add them back in when the "show excluded" checkbox is on.
    _es_logged_s    = sum(i["fields"].get("timespent")            or 0 for i in excl_summ_issues)
    _es_estimated_s = sum(i["fields"].get("timeoriginalestimate") or 0 for i in excl_summ_issues)
    _es_rows  = [_issue_row(i) for i in excl_summ_issues]
    _es_cycle = [r["cycle_days"] for r in _es_rows if r.get("cycle_days") is not None]
    _es_by_dev = {}
    for _i in excl_summ_issues:
        _af  = _i["fields"].get("assignee") or {}
        _a   = _af.get("displayName", "Unassigned")
        if _a not in _es_by_dev:
            _es_by_dev[_a] = {"logged_h": 0.0, "estimated_h": 0.0, "total": 0, "completed": 0}
        _es_by_dev[_a]["total"]       += 1
        _es_by_dev[_a]["logged_h"]    += round((_i["fields"].get("timespent")            or 0) / 3600, 2)
        _es_by_dev[_a]["estimated_h"] += round((_i["fields"].get("timeoriginalestimate") or 0) / 3600, 2)
        if _i["fields"]["status"]["statusCategory"]["key"] == "done":
            _es_by_dev[_a]["completed"] += 1
    excl_summary_stats = {
        "item_count":        len(excl_summ_issues),
        "completed_count":   sum(1 for i in excl_summ_issues
                                 if i["fields"]["status"]["statusCategory"]["key"] == "done"),
        "bug_count":         sum(1 for i in excl_summ_issues
                                 if i["fields"]["issuetype"]["name"] == "Bug"),
        "story_count":       sum(1 for i in excl_summ_issues
                                 if i["fields"]["issuetype"]["name"] == "Story"),
        "task_count":        sum(1 for i in excl_summ_issues
                                 if i["fields"]["issuetype"]["name"] == "Task"),
        "oos_count":         sum(1 for i in excl_summ_issues
                                 if "Out_Of_Sprint" in i["fields"].get("labels", [])),
        "oos_open_count":    sum(1 for i in excl_summ_issues
                                 if "Out_Of_Sprint" in i["fields"].get("labels", [])
                                 and i["fields"]["status"]["statusCategory"]["key"] != "done"),
        "avg_cycle_days":    round(sum(_es_cycle) / len(_es_cycle), 1) if _es_cycle else 0,
        "med_cycle_days":    round(sorted(_es_cycle)[len(_es_cycle) // 2], 1) if _es_cycle else 0,
        "logged_h":          round(_es_logged_s    / 3600, 1),
        "estimated_h":       round(_es_estimated_s / 3600, 1),
        "no_estimate_count": sum(1 for i in excl_summ_issues if not i["fields"].get("timeoriginalestimate")),
        "no_log_count":      sum(1 for i in excl_summ_issues if not i["fields"].get("timespent")),
        "by_dev":            _es_by_dev,
    } if excl_summ_issues else {}

    # Key set used to filter raw JQL results (e.g. rollover) against the exclusion list above
    _filtered_keys = {i["key"] for i in all_issues}

    # Sprint membership — Jira Cloud REST v3 doesn't reliably return customfield_10020
    # so we fetch issue keys per sprint with a lightweight JQL call instead.
    print(f"  Building sprint membership map ({len(sprints)} sprints, parallel)...")
    _sprint_membership: dict[str, list[str]] = {}  # issue_key -> [sprint_id_str, ...]
    prev_sid_str = str(prev_sprint_id) if prev_sprint_id else None
    _membership_targets = [(str(s["id"]), s["name"]) for s in sprints]
    if prev_sid_str:
        _membership_targets.append((prev_sid_str, f"prev-quarter {prev_sprint_id}"))

    def _fetch_sprint_keys(sid_name):
        sid, name = sid_name
        keys = {i["key"] for i in jira_search(
            f"project = {project_key} AND sprint = {sid}",
            fields="key", max_results=2000,
        )}
        return sid, name, keys

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for sid, name, keys in ex.map(_fetch_sprint_keys, _membership_targets):
            for k in keys:
                _sprint_membership.setdefault(k, []).append(sid)
            suffix = " (rollover check)" if sid == prev_sid_str else ""
            print(f"    Sprint {name}: {len(keys)} issues{suffix}")

    def _issue_sprint_ids(issue):
        return _sprint_membership.get(issue.get("key", ""), [])
    def _row_with_sprints(issue):
        row = _issue_row(issue)
        row["sprint_ids"] = _issue_sprint_ids(issue)
        return row

    # Statuses/labels in the Done category that should NOT count as completed work.
    # excluded_done_statuses: e.g. ["Rejected"] for PEM
    # excluded_done_labels:   e.g. ["Archive"] for DLK (Done + that label = rejected)
    _excl_done_st  = set(proj.get("excluded_done_statuses", []))
    _excl_done_lbl = set(proj.get("excluded_done_labels",   []))
    def _is_done(issue):
        if issue["fields"]["status"]["statusCategory"]["key"] != "done":
            return False
        if issue["fields"]["status"]["name"] in _excl_done_st:
            return False
        if _excl_done_lbl & set(issue["fields"].get("labels", [])):
            return False
        return True

    completed   = [i for i in all_issues if _is_done(i)]
    in_progress = [i for i in all_issues
                   if i["fields"]["status"]["statusCategory"]["key"] == "indeterminate"]

    if use_oos:
        oos_all  = [i for i in all_issues
                    if "Out_Of_Sprint" in i["fields"].get("labels", [])]
        oos_open = [i for i in oos_all
                    if i["fields"]["status"]["statusCategory"]["key"] != "done"]
    else:
        oos_all  = []
        oos_open = []

    released_issues = [i for i in all_issues
                       if i["fields"]["status"]["name"] in ("Released", "Closed", "Merged")
                       and i["fields"].get("fixVersions")]

    version_ids = {}
    versions    = {}
    version_release_dates = {}
    for issue in completed:
        for v in issue["fields"].get("fixVersions", []):
            if not v.get("released", False):
                continue
            versions[v["name"]] = versions.get(v["name"], 0) + 1
            if v["name"] not in version_ids:
                version_ids[v["name"]] = v.get("id", "")
            rd = v.get("releaseDate", "")
            if rd and (v["name"] not in version_release_dates or rd > version_release_dates[v["name"]]):
                version_release_dates[v["name"]] = rd
    last_release_date = max(version_release_dates.values(), default=None) if version_release_dates else None
    version_details = sorted([
        {
            "name":       name,
            "release_date": version_release_dates.get(name, ""),
            "ticket_count": versions[name],
            "version_id": version_ids.get(name, ""),
        }
        for name in versions
    ], key=lambda x: x["release_date"], reverse=True)

    type_counts = {}
    for issue in all_issues:
        t = issue["fields"]["issuetype"]["name"]
        type_counts[t] = type_counts.get(t, 0) + 1

    total   = len(all_issues)
    bugs    = type_counts.get("Bug", 0)
    stories = type_counts.get("Story", 0)
    tasks   = type_counts.get("Task", 0)
    closed_sprint_count = sum(1 for s in sprints if s["state"].lower() == "closed")

    # Tickets per day — completed items divided by days elapsed in the quarter so far
    today         = ref or date.today()
    qs_date       = current_quarter_start(ref)
    qe_month      = qs_date.month + 2
    qe_date       = date(qs_date.year, qe_month, calendar.monthrange(qs_date.year, qe_month)[1])
    days_elapsed  = min((today - qs_date).days + 1, (qe_date - qs_date).days + 1)
    tickets_per_day = round(len(completed) / days_elapsed, 2) if days_elapsed else 0

    # Story points (always computed; display controlled by use_sp flag)
    sp_total     = sum(int(i["fields"].get(sp_field) or 0) for i in all_issues)
    sp_completed = sum(int(i["fields"].get(sp_field) or 0) for i in completed)

    # Time tracking / no-estimate logic differs by project mode
    total_logged_s    = sum(i["fields"].get("timespent")            or 0 for i in all_issues)
    total_estimated_s = sum(i["fields"].get("timeoriginalestimate") or 0 for i in all_issues)
    if use_sp:
        no_estimate = [i for i in all_issues if not (i["fields"].get(sp_field) or 0)]
        no_log      = []
    else:
        no_estimate = [i for i in all_issues if not i["fields"].get("timeoriginalestimate")]
        no_log      = [i for i in all_issues if not i["fields"].get("timespent")]
    time_logged_h    = round(total_logged_s    / 3600, 1)
    time_estimated_h = round(total_estimated_s / 3600, 1)
    # Accuracy: how close is logged to estimated? Always 0—100%.
    # min/max ratio is symmetric — over-running 50% scores the same as under-running 50%.
    estimate_accuracy_pct = (
        round(min(total_logged_s, total_estimated_s) /
              max(total_logged_s, total_estimated_s) * 100)
        if total_estimated_s and total_logged_s else 0
    )
    # Variance: positive = over-ran, negative = under-ran (kept for Time tab detail)
    estimate_variance_pct = (
        round((total_logged_s - total_estimated_s) / total_estimated_s * 100)
        if total_estimated_s else 0
    )

    # Cycle time: In Progress start → resolved for done issues (in calendar days).
    # Uses the earliest changelog transition into an In Progress status as the start;
    # falls back to the issue creation date only if no such transition exists.
    cycle_times = []
    for i in completed:
        rs = (i["fields"].get("resolutiondate") or "")[:10]
        if not rs:
            continue
        ip = _earliest_in_progress_date(i, in_progress_statuses)
        # Skip issues that never entered In Progress — they were closed without work
        # (e.g. "To Do → Done" / won't-do closures). Fall back to created only when
        # there IS logged time, meaning work happened despite no status transition.
        if ip:
            cs = ip
        elif (i["fields"].get("timespent") or 0) > 0:
            cs = (i["fields"].get("created") or "")[:10]
        else:
            continue  # no work done — exclude from cycle time
        if cs:
            try:
                cycle_times.append(max(0, (date.fromisoformat(rs) - date.fromisoformat(cs)).days))
            except Exception:
                pass
    avg_cycle_days = round(sum(cycle_times) / len(cycle_times), 1) if cycle_times else 0
    med_cycle_days = round(sorted(cycle_times)[len(cycle_times) // 2], 1) if cycle_times else 0

    # Assignee workload: aggregate from all issues
    assignee_map = {}
    for i in all_issues:
        af  = i["fields"].get("assignee") or {}
        a   = af.get("displayName", "Unassigned")
        aid = af.get("accountId", "")
        if a not in assignee_map:
            assignee_map[a] = {"account_id": aid, "total": 0, "completed": 0,
                               "logged_s": 0, "estimated_s": 0, "sp_total": 0, "sp_completed": 0}
        assignee_map[a]["total"]       += 1
        sp_val = int(i["fields"].get(sp_field) or 0)
        assignee_map[a]["sp_total"]    += sp_val
        if _is_done(i):
            assignee_map[a]["completed"]   += 1
            assignee_map[a]["sp_completed"] += sp_val
        assignee_map[a]["logged_s"]    += i["fields"].get("timespent") or 0
        assignee_map[a]["estimated_s"] += i["fields"].get("timeoriginalestimate") or 0
    def _team_period_label(team_map, account_id, qs, qe):
        """Return a short label like 'from May 25' / 'until Jun 12' / 'partial' if the
        member was not on the team for the full quarter, else None."""
        entry = team_map.get(account_id)
        if not entry:
            return None
        def fmt(d):
            import datetime
            try: return datetime.date.fromisoformat(d).strftime("%-d %b") if d else None
            except Exception: return None
        periods = entry.get("periods")
        if periods:
            # Multiple stints — always partial
            parts = []
            for p in periods:
                s, u = p.get("since"), p.get("until")
                if s and s > str(qs): parts.append(f"from {fmt(s) or s}")
                if u and u < str(qe): parts.append(f"until {fmt(u) or u}")
            return ", ".join(parts) if parts else "partial"
        since = entry.get("since")
        until = entry.get("until")
        parts = []
        if since and since > str(qs): parts.append(f"since {fmt(since) or since}")
        if until and until < str(qe): parts.append(f"until {fmt(until) or until}")
        return ", ".join(parts) if parts else None

    assignee_stats = sorted([
        {
            "name":            a,
            "account_id":      v["account_id"],
            "is_team":         _is_team_member(proj["team_map"], v["account_id"], str(qs_date), str(qe_date)),
            "team_period":     _team_period_label(proj["team_map"], v["account_id"], qs_date, qe_date),
            "total":           v["total"],
            "completed":       v["completed"],
            "logged_h":        round(v["logged_s"] / 3600, 1),
            "estimated_h":     round(v["estimated_s"] / 3600, 1),
            "sp_total":        v["sp_total"],
            "sp_completed":    v["sp_completed"],
            "completion_rate": round(v["completed"] / v["total"] * 100) if v["total"] else 0,
        }
        for a, v in assignee_map.items()
    ], key=lambda x: (x["is_team"], x["total"]), reverse=True)

    # Sprint rollover: items in each closed sprint that were not completed
    # Filter against _filtered_keys so excluded issues (e.g. buffer work) are not counted
    closed_sprints = [s for s in sprints if s["state"].lower() == "closed"]

    def _fetch_rollover(s):
        rolled = jira_search(
            f"project = {project_key} AND sprint = {s['id']} AND statusCategory != Done",
            fields="key",
        )
        return sum(1 for r in rolled if r["key"] in _filtered_keys)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rollover_count = sum(ex.map(_fetch_rollover, closed_sprints))
    rollover_pct = round(rollover_count / total * 100) if total else 0

    oos_open_detail = []
    for issue in oos_open:
        assignee = issue["fields"].get("assignee")
        oos_open_detail.append({
            "key":      issue["key"],
            "summary":  issue["fields"]["summary"],
            "assignee": assignee["displayName"] if assignee else "Unassigned",
            "status":   issue["fields"]["status"]["name"],
            "priority": (issue["fields"].get("priority") or {}).get("name", ""),
        })

    _result = {
        "total":                   total,
        "completed":               len(completed),
        "in_progress":             len(in_progress),
        "completion_rate":         round(len(completed) / total * 100) if total else 0,
        "releases_shipped":        len(versions),
        "last_release_date":       last_release_date,
        "version_details":         version_details,
        "tickets_per_day":         tickets_per_day,
        "avg_releases_per_sprint": round(len(versions) / closed_sprint_count, 1) if closed_sprint_count else 0,
        "med_releases_per_sprint": (lambda counts: sorted(counts)[len(counts)//2] if counts else 0)(
            [sum(1 for rd in version_release_dates.values()
                 if (s["start_date"] or "") <= rd <= (s["end_date"] or str(date.today())))
             for s in sprints if s["state"].lower() == "closed"]
        ),
        "oos_total":               len(oos_all),
        "oos_open":                len(oos_open),
        "oos_pct":                 round(len(oos_all) / total * 100) if total else 0,
        "oos_open_detail":         oos_open_detail,
        "bugs":                    bugs,
        "stories":                 stories,
        "tasks":                   tasks,
        "bug_pct":                 round(bugs / total * 100) if total else 0,
        "versions":                versions,
        "version_ids":             version_ids,
        "sprint_count":            len(sprints),
        "closed_sprint_count":     closed_sprint_count,
        "quarter":                 quarter_label(ref),
        "quarter_start":           str(current_quarter_start(ref)),
        "sprint_ids":              sprint_ids,
        "board_id":                str(proj["board_id"]),
        "jira_base":               JIRA_BASE_URL,
        "as_of":                   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "time_logged_h":        time_logged_h,
        "time_estimated_h":     time_estimated_h,
        "estimate_accuracy_pct":estimate_accuracy_pct,
        "estimate_variance_pct":estimate_variance_pct,
        "no_estimate_count":    len(no_estimate),
        "no_estimate_pct":      round(len(no_estimate) / total * 100) if total else 0,
        "no_log_count":         len(no_log),
        "avg_cycle_days":       avg_cycle_days,
        "med_cycle_days":       med_cycle_days,
        "rollover_count":       rollover_count,
        "rollover_pct":         rollover_pct,
        "assignee_stats":       assignee_stats,
        "issues": {
            "all":         [_row_with_sprints(i) for i in all_issues],
            "oos_all":     [_row_with_sprints(i) for i in oos_all],
            "oos_open":    [_row_with_sprints(i) for i in oos_open],
            "released":    [_row_with_sprints(i) for i in sorted(
                released_issues,
                key=lambda i: (
                    max((version_release_dates.get(v["name"], "") for v in i["fields"].get("fixVersions", [])), default=""),
                    max((v["name"].lstrip("v") for v in i["fields"].get("fixVersions", [])), default=""),
                ),
                reverse=True,
            )],
            "in_progress": [dict(r, sprint_ids=_issue_sprint_ids(
                                next((i for i in all_issues if i["key"] == r["key"]), {})))
                            for r in _build_inprogress_rows(in_progress, all_issues, qe_date, in_progress_statuses)],
            "no_estimate":       [_row_with_sprints(i) for i in no_estimate],
            "excluded_summary":  [_row_with_sprints(i) for i in excl_summ_issues],
        },
        "per_sprint":          "__PLACEHOLDER__",
        "excl_summary_stats":  excl_summary_stats,
    }
    _per_sprint = _compute_per_sprint(sprints, all_issues, in_progress_statuses,
                                      proj, version_release_dates,
                                      _issue_sprint_ids,
                                      prev_q_sprint_id=prev_sid_str,
                                      prev_q_sprint_end=prev_sprint_end,
                                      quarter_start_str=str(qs_date),
                                      excl_issues=excl_summ_issues)
    _sp_velocity_avg = 0
    if use_sp:
        _closed_sps = [v["sp_completed"] for v in _per_sprint.values()
                       if v["sprint_state"].lower() == "closed"]
        _sp_velocity_avg = round(sum(_closed_sps) / len(_closed_sps), 1) if _closed_sps else 0
    _result["per_sprint"]      = _per_sprint
    _result["use_story_points"]   = use_sp
    _result["use_oos"]            = use_oos
    _excl_terms = proj.get("excluded_summary_contains", [])
    _result["excl_summary_label"] = _excl_terms[0] if len(_excl_terms) == 1 else ""
    _result["sp_total"]         = sp_total
    _result["sp_completed"]     = sp_completed
    _result["sp_velocity_avg"]  = _sp_velocity_avg
    # Worklog data — only fetched when "fetch_worklogs": true in project config.
    # Adds one API call per issue that has timespent > 0.
    if proj.get("fetch_worklogs", False):
        _result["worklog_by_person"] = fetch_worklogs_for_quarter(all_issues + excl_summ_issues, qs_date, qe_date)
    else:
        _result["worklog_by_person"] = {}
    return _result


# ---------------------------------------------------------------------------
# Claude — generate narrative notes
# ---------------------------------------------------------------------------

def generate_notes(kpis, sprints, existing_notes=None, existing_kpis=None, proj_context=""):
    existing_notes = existing_notes or {}
    existing_kpis  = existing_kpis  or {}
    use_sp  = kpis.get("use_story_points", False)
    use_oos = kpis.get("use_oos", True)
    all_keys = [
        "total","completed","completion_rate","releases_shipped",
        *( ["oos_total","oos_open"] if use_oos else [] ),
        "type_split","avg_releases","rollover","cycle_time","assignee_workload",
    ]
    if use_sp:
        all_keys += ["sp_velocity", "no_estimate"]  # no_estimate = no story points
    else:
        all_keys += ["time_logged", "estimate_accuracy", "no_estimate"]
    # Which KPI fields drive each note — if none changed, keep the existing note
    _note_deps = {
        "total":             ["total"],
        "completed":         ["completed"],
        "completion_rate":   ["completion_rate"],
        "releases_shipped":  ["releases_shipped", "avg_releases_per_sprint"],
        "oos_total":         ["oos_total", "oos_pct"],
        "oos_open":          ["oos_open"],
        "type_split":        ["bugs", "stories", "tasks", "bug_pct"],
        "avg_releases":      ["avg_releases_per_sprint"],
        "time_logged":       ["time_logged_h", "time_estimated_h"],
        "estimate_accuracy": ["estimate_accuracy_pct", "estimate_variance_pct"],
        "no_estimate":       ["no_estimate_count", "no_estimate_pct"],
        "sp_velocity":       ["sp_completed", "sp_velocity_avg", "sp_total"],
        "rollover":          ["rollover_count", "rollover_pct"],
        "cycle_time":        ["avg_cycle_days", "med_cycle_days"],
        "assignee_workload": ["assignee_stats"],
    }
    def _kpi_changed(key):
        if not existing_notes.get(key, "").strip():
            return True  # no existing note — must generate
        if not existing_kpis:
            return True  # no previous data to compare against
        return any(kpis.get(f) != existing_kpis.get(f) for f in _note_deps.get(key, []))

    missing_keys = [k for k in all_keys if _kpi_changed(k)]
    if not missing_keys:
        print("      KPI values unchanged — skipping API call, reusing existing notes.")
        return existing_notes

    print(f"      Generating notes for {len(missing_keys)} key(s): {', '.join(missing_keys)}")
    current_sprint = next(
        (s["name"] for s in sprints if s["state"].lower() == "active"), None
    )
    # Strip fields that are bulky, already in user_text, or irrelevant to notes
    _prompt_exclude = {
        "issues", "version_details", "version_ids", "versions",
        "oos_open_detail", "sprint_ids", "quarter", "quarter_start",
        "board_id", "jira_base", "as_of",
    }
    kpis_for_prompt = {k: v for k, v in kpis.items() if k not in _prompt_exclude}
    # Filter assignee_stats to team members only so Claude doesn't call out non-team assignees
    if "assignee_stats" in kpis_for_prompt:
        kpis_for_prompt["assignee_stats"] = [
            a for a in kpis_for_prompt["assignee_stats"] if a.get("is_team")
        ]

    if TESTING_MODE:
        print("      TESTING MODE — skipping Claude API call, preserving existing notes.")
        return {**{k: "[test]" for k in all_keys}, **existing_notes}

    system_text = """\
You are a technical product owner writing concise, insightful notes for a management quarter dashboard.
The audience is product and engineering leadership who want to quickly understand team health and delivery performance.
Write 1-2 sentences per metric. Be direct, factual, and actionable. Flag risks clearly. Celebrate genuine wins briefly.
Do not pad with filler phrases like "the team is working hard" or "good progress was made".
IMPORTANT: If the quarter status says IN PROGRESS, the data is mid-quarter — do NOT write as if the quarter is finished.
The active sprint is not necessarily the last sprint; more sprints will follow before quarter end. Frame notes accordingly (e.g. "on track to...", "at this point in the quarter...", "with X days remaining...").
Respond ONLY with a valid JSON object — no markdown, no preamble, no backticks, no trailing commas.

METRIC GUIDANCE — use this to interpret each KPI and decide what to flag:

total: Total tickets in scope for the quarter across all sprints.
  - Flag if unusually high (scope creep risk) or low (team underutilised).
  - Note whether it reflects a healthy pipeline or signs of overloading.

completed: Tickets moved to Done status.
  - Compare against total to give context. Flag if significantly below total mid-quarter.
  - Note whether velocity is on track for quarter goals.

completion_rate: Percentage of in-scope tickets completed.
  - 80%+ is healthy. 60-79% warrants a comment on blockers. Below 60% is a concern.
  - If quarter is still active, note how much time remains and whether rate is on track.

releases_shipped: Number of Jira fix versions released this quarter.
  - Flag if zero (nothing shipped). Multiple releases = good cadence.
  - Note if releases are frequent (good) or infrequent (potential bottleneck).

__OOS_GUIDANCE__type_split: Breakdown of bugs vs stories vs tasks.
  - High bug ratio (>40%) signals quality issues needing attention.
  - Healthy mix is mostly stories/tasks with a small bug count.
  - Flag if bugs dominate the quarter.

avg_releases: Median (and mean) releases per closed sprint.
  - Use the median as the headline — it is resistant to a single sprint with a large batch skewing the picture.
  - Use the TEAM CONTEXT to calibrate what is healthy — web teams can ship multiple times per sprint; mobile teams may ship once per quarter due to app store review. Do not flag low counts as a concern for mobile teams.

time_logged: Total hours logged by the team across the quarter.
  - Compare against expected capacity (team size x sprint days x hours/day).
  - Flag if significantly under-logged (may indicate tracking issues or underutilisation).
  - Flag if over-logged (potential burnout or scope issues).

estimate_accuracy: How close actual time spent was to original estimates.
  - Within 20% variance is good. Over 50% variance indicates poor estimation.
  - Flag consistent over- or under-estimation patterns.

no_estimate: Tickets with no estimate set (time estimate for time-tracking projects; story points for SP projects).
  - High percentage means planning data is unreliable. Flag if above 20%.
  - Zero or near-zero is excellent hygiene.

assignee_workload: Distribution of tickets across team members.
  - Flag if one person carries a disproportionate share (>40% of tickets).
  - Note if workload is well-balanced or concentrated on specific individuals.
  - Mention unassigned tickets if significant.
  - For SP projects, reference story points (sp_total/sp_completed) per person where available.

rollover: Tickets carried over from a previous sprint without completion.
  - Any rollover reduces sprint predictability. Flag count and percentage.
  - Identify if rollover is a recurring pattern or a one-off.

cycle_time: Median (and mean) days from "In Progress" to "Done".
  - Use median as the headline — it is resistant to a small number of long-running tickets inflating the average.
  - Under 3 days = excellent flow. 3-7 days = normal. Over 7 days = flag blockers.
  - If avg is significantly higher than median, note that outlier tickets are skewing the mean.

sp_velocity: Average story points completed per sprint (story-points projects only).
  - Comment on velocity consistency and trend. Flag if SP completed is significantly below SP planned.
  - Mention total SP completed vs planned (sp_completed vs sp_total) for the quarter.
  - If velocity is improving sprint-on-sprint, note that positively.

Return ONLY the following keys that are needed (do not include any others):
__MISSING_KEYS_JSON__"""
    if use_sp:
        system_text += "\n\nSP MODE: This project tracks story points (not time). no_estimate = items missing a story point value. sp_velocity = avg story points completed per sprint."
    if proj_context:
        system_text += f"\n\nTEAM CONTEXT: {proj_context}"

    missing_keys_json = json.dumps(
        {k: "<1-2 sentence note>" for k in missing_keys}, indent=2
    )
    _oos_guidance = (
        "oos_total: Out-of-sprint tickets — items added to a sprint after it started.\n"
        "  - High OOS indicates poor sprint planning or reactive work. Flag if above 20% of total.\n"
        "  - Low OOS = disciplined planning, worth noting positively.\n\n"
        "oos_open: Out-of-sprint tickets still open/unresolved.\n"
        "  - Any open OOS items are unplanned debt. Flag if non-zero and note the count.\n"
        "  - Zero is the target — confirm if achieved.\n\n"
    ) if use_oos else ""
    filled_system = (system_text
                     .replace("__OOS_GUIDANCE__", _oos_guidance)
                     .replace("__MISSING_KEYS_JSON__", missing_keys_json))

    # Quarter progress context
    qs_date   = date.fromisoformat(kpis['quarter_start'])
    qe_month  = qs_date.month + 2
    qe_date   = date(qs_date.year, qe_month, calendar.monthrange(qs_date.year, qe_month)[1])
    today     = date.today()
    is_active = today <= qe_date
    days_total   = (qe_date - qs_date).days + 1
    days_elapsed = min((today - qs_date).days + 1, days_total)
    days_remaining = max((qe_date - today).days, 0)
    pct_elapsed  = round(days_elapsed / days_total * 100)
    closed_sprints = sum(1 for s in sprints if s["state"].lower() == "closed")
    total_sprints  = len(sprints)
    quarter_status = (
        f"IN PROGRESS — {pct_elapsed}% through ({days_elapsed}/{days_total} days elapsed, "
        f"{days_remaining} days remaining). "
        f"{closed_sprints} of {total_sprints} sprints closed. "
        f"Active sprint: {current_sprint}. More sprints likely remain before quarter end ({qe_date})."
    ) if is_active else f"COMPLETED — quarter ended {qe_date}."

    _oos_user_line = f"Open OOS items: {json.dumps(kpis['oos_open_detail'])}\n" if use_oos else ""
    user_text = f"""\
Quarter: {kpis['quarter']} (started {kpis['quarter_start']}, ends {qe_date})
Quarter status: {quarter_status}
{_oos_user_line}

KPI data:
{json.dumps(kpis_for_prompt, indent=2)}"""

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 1500,
        "system": [{"type": "text", "text": filled_system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_text}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
        text = result["content"][0]["text"].strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
            text = text.rsplit("```", 1)[0]
        new_notes = json.loads(text.strip())
        return {**existing_notes, **new_notes}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode()
            err = json.loads(body).get("error", {})
            detail = f"{err.get('type','')}: {err.get('message','')}"
        except Exception:
            detail = body[:300] if body else str(exc)
        print(f"      WARNING: Claude API error {exc.code} — {detail}")
        print(f"      Model in use: {ANTHROPIC_MODEL} — update ANTHROPIC_MODEL at top of script if retired.")
        return existing_notes
    except Exception as exc:
        print(f"      WARNING: AI notes unavailable ({exc}) — continuing without notes.")
        return existing_notes
_SPRINT_NOTE_DEPS = [
    "total", "completed", "completion_rate",
    "bugs", "stories", "tasks", "bug_pct",
    "rollover_count", "rollover_pct", "oos_total",
    "med_cycle_days", "avg_cycle_days", "releases_shipped",
]

def generate_sprint_notes(sprint_name, sprint_state, sp_kpis, existing_notes=None,
                          existing_sp_kpis=None, proj_context="", use_oos=True):
    """Generate AI narrative notes for a single sprint.
    Closed sprints with existing notes are locked permanently.
    Active sprints are only regenerated when the underlying KPI values change."""
    existing_notes    = existing_notes    or {}
    existing_sp_kpis  = existing_sp_kpis  or {}

    # Lock once closed and notes exist
    if sprint_state.lower() == "closed" and existing_notes:
        return existing_notes

    # Skip if notes exist and none of the input fields changed
    if existing_notes and all(sp_kpis.get(f) == existing_sp_kpis.get(f) for f in _SPRINT_NOTE_DEPS):
        return existing_notes

    note_keys = ["completion_rate", *( ["oos_total"] if use_oos else [] ),
                 "rollover", "cycle_time", "type_split"]

    if TESTING_MODE:
        return {**{k: "[test]" for k in note_keys}, **existing_notes}

    system_text = """\
You are a technical product owner writing concise notes for a Jira sprint review card on a management dashboard.
Write 1-2 sentences per metric. Be direct, factual, and actionable. Flag risks. Celebrate genuine wins briefly.
Do not pad with filler. If the sprint is ACTIVE the data is mid-sprint — frame notes accordingly.
Respond ONLY with a valid JSON object — no markdown, no backticks, no trailing commas."""
    if proj_context:
        system_text += f"\n\nTEAM CONTEXT: {proj_context}"
    oos_guidance = "\noos_total: Items added to the sprint after it started. High OOS = reactive/unplanned work. Zero = disciplined planning." if use_oos else ""
    oos_return   = ',"oos_total":"..."' if use_oos else ""
    system_text += f"""

METRIC GUIDANCE:
completion_rate: % of sprint items completed. 80%+ healthy. Below 60% is a concern. Active sprint: comment on trajectory.{oos_guidance}
rollover: Items carried forward from an earlier sprint in the same quarter. Works for all sprint states. Flag count and % if non-zero.
cycle_time: Median days from In Progress to Done. Under 3d excellent; 3-7d normal; over 7d flag.
type_split: Bug vs story vs task split. Flag if bugs exceed 40% of sprint items.

Return ONLY these keys (no others):
{{"completion_rate":"..."{oos_return},"rollover":"...","cycle_time":"...","type_split":"..."}}"""

    cr  = sp_kpis.get("completion_rate", 0)
    oos_line = f"\nOOS total: {sp_kpis.get('oos_total',0)}" if use_oos else ""
    user_text = f"""Sprint: {sprint_name}
State: {sprint_state}
Total: {sp_kpis.get("total",0)}  Completed: {sp_kpis.get("completed",0)} ({cr}%)
Bug/Story/Task: {sp_kpis.get("bugs",0)}/{sp_kpis.get("stories",0)}/{sp_kpis.get("tasks",0)} ({sp_kpis.get("bug_pct",0)}% bugs)
Rollover: {sp_kpis.get("rollover_count",0)} items ({sp_kpis.get("rollover_pct",0)}%){oos_line}
Cycle time: {sp_kpis.get("med_cycle_days",0)}d median ({sp_kpis.get("avg_cycle_days",0)}d avg)
Releases: {sp_kpis.get("releases_shipped",0)}"""

    body = {
        "model":      ANTHROPIC_MODEL,
        "max_tokens": 600,
        "system":     [{"type": "text", "text": system_text}],
        "messages":   [{"role": "user", "content": user_text}],
    }
    headers = {
        "Content-Type":    "application/json",
        "x-api-key":       ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
        text = result["content"][0]["text"].strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:]).rsplit("```", 1)[0]
        return json.loads(text.strip())
    except Exception as exc:
        print(f"      WARNING: sprint notes failed for {sprint_name} ({exc})")
        return existing_notes


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def ensure_dirs(proj):
    os.makedirs(proj["data_dir"],    exist_ok=True)
    os.makedirs(proj["archive_dir"], exist_ok=True)
    os.makedirs(proj["reports_dir"], exist_ok=True)
    os.makedirs(DASHBOARD_OUTPUT_DIR, exist_ok=True)


def save_quarter_data(kpis, notes, sprints, proj, notes_generated_at=None):
    key  = quarter_file_key(kpis["quarter"])
    path = os.path.join(proj["data_dir"], f"{key}.json")
    now  = datetime.now(timezone.utc).isoformat()
    payload = {
        "quarter":            kpis["quarter"],
        "kpis":               kpis,
        "notes":              notes,
        "sprints":            sprints,
        "saved_at":           now,
        "notes_generated_at": notes_generated_at or now,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"      Saved data: {path}")
    return path


def load_all_quarters(proj):
    """Load all saved quarter JSON files for a project, sorted newest-first."""
    pattern = os.path.join(proj["data_dir"], "Q*.json")

    def _quarter_sort_key(path):
        name = os.path.basename(path).replace(".json", "")  # e.g. "Q3_2025"
        q, year = name.split("_")
        return (int(year), int(q[1:]))

    quarters = {}
    for f in sorted(glob.glob(pattern), key=_quarter_sort_key, reverse=True):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            quarters[data["quarter"]] = data
        except Exception as e:
            print(f"      Warning: could not load {f}: {e}")
    return quarters


def archive_old_quarters(all_quarters, current_quarter, proj):
    """Write a frozen standalone HTML for any quarter that isn't the current one."""
    for q_label, data in all_quarters.items():
        if q_label == current_quarter:
            continue
        html_path = os.path.join(proj["archive_dir"], quarter_file_key(q_label) + ".html")
        if os.path.exists(html_path):
            continue
        print(f"      Archiving {q_label} → {os.path.basename(html_path)}")
        # Archive uses single-project data for this project only
        proj_data = {proj["key"]: {"qs": {q_label: data}, "proj_key": proj["key"],
                                   "board_id": proj["board_id"], "display": proj["display"]}}
        html = _render_html(proj_data)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__DASHBOARD_TITLE__</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>">
<link rel="stylesheet" href="assets/quarters_style__ASSET_SUFFIX__.css?v=__ASSET_VERSION__">
</head>
<body>
__PREVIEW_BANNER__
<header id="site-header">
  <div class="header-top">
    <div class="logo-wrap">
      <img src="assets/logo.png?v=__ASSET_VERSION__" alt="__LOGO_ALT__" class="site-logo">
    </div>
    <div class="hdr-center">
      <div class="logo"><span id="proj-name"></span> Quarter Dashboard</div>
      <div class="qs">
        <input type="text" id="q-input" readonly placeholder="Select quarter…">
        <span class="q-arrow">▼</span>
        <div class="q-dd" id="q-dd">
          <input class="q-search" id="q-search" placeholder="Search quarters…">
          <div id="q-opts"></div>
        </div>
      </div>
      <span class="logo-sub" id="hdr-sprint"></span>
    </div>
    <div class="hdr-right">
      <div class="proj-tabs" id="proj-tabs"></div>
      <div class="as-of" id="as-of"></div>
      <button id="refresh-btn" title="Regenerate dashboard data" style="display:none">↻ Refresh</button>
      <a href="mailto:hugh.odwyer@datamars.com?subject=Dashboard%20Feedback&body=Page%3A%20__DASHBOARD_TITLE__%0A%0AFeedback%3A%0A" title="Send feedback" id="feedback-btn">&#x2709; Feedback</a>
    </div>
  </div>
  <div class="tabs-bar" id="tabs-bar"></div>
</header>

<div id="refresh-banner"></div>

<!-- Refresh modal -->
<div class="modal-backdrop" id="refresh-modal">
  <div class="modal-box">
    <h3 id="refresh-modal-title"></h3>
    <p id="refresh-modal-msg"></p>
    <button class="modal-close" onclick="document.getElementById('refresh-modal').classList.remove('open')">OK</button>
  </div>
</div>

<div id="sprint-sel-bar"><label id="excl-toggle-hdr" class="excl-toggle" style="display:none"><input type="checkbox" id="exclCb"> Show excluded</label></div>
<div id="trends-toolbar" style="display:none"><label id="excl-toggle-trends" class="excl-toggle" style="display:none"><input type="checkbox" id="exclCbTrends"> Show excluded</label></div>
<main id="dash"><div class="nodata">Loading…</div></main>
<button id="btt" title="Back to top" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑</button>

<script>
const ALL_DATA=__ALL_DATA_JSON__;
const WLOG_ADMINS=__WLOG_ADMINS_JSON__;
const REFRESH_WEBHOOK=__REFRESH_WEBHOOK_URL__;
const REFRESH_DATA_WEBHOOK=__REFRESH_DATA_WEBHOOK_URL__;
const REFRESH_REQUEST_WEBHOOK=__REFRESH_REQUEST_WEBHOOK_URL__;
const NOTES_REFRESH_TIME=__NOTES_REFRESH_TIME__;
const LAST_REFRESH_TS=__LAST_REFRESH_TS__;
</script>
<script src="assets/quarters_script__ASSET_SUFFIX__.js?v=__ASSET_VERSION__"></script>
<div id="tt"></div>
<div id="cf-access-notice" style="display:none;position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1e293b;color:#f8fafc;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:500;align-items:center;gap:10px;box-shadow:0 4px 12px rgba(0,0,0,.3);z-index:9999">
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="#f59e0b" stroke-width="1.5"/><path d="M8 5v4M8 11v.5" stroke="#f59e0b" stroke-width="1.5" stroke-linecap="round"/></svg>
  You can only view your own time log
</div>
</body>
</html>"""


def _render_html(all_projects_data, preview=False):
    """Render the HTML template.
    CSS and JS are served as external files from the output directory.
    Only the data payload is injected inline.
    """
    # ensure_ascii=True escapes all non-ASCII chars as \uXXXX — immune to encoding corruption
    # and prevents U+2028/U+2029 line separators breaking the script tag.
    all_data_json = json.dumps(all_projects_data, default=str, ensure_ascii=True)
    # Escape </ so </script> in any value can't terminate the script tag early
    all_data_json = all_data_json.replace("</", "<\\/")
    webhook_json  = json.dumps(REFRESH_WEBHOOK_URL)
    notes_refresh_time_json = json.dumps(NOTES_REFRESH_TIME)
    # Read last_refresh.json to get the timestamp of the last full run
    _last_refresh_path = os.path.join(DASHBOARD_OUTPUT_DIR, "data", "last_refresh.json")
    try:
        _last_refresh_ts = json.loads(open(_last_refresh_path, encoding="utf-8").read()).get("timestamp", "")
    except Exception:
        _last_refresh_ts = ""
    last_refresh_ts_json = json.dumps(_last_refresh_ts)
    # Cache-busting version string — changes every run so browsers always fetch fresh assets
    asset_version = str(int(datetime.now().timestamp()))
    preview_banner = (
        '<div style="background:#b45309;color:#fff;text-align:center;padding:6px 12px;'
        'font-size:13px;font-weight:700;letter-spacing:.04em;position:sticky;top:0;z-index:9998">'
        '⚠ PREVIEW — this is a test build. '
        f'<a href="{DASHBOARD_FILENAME}" style="color:#fde68a;text-decoration:underline">Go to live dashboard →</a>'
        '</div>'
    ) if preview else ""
    return (
        _HTML_TEMPLATE
        .replace("__ALL_DATA_JSON__",      all_data_json)
        .replace("__WLOG_ADMINS_JSON__",   json.dumps(WLOG_ADMINS, ensure_ascii=True))
        .replace("__REFRESH_WEBHOOK_URL__",      webhook_json)
        .replace("__REFRESH_DATA_WEBHOOK_URL__",     json.dumps(REFRESH_DATA_WEBHOOK_URL))
        .replace("__REFRESH_REQUEST_WEBHOOK_URL__",  json.dumps(REFRESH_REQUEST_WEBHOOK_URL))
        .replace("__NOTES_REFRESH_TIME__",     notes_refresh_time_json)
        .replace("__LAST_REFRESH_TS__",        last_refresh_ts_json)
        .replace("__PREVIEW_BANNER__",     preview_banner)
        .replace("__DASHBOARD_TITLE__",    DASHBOARD_TITLE)
        .replace("__LOGO_ALT__",           LOGO_ALT)
        .replace("__ASSET_VERSION__",      asset_version)
        .replace("__ASSET_SUFFIX__",       "_dev" if preview else "")
    )


def generate_html_dashboard(all_projects_data):
    import shutil
    _here    = pathlib.Path(__file__).parent
    _out_dir = pathlib.Path(DASHBOARD_OUTPUT_DIR)

    # Copy CSS and JS into assets/ subfolder.
    # Dev assets (quarters_script_dev.js / quarters_style_dev.css) are kept separate
    # from live assets so test builds never overwrite what the live dashboard serves.
    _assets_dir = _out_dir / "assets"
    _assets_dir.mkdir(exist_ok=True)
    for asset in ("quarters_script.js", "quarters_style.css", "logo.png"):
        src = _here / asset
        if src.exists():
            shutil.copy2(src, _assets_dir / asset)
    for asset in ("quarters_script_dev.js", "quarters_style_dev.css"):
        src = _here / asset
        if src.exists():
            shutil.copy2(src, _assets_dir / asset)

    # Always write the live page so data stays current for users
    live_path = _out_dir / DASHBOARD_FILENAME
    live_path.write_text(_render_html(all_projects_data, preview=False), encoding="utf-8")

    # Also write the preview page when PREVIEW_MODE is on
    if PREVIEW_MODE:
        preview_path = _out_dir / DASHBOARD_PREVIEW_FILE
        preview_path.write_text(_render_html(all_projects_data, preview=True), encoding="utf-8")
        return str(preview_path)

    return str(live_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _quarter_last_day(label):
    """Return the last calendar day of a quarter label like 'Q3 2025'."""
    parts   = label.split()
    q       = int(parts[0][1:])
    year    = int(parts[1])
    last_month = q * 3
    return date(year, last_month, calendar.monthrange(year, last_month)[1])


def _enrich_past_quarters_with_carryovers(kpis, all_quarters, proj):
    """Push carry-in markers into past quarter JSONs based on the current quarter's data.

    When a carry-over item is detected in the current quarter (origin_quarter set), we
    look at every saved past quarter's in_progress list and update any matching issue row
    with the correct carry-in metadata relative to that quarter's end date — so past
    quarter dashboards show stale items without needing a full Jira backfill.
    """
    carry_overs = {
        row["key"]: row
        for row in kpis["issues"]["in_progress"]
        if row.get("origin_quarter") and row.get("ip_date")
    }
    if not carry_overs:
        return

    updated = []
    for q_label, q_data in all_quarters.items():
        if q_label == kpis["quarter"]:
            continue

        q_end    = _quarter_last_day(q_label)
        q_start  = date(q_end.year, q_end.month - 2, 1)
        q_end_s  = str(q_end)
        ip_list  = q_data.get("kpis", {}).get("issues", {}).get("in_progress", [])
        if not ip_list:
            continue

        changed = False
        for row in ip_list:
            if row.get("resolved_quarter"):
                continue  # already tagged as resolved in a later quarter — leave it
            co = carry_overs.get(row["key"])
            if not co:
                continue

            ip_d = date.fromisoformat(co["ip_date"])
            if ip_d >= q_start:
                continue  # item started within this past quarter — not a carry-in for it

            orig_q = ((ip_d.month  - 1) // 3) + 1
            past_q = ((q_end.month - 1) // 3) + 1
            qc = (q_end.year - ip_d.year) * 4 + (past_q - orig_q)

            new_cls = "carried-in-long" if qc >= 2 else "carried-in"
            if (row.get("quarters_carried") != qc
                    or row.get("origin_quarter") != co["origin_quarter"]
                    or row.get("_rowCls") != new_cls):
                row["origin_quarter"]   = co["origin_quarter"]
                row["ip_date"]          = co["ip_date"]
                row["quarters_carried"] = qc
                row["_rowCls"]          = new_cls
                changed = True

        if changed:
            path = os.path.join(proj["data_dir"], f"{quarter_file_key(q_label)}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(q_data, f, indent=2, default=str)
            updated.append(q_label)

    if updated:
        print(f"      Carry-in markers pushed to: {', '.join(updated)}")


def _get_prev_sprint_id(proj, current_sprints):
    """Return (sprint_id, end_date_str) for the sprint immediately before this quarter,
    or (None, None) if no saved data exists yet."""
    if not current_sprints:
        return None, None
    first_start = current_sprints[0]["start_date"]
    best_id, best_end = None, ""
    for f in glob.glob(os.path.join(proj["data_dir"], "Q*.json")):
        try:
            saved = json.loads(open(f, encoding="utf-8").read())
            for s in saved.get("sprints", []):
                end = s.get("end_date") or ""
                if end and end < first_start and end > best_end:
                    best_end, best_id = end, s["id"]
        except Exception:
            pass
    return best_id, (best_end or None)


def _run_quarter(proj, ref=None, skip_notes=False):
    """Fetch, compute, and save data for one quarter of one project. ref=None = current quarter.
    skip_notes=True reuses existing Claude notes without making any API calls."""
    global _ACTIVE_PROJECT_KEY, _ACTIVE_SP_FIELD
    _ACTIVE_PROJECT_KEY = proj["key"]
    _ACTIVE_SP_FIELD    = proj.get("story_points_field") or "customfield_10016"

    print(f"\n{'='*52}")
    print(f"Project : {proj['display']}  |  Quarter: {quarter_label(ref)} (starts {current_quarter_start(ref)})")

    print("\n[1/4] Discovering sprints...")
    raw_sprints = fetch_sprints_in_quarter(proj, ref)
    if not raw_sprints:
        print("      No sprints found — skipping.")
        return None
    sprints = classify_sprints(raw_sprints)
    for s in sprints:
        print(f"      {s['name']}  [{s['status_label']}]  {s['start_date']} → {s['end_date']}")

    print(f"\n[2/4] Fetching KPIs from Jira ({len(sprints)} sprints)...")
    prev_sprint_id, prev_sprint_end = _get_prev_sprint_id(proj, sprints)
    if prev_sprint_id:
        print(f"      Previous quarter last sprint: {prev_sprint_id} (ends {prev_sprint_end})")
    kpis = fetch_kpis(sprints, proj, ref, prev_sprint_id=prev_sprint_id, prev_sprint_end=prev_sprint_end)
    if proj.get("use_story_points"):
        print(f"      Total: {kpis['total']} | Done: {kpis['completed']} | "
              f"Rollover: {kpis['rollover_count']} | Cycle: {kpis['avg_cycle_days']}d | "
              f"SP: {kpis['sp_completed']}/{kpis['sp_total']} | No-SP-est: {kpis['no_estimate_count']}")
    else:
        print(f"      Total: {kpis['total']} | Done: {kpis['completed']} | "
              f"Rollover: {kpis['rollover_count']} | Cycle: {kpis['avg_cycle_days']}d | "
              f"Logged: {kpis['time_logged_h']}h | No-estimate: {kpis['no_estimate_count']}")
    _update_developer_roster(kpis.get("assignee_stats", []))

    existing_json_path = os.path.join(proj["data_dir"], f"{quarter_file_key(kpis['quarter'])}.json")
    existing_saved = {}
    if os.path.exists(existing_json_path):
        try:
            existing_saved = json.loads(open(existing_json_path, encoding="utf-8").read())
        except Exception:
            pass

    if skip_notes:
        print("\n[3/4] Skipping Claude notes (data-only run) — reusing saved notes...")
        notes = existing_saved.get("notes", {})
        notes_generated_at = existing_saved.get("notes_generated_at")
        for sid, spd in kpis["per_sprint"].items():
            spd["notes"] = existing_saved.get("kpis", {}).get("per_sprint", {}).get(sid, {}).get("notes", {})
        print(f"      Reused notes for {len(notes)} quarter key(s); sprint notes carried forward.")
    else:
        print("\n[3/4] Generating notes via Claude...")
        existing_notes = {}
        existing_kpis  = {}
        if not FORCE_NOTES:
            existing_notes = existing_saved.get("notes", {})
            existing_kpis  = existing_saved.get("kpis",  {})
        notes = generate_notes(kpis, sprints, existing_notes, existing_kpis,
                               proj_context=proj.get("notes_context", ""))
        quarter_notes_generated = (notes != existing_notes)
        print(f"      Notes populated: {', '.join(notes.keys()) if notes else 'none (skipped)'}")

        # Sprint notes — only regenerated when KPI values change; closed sprints locked permanently
        print("      Generating sprint notes...")
        existing_per_sprint_notes = {}
        existing_per_sprint_kpis  = {}
        if not FORCE_NOTES:
            for sid, spd in existing_saved.get("kpis", {}).get("per_sprint", {}).items():
                existing_per_sprint_notes[sid] = spd.get("notes", {})
                existing_per_sprint_kpis[sid]  = spd
        any_sprint_generated = False
        for sid, spd in kpis["per_sprint"].items():
            prev_notes = existing_per_sprint_notes.get(sid, {})
            prev_kpis  = existing_per_sprint_kpis.get(sid, {})
            new_notes  = generate_sprint_notes(spd["sprint_name"], spd["sprint_state"], spd,
                                               prev_notes, prev_kpis,
                                               proj_context=proj.get("notes_context", ""),
                                               use_oos=proj.get("use_oos", True))
            spd["notes"] = new_notes
            locked    = spd["sprint_state"].lower() == "closed" and bool(prev_notes)
            unchanged = (not locked) and (new_notes is prev_notes or new_notes == prev_notes)
            if not locked and not unchanged:
                any_sprint_generated = True
            print(f"        {spd['sprint_name']}: {'locked' if locked else ('unchanged' if unchanged else 'generated')}")
        anything_generated = quarter_notes_generated or any_sprint_generated
        notes_generated_at = datetime.now(timezone.utc).isoformat() if anything_generated else existing_saved.get("notes_generated_at")

    print("\n[4/4] Saving quarter data...")
    save_quarter_data(kpis, notes, sprints, proj, notes_generated_at=notes_generated_at)

    all_quarters = load_all_quarters(proj)
    _enrich_past_quarters_with_carryovers(kpis, all_quarters, proj)
    archive_old_quarters(all_quarters, kpis["quarter"], proj)
    print(f"      {kpis['as_of']}")
    return all_quarters


def main():
    parser = argparse.ArgumentParser(description="Quarter Dashboard generator")
    parser.add_argument(
        "--data-only", action="store_true",
        help="Refresh Jira data only — skip Claude API calls and reuse existing notes."
    )
    parser.add_argument(
        "--force-notes", action="store_true",
        help="Force regeneration of all Claude notes even if KPI values are unchanged."
    )
    args = parser.parse_args()
    skip_notes  = args.data_only
    force_notes = args.force_notes

    # CLI --force-notes overrides the module-level constant
    global FORCE_NOTES
    if force_notes:
        FORCE_NOTES = True

    print("=== Quarter Dashboard — Multi-Project ===")
    if skip_notes:
        print("Mode: DATA-ONLY (Claude notes unchanged)")
    elif FORCE_NOTES:
        print("Mode: FORCE-NOTES (all Claude notes will be regenerated)")
    for proj in PROJECTS:
        print(f"\n{'#'*52}")
        print(f"# Project: {proj['display']} (board {proj['board_id']})")
        ensure_dirs(proj)

    all_projects_data = {}
    refs = [_quarter_last_day(q) for q in BACKFILL_QUARTERS] + [None]

    for proj in PROJECTS:
        print(f"\n{'#'*52}")
        print(f"# Processing: {proj['display']}")
        proj_quarters = {}
        for ref in refs:
            result = _run_quarter(proj, ref, skip_notes=skip_notes)
            if result:
                proj_quarters = result  # load_all_quarters returns full set each time
        all_projects_data[proj["key"]] = {
            "qs":              proj_quarters,
            "proj_key":        proj["key"],
            "board_id":        proj["board_id"],
            "display":         proj["display"],
            "use_story_points": proj.get("use_story_points", False),
            "use_oos":          proj.get("use_oos", True),
        }

    print(f"\n{'='*52}")
    print("Building combined HTML dashboard...")
    path = generate_html_dashboard(all_projects_data)
    print(f"Dashboard: {path}")
    if DASHBOARD_BASE_URL:
        live_url    = DASHBOARD_BASE_URL.rstrip("/") + "/" + DASHBOARD_FILENAME
        preview_url = DASHBOARD_BASE_URL.rstrip("/") + "/" + DASHBOARD_PREVIEW_FILE
        print(f"\nDone. Live: {live_url}")
        if PREVIEW_MODE:
            print(f"      Preview: {preview_url}")
            print(f"      Both files updated — live page data is current.")
    else:
        print(f"\nDone. Output: {path}")


if __name__ == "__main__":
    main()