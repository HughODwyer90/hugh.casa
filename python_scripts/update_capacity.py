#!/usr/bin/env python3
"""
update_capacity.py — called by Home Assistant when a capacity edit is made in the dashboard.

HA passes the webhook payload as a JSON file path in argv[1], or pipes JSON to stdin.

Payload format:
  {"project": "DLK", "account_id": "712020:abc...", "name": "Igor Schouten", "capacity_h": 64}

The script finds the team JSON for that project and updates (or adds) capacity_h for that account.
"""

import sys
import json
import pathlib

# Map project key (uppercase) → team JSON filename, same dir as this script
_HERE = pathlib.Path(__file__).parent

# Build map from PROJECTS in quarters_report_dev.py dynamically by scanning for team files,
# or just read the same secrets/config. Simplest: look for team_members_{key}.json files.
def _find_team_file(project_key):
    key = project_key.lower()
    candidates = [
        _HERE / f"team_members_{key}.json",
        _HERE / f"team_members_{key.upper()}.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def main():
    # Read payload — from file path in argv[1] or stdin
    if len(sys.argv) > 1:
        payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    else:
        payload = json.loads(sys.stdin.read())

    project    = payload.get("project", "").upper()
    account_id = payload.get("account_id", "").strip()
    name       = payload.get("name", "").strip()
    capacity_h = payload.get("capacity_h")

    if not project or not account_id or capacity_h is None:
        print("ERROR: missing project, account_id, or capacity_h in payload", file=sys.stderr)
        sys.exit(1)

    capacity_h = float(capacity_h)
    if capacity_h <= 0:
        print(f"ERROR: capacity_h must be > 0, got {capacity_h}", file=sys.stderr)
        sys.exit(1)

    team_file = _find_team_file(project)
    if not team_file:
        print(f"ERROR: no team file found for project {project}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(team_file.read_text(encoding="utf-8"))

    if account_id in data:
        entry = data[account_id]
        if isinstance(entry, str):
            # Legacy flat format — upgrade to object
            data[account_id] = {"name": entry, "capacity_h": capacity_h}
        else:
            data[account_id]["capacity_h"] = capacity_h
    else:
        # Account not in file yet — add it
        data[account_id] = {"name": name, "capacity_h": capacity_h}
        print(f"NOTE: {account_id} ({name}) was not in {team_file.name} — added.")

    team_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"OK: set {name} ({account_id}) capacity_h={capacity_h} in {team_file.name}")


if __name__ == "__main__":
    main()