#!/usr/bin/env python3
"""Promote dev assets to live.

Copies the three dev files over their live counterparts:
  quarters_script_dev.js   -> quarters_script.js
  quarters_style_dev.css   -> quarters_style_dev.css -> quarters_style.css
  dlk_quarter_report_dev.py -> dlk_quarter_report.py
"""
import shutil
import pathlib

HERE = pathlib.Path(__file__).parent

PROMOTIONS = [
    ("quarters_script_dev.js",    "quarters_script.js"),
    ("quarters_style_dev.css",    "quarters_style.css"),
    ("dlk_quarter_report_dev.py", "dlk_quarter_report.py"),
]

for src_name, dst_name in PROMOTIONS:
    src = HERE / src_name
    dst = HERE / dst_name
    if not src.exists():
        print(f"  SKIP  {src_name} (not found)")
        continue
    shutil.copy2(src, dst)
    print(f"  OK    {src_name} -> {dst_name}")

# Ensure the promoted report script runs in live mode
report = HERE / "dlk_quarter_report.py"
if report.exists():
    text = report.read_text(encoding="utf-8")
    patched = text.replace(
        "PREVIEW_MODE  = True   # DEV: always on. Set to False when copying to live. — live page untouched",
        "PREVIEW_MODE  = False  # Set to True to write to test.html instead of the live page",
    )
    if patched != text:
        report.write_text(patched, encoding="utf-8")
        print("  OK    PREVIEW_MODE set to False in dlk_quarter_report.py")
    else:
        print("  WARN  Could not find PREVIEW_MODE line to patch — check manually")

print("\nDone. Run dlk_quarter_report.py to redeploy.")