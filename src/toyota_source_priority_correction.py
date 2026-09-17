#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_source_prioritized.json"
OUTPUT = BASE / "data/toyota_source_prioritized.json"
REPORT = BASE / "reports/toyota_source_priority_correction.json"

# Explicit corrections based on Toyota Malaysia brochure
# versioned/current vs 2023 historical files.

CURRENT = {
    "Corolla-GR-Sport-Brochure.txt",
    "gr86-brochure.txt",
}

HISTORICAL = {
    "Corolla-GR-Sport-eBrochure-2023.txt",
    "GR86-2023-Brochure.txt",
}

with open(INPUT, encoding="utf-8") as f:
    data = json.load(f)

changes = []

for record in data.get("records", []):

    filename = record.get("source_file")

    old = record.get("source_priority")

    if filename in CURRENT:
        new = "CURRENT_PRIMARY"
    elif filename in HISTORICAL:
        new = "HISTORICAL_OR_SECONDARY"
    else:
        continue

    if old != new:
        record["source_priority"] = new

        changes.append({
            "source_file": filename,
            "old_priority": old,
            "new_priority": new
        })

# Make sure metadata records the correction.
data["priority_correction"] = {
    "applied_at": datetime.now().isoformat(),
    "reason": "Correct current vs 2023 brochure classification",
    "changes": changes
}

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

report = {
    "generated_at": datetime.now().isoformat(),
    "changes": changes,
    "changed_records": len(changes),
    "master_modified": False,
    "output": str(OUTPUT)
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print("SOURCE PRIORITY CORRECTION")
print("=" * 75)

for x in changes:
    print(
        x["source_file"],
        "|",
        x["old_priority"],
        "->",
        x["new_priority"]
    )

print()
print("Changed records :", len(changes))
print("Output          :", OUTPUT)
print("Report          :", REPORT)
print("MASTER JSON MODIFIED : NO")
print("JSON VALID")
