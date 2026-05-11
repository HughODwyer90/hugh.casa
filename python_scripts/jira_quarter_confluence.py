#!/usr/bin/env python3
"""
DLK Sprint Report — Automated updater
Dynamically discovers all DLK sprints started in the current quarter,
pulls live KPIs from Jira, generates narrative via Claude API,
then updates the Confluence page.
"""

import json
import uuid
import base64
import urllib.request
import urllib.parse
from datetime import datetime, timezone, date, time
from zoneinfo import ZoneInfo
from secret_manager import SecretsManager

secrets = SecretsManager()

JIRA_BASE_URL        = secrets["jira_base_url"].rstrip("/")
JIRA_EMAIL           = secrets["jira_username"]
JIRA_API_TOKEN       = secrets["jira_api_token"]

CONFLUENCE_PAGE_ID   = secrets.get("confluence_page_id", "3578724420")
CONFLUENCE_SPACE_KEY = secrets.get("confluence_space_key", "SF")

ANTHROPIC_API_KEY    = secrets["anthropic_api_key"]

JIRA_BOARD_ID        = secrets.get("jira_board_id", "136")

CONFLUENCE_BASE_URL  = JIRA_BASE_URL
JIRA_CLOUD_ID        = "421579de-9f66-4d01-98ad-937a48a63d28"

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


def http_put(url, headers, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Quarter helpers
# ---------------------------------------------------------------------------

def current_quarter_start():
    today = date.today()
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    return date(today.year, quarter_month, 1)


def quarter_label():
    today = date.today()
    q = ((today.month - 1) // 3) + 1
    return f"Q{q} {today.year}"


# ---------------------------------------------------------------------------
# Sprint discovery
# ---------------------------------------------------------------------------

def fetch_sprints_in_quarter():
    """
    Discover sprints via the agile board API.
    Includes any sprint that overlaps with the current quarter,
    even if it started before the quarter boundary.
    """
    headers = _auth_header()
    quarter_start = current_quarter_start()
    today = date.today()

    board_url = f"{JIRA_BASE_URL}/rest/agile/1.0/board?projectKeyOrId=DLK&maxResults=50"
    board_data = http_get(board_url, headers)
    boards = board_data.get("values", [])
    if not boards:
        raise RuntimeError("No boards found for project DLK")

    preferred = next(
        (b for b in boards if str(b["id"]) == str(JIRA_BOARD_ID)),
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

                # Include sprint if it overlaps with the current quarter at all
                sprint_end = end_date or today
                if not (sprint_start <= today and sprint_end >= quarter_start):
                    continue

                seen[sid] = {
                    "id": sid,
                    "name": sprint["name"],
                    "state": sprint["state"],
                    "start_date": sprint_start,
                    "end_date": end_date,
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
# Jira issue fetching
# ---------------------------------------------------------------------------

def jira_search(jql, fields="key,summary,status,issuetype,assignee,fixVersions,labels,priority",
                max_results=500):
    headers = _auth_header()
    all_issues = []
    next_page_token = None

    while True:
        params = {
            "jql": jql,
            "fields": fields,
            "maxResults": 100,
        }
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


# ---------------------------------------------------------------------------
# KPI calculation
# ---------------------------------------------------------------------------

def fetch_kpis(sprints):
    sprint_ids = [str(s["id"]) for s in sprints]
    sprint_clause = ", ".join(sprint_ids)
    base_jql = f"project = DLK AND sprint in ({sprint_clause})"

    print(f"  Querying: {base_jql[:90]}...")
    all_issues = jira_search(base_jql)

    completed   = [i for i in all_issues
                   if i["fields"]["status"]["statusCategory"]["key"] == "done"]
    in_progress = [i for i in all_issues
                   if i["fields"]["status"]["statusCategory"]["key"] == "indeterminate"]

    oos_all  = [i for i in all_issues
                if "Out_Of_Sprint" in i["fields"].get("labels", [])]
    oos_open = [i for i in oos_all
                if i["fields"]["status"]["statusCategory"]["key"] != "done"]

    version_ids = {}
    versions = {}

    for issue in completed:
        for v in issue["fields"].get("fixVersions", []):
            if not v.get("released", False):
                continue

            versions[v["name"]] = versions.get(v["name"], 0) + 1

            if v["name"] not in version_ids:
                version_ids[v["name"]] = v.get("id", "")

    type_counts = {}
    for issue in all_issues:
        t = issue["fields"]["issuetype"]["name"]
        type_counts[t] = type_counts.get(t, 0) + 1

    total   = len(all_issues)
    bugs    = type_counts.get("Bug", 0)
    stories = type_counts.get("Story", 0)
    tasks   = type_counts.get("Task", 0)
    closed_sprint_count = sum(1 for s in sprints if s["state"].lower() == "closed")

    open_oos_detail = []
    for issue in oos_open:
        assignee = issue["fields"].get("assignee")
        open_oos_detail.append({
            "key": issue["key"],
            "summary": issue["fields"]["summary"],
            "assignee": assignee["displayName"] if assignee else "Unassigned",
            "status": issue["fields"]["status"]["name"],
            "priority": issue["fields"].get("priority", {}).get("name", ""),
        })

    return {
        "total": total,
        "completed": len(completed),
        "in_progress": len(in_progress),
        "completion_rate": round(len(completed) / total * 100) if total else 0,
        "releases_shipped": len(versions),
        "avg_releases_per_sprint": round(
            len(versions) / closed_sprint_count, 1
        ) if closed_sprint_count else 0,
        "oos_total": len(oos_all),
        "oos_open": len(oos_open),
        "oos_pct": round(len(oos_all) / total * 100) if total else 0,
        "oos_open_detail": open_oos_detail,
        "bugs": bugs,
        "stories": stories,
        "tasks": tasks,
        "bug_pct": round(bugs / total * 100) if total else 0,
        "versions": versions,
        "version_ids": version_ids,
        "sprint_count": len(sprints),
        "closed_sprint_count": closed_sprint_count,
        "quarter": quarter_label(),
        "quarter_start": str(current_quarter_start()),
        "sprints": sprint_ids,
        "as_of": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    }


# ---------------------------------------------------------------------------
# Claude — generate narrative notes
# ---------------------------------------------------------------------------

def generate_notes(kpis, sprints):
    current_sprint = next(
        (s["name"] for s in sprints if s["state"].lower() == "active"), None
    )
    prompt = f"""You are a technical product owner writing a brief management sprint report.
Given the following Jira KPI data for {kpis['quarter']}, write a SHORT (max 12 words)
management-friendly note for each metric. Be factual. Flag anything needing attention.
Respond ONLY with a JSON object — no markdown, no preamble, no backticks.

Context:
- Quarter: {kpis['quarter']} (started {kpis['quarter_start']})
- Sprints covered: {', '.join(kpis['sprints'])}
- Current sprint: {current_sprint or 'none active'}
- Open OOS items: {json.dumps(kpis['oos_open_detail'])}

KPI data:
{json.dumps(kpis, indent=2)}

Return exactly this JSON structure:
{{
  "total": "<note>",
  "completed": "<note>",
  "completion_rate": "<note>",
  "releases_shipped": "<note>",
  "oos_total": "<note>",
  "oos_open": "<note>",
  "type_split": "<note>",
  "avg_releases": "<note>"
}}"""

    body = {
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())

    text = result["content"][0]["text"].strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# ADF helpers
# ---------------------------------------------------------------------------

def txt(t, bold=False, url=None):
    node = {"type": "text", "text": t}
    marks = []
    if bold:
        marks.append({"type": "strong"})
    if url:
        marks.append({"type": "link", "attrs": {"href": url}})
    if marks:
        node["marks"] = marks
    return node


def para(*content):
    return {"type": "paragraph", "content": list(content)}


def heading(level, t):
    return {"type": "heading", "attrs": {"level": level}, "content": [txt(t)]}


def status_node(label, color):
    return {"type": "status", "attrs": {"text": label, "color": color, "style": "bold"}}


def th(t):
    return {"type": "tableHeader", "attrs": {"colspan": 1, "rowspan": 1},
            "content": [para(txt(t, bold=True))]}


def td(*content):
    return {"type": "tableCell", "attrs": {"colspan": 1, "rowspan": 1},
            "content": [para(*content)]}


def tr(*cells):
    return {"type": "tableRow", "content": list(cells)}


def table(rows, layout="default"):
    return {
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": layout},
        "content": rows,
    }


def panel(panel_type, *content):
    return {"type": "panel", "attrs": {"panelType": panel_type}, "content": list(content)}


def jira_work_items(jql, columns):
    """Jira Work Items blockCard — live datasource table, full width."""
    col_keys = [{"key": c.strip()} for c in columns.split(",")]
    encoded_jql = urllib.parse.quote(jql)
    return {
        "type": "blockCard",
        "attrs": {
            "layout": "full-width",
            "datasource": {
                "id": "d8b75300-dfda-4519-b6cd-e49abbd50401",
                "parameters": {
                    "cloudId": JIRA_CLOUD_ID,
                    "jql": jql,
                },
                "views": [{
                    "type": "table",
                    "properties": {
                        "columns": col_keys
                    }
                }]
            },
            "localId": str(uuid.uuid4()),
            "url": f"https://datamars.atlassian.net/issues/?jql={encoded_jql}",
        }
    }


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def build_page(kpis, notes, sprints):
    sprint_ids    = [str(s["id"]) for s in sprints]
    sprint_clause = ", ".join(sprint_ids)
    base_jql      = f"project = DLK AND sprint in ({sprint_clause})"
    first_sprint  = sprints[0]["name"].replace("DLK ", "") if sprints else ""
    last_sprint   = sprints[-1]["name"].replace("DLK ", "") if sprints else ""

    # Open OOS notes cell content with linked issue keys
    if kpis["oos_open"] == 0:
        oos_val     = status_node("0 — clear", "green")
        oos_content = [txt("All out-of-sprint items resolved.")]
    else:
        oos_val = status_node(
            f"{kpis['oos_open']} — needs attention",
            "red" if kpis["oos_open"] > 2 else "yellow"
        )
        oos_content = []
        for i in kpis["oos_open_detail"][:3]:
            issue_url = f"https://datamars.atlassian.net/browse/{i['key']}"
            oos_content.append(txt(i["key"], url=issue_url))
            oos_content.append(txt(f" ({i['assignee']}, {i['status']})  "))

    # Version links for releases shipped notes cell
    version_links = []
    for name, vid in kpis.get("version_ids", {}).items():
        version_url = (
            f"https://datamars.atlassian.net/projects/DLK/versions/{vid}"
            f"/tab/release-report-all-issues"
        )
        version_links.append(txt(name, url=version_url))
        version_links.append(txt("  "))

    # Sprint overview table with linked sprint names
    sprint_rows = [tr(th("Sprint"), th("Dates"), th("Status"), th("State"))]
    for s in sprints:
        date_str = ""
        if s.get("start_date") and s.get("end_date"):
            date_str = (f"{s['start_date'].strftime('%d %b')} – "
                        f"{s['end_date'].strftime('%d %b %Y')}")
        elif s.get("start_date"):
            date_str = f"From {s['start_date'].strftime('%d %b %Y')}"
        sprint_url = (
            f"https://datamars.atlassian.net/jira/software/projects/DLK"
            f"/boards/{JIRA_BOARD_ID}?sprint={s['id']}"
        )
        sprint_rows.append(tr(
            td(txt(s["name"], url=sprint_url)),
            td(txt(date_str)),
            td(status_node(s["status_label"], s["status_color"])),
            td(txt(s["state"].capitalize())),
        ))

    # KPI table
    kpi_rows = [
        tr(th("Metric"), th("Value"), th("Notes")),
        tr(td(txt("Total items in period")),
           td(txt(str(kpis["total"]), bold=True)),
           td(txt(notes.get("total", f"Across {kpis['sprint_count']} sprints in {kpis['quarter']}")))),
        tr(td(txt("Items completed / released")),
           td(txt(str(kpis["completed"]), bold=True)),
           td(txt(notes.get("completed", "Status: Released, Closed or Merged")))),
        tr(td(txt("Completion rate")),
           td(txt(f"{kpis['completion_rate']}%", bold=True)),
           td(txt(notes.get("completion_rate", "")))),
        tr(td(txt("Releases shipped")),
           td(txt(str(kpis["releases_shipped"]), bold=True)),
           td(*(version_links if version_links else [txt(notes.get("releases_shipped", ""))]))),
        tr(td(txt("Out-of-sprint items")),
           td(txt(f"{kpis['oos_total']}  ({kpis['oos_pct']}% of total)", bold=True)),
           td(txt(notes.get("oos_total", "")))),
        tr(td(txt("Open OOS items (unresolved)")),
           td(oos_val),
           td(*oos_content)),
        tr(td(txt("Bug / Story / Task split")),
           td(txt(f"{kpis['bugs']} / {kpis['stories']} / {kpis['tasks']}", bold=True)),
           td(txt(notes.get("type_split", f"{kpis['bug_pct']}% bugs")))),
        tr(td(txt("Avg releases per closed sprint")),
           td(txt(str(kpis["avg_releases_per_sprint"]), bold=True)),
           td(txt(notes.get("avg_releases", "")))),
    ]
    irish_tz = ZoneInfo("Europe/Dublin")

    # 5pm Irish time today
    irish_5pm = datetime.combine(
        datetime.now(irish_tz).date(),
        time(17, 0),
        tzinfo=irish_tz
    )

    utc_time = irish_5pm.astimezone(ZoneInfo("UTC"))

    
    return {
        "version": 1,
        "type": "doc",
        "content": [
            panel("info", para(
                txt(f"{kpis['quarter']} | {sprints[0]['name']} → {sprints[-1]['name']} | "
                    f"Auto-updated: {kpis['as_of']}")
            )),
            heading(2, "Sprint overview"),
            table(sprint_rows),
            heading(2, f"KPIs — {kpis['quarter']} ({first_sprint} – {last_sprint})"),
            table(kpi_rows, layout="full-width"),
            heading(2, "All items in scope (live)"),
            para(txt(f"Every issue across {kpis['quarter']} sprints. Refreshes on page load.")),
            jira_work_items(
                f"{base_jql} ORDER BY sprint ASC, status ASC",
                "issuetype,key,summary,assignee,priority,status,fixVersions,labels",
            ),
            heading(2, "Out-of-sprint items (all)"),
            jira_work_items(
                f"{base_jql} AND labels = Out_Of_Sprint ORDER BY status ASC",
                "issuetype,key,summary,assignee,status,fixVersions,labels",
            ),
            heading(2, "Open out-of-sprint items (action required)"),
            jira_work_items(
                f"{base_jql} AND labels = Out_Of_Sprint AND statusCategory != Done ORDER BY priority ASC",
                "issuetype,key,summary,assignee,priority,status,labels",
            ),
            heading(2, "Released items"),
            jira_work_items(
                f"{base_jql} AND status in (Released, Closed, Merged) AND fixVersion is not EMPTY ORDER BY fixVersions ASC, key ASC",
                "issuetype,key,summary,assignee,fixVersions,labels",
            ),
            heading(2, "Still in progress"),
            jira_work_items(
                f"{base_jql} AND statusCategory != Done ORDER BY status ASC, assignee ASC",
                "issuetype,key,summary,assignee,priority,status",
            ),
            panel("note", para(
                txt(
                    f"This page is updated daily at "
                    f"{utc_time.strftime('%H:%M UTC')}."
                )
            )),
        ],
    }


# ---------------------------------------------------------------------------
# Confluence update
# ---------------------------------------------------------------------------

def get_page_meta():
    headers = _auth_header()
    url = f"{CONFLUENCE_BASE_URL}/wiki/api/v2/pages/{CONFLUENCE_PAGE_ID}"
    data = http_get(url, headers)
    return data["version"]["number"], data["title"]


def update_confluence_page(doc, title, current_version):
    headers = _auth_header()
    url = f"{CONFLUENCE_BASE_URL}/wiki/api/v2/pages/{CONFLUENCE_PAGE_ID}"
    body = {
        "id": CONFLUENCE_PAGE_ID,
        "status": "current",
        "title": title,
        "version": {
            "number": current_version + 1,
            "message": f"Auto-updated — {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}",
        },
        "body": {
            "representation": "atlas_doc_format",
            "value": json.dumps(doc),
        },
    }
    return http_put(url, headers, body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== DLK Sprint Report Updater ===")
    print(f"Quarter : {quarter_label()} (starts {current_quarter_start()})")
    print(f"Board   : {JIRA_BOARD_ID}")
    print(f"Page    : {CONFLUENCE_PAGE_ID}")

    print("\n[1/5] Discovering sprints in current quarter...")
    raw_sprints = fetch_sprints_in_quarter()
    if not raw_sprints:
        print("      No sprints found in current quarter — nothing to do.")
        return
    sprints = classify_sprints(raw_sprints)
    for s in sprints:
        print(f"      {s['name']}  [{s['status_label']}]  {s['start_date']} → {s['end_date']}")

    print(f"\n[2/5] Fetching KPIs from Jira ({len(sprints)} sprints)...")
    kpis = fetch_kpis(sprints)
    print(f"      Total: {kpis['total']} | Done: {kpis['completed']} | "
          f"In Progress: {kpis['in_progress']} | "
          f"OOS: {kpis['oos_total']} | Releases: {kpis['releases_shipped']}")

    print("\n[3/5] Generating notes via Claude...")
    notes = generate_notes(kpis, sprints)
    print(f"      Generated notes for: {', '.join(notes.keys())}")

    print("\n[4/5] Building page...")
    doc = build_page(kpis, notes, sprints)

    print("\n[5/5] Updating Confluence...")
    version, _ = get_page_meta()
    new_title = f"DLK Quarter Report — Management View ({quarter_label()})"
    result = update_confluence_page(doc, new_title, version)
    print(f"      Version {result['version']['number']} — \"{new_title}\"")

    print(f"\nDone. {kpis['as_of']}")
    print(f"View : {CONFLUENCE_BASE_URL}/wiki/spaces/{CONFLUENCE_SPACE_KEY}/pages/{CONFLUENCE_PAGE_ID}")


if __name__ == "__main__":
    main()
