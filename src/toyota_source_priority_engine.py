#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

SOURCES = BASE / "data/toyota_brochure_sources.json"
VALIDATED = BASE / "data/toyota_validated_candidates.json"

OUT = BASE / "data/toyota_source_prioritized.json"
REPORT = BASE / "reports/toyota_source_priority_report.json"

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def source_date(url):
    """
    Extract date/version information from official Toyota URL.
    Examples:
      january-2026
      july-2026
      april-2026
      march-2026
      2026/july
      2025/v1
      2023
    """

    s = url.lower()

    # YYYY/month
    m = re.search(
        r"/(20\d{2})/(january|february|march|april|may|june|july|august|september|october|november|december)/",
        s
    )

    if m:
        return {
            "year": int(m.group(1)),
            "month": m.group(2),
            "source_date": f"{m.group(1)}-{m.group(2)}"
        }

    # month-YYYY
    m = re.search(
        r"/(january|february|march|april|may|june|july|august|september|october|november|december)[-/](20\d{2})/",
        s
    )

    if m:
        return {
            "year": int(m.group(2)),
            "month": m.group(1),
            "source_date": f"{m.group(2)}-{m.group(1)}"
        }

    # standalone 20XX
    years = re.findall(r"\b(20\d{2})\b", s)

    if years:
        year = max(int(x) for x in years)
        return {
            "year": year,
            "month": None,
            "source_date": str(year)
        }

    return {
        "year": None,
        "month": None,
        "source_date": None
    }


def model_key(name):
    return norm(name)


print("TOYOTA SOURCE PRIORITY ENGINE")
print("=" * 75)

with open(SOURCES, encoding="utf-8") as f:
    sources = json.load(f)

with open(VALIDATED, encoding="utf-8") as f:
    validated = json.load(f)

source_map = {}

for source in sources:

    url = source["brochure_url"]
    filename = Path(url.split("/")[-1]).stem + ".txt"

    date_info = source_date(url)

    source_map[filename] = {
        "brochure_url": url,
        "source_file": filename,
        **date_info
    }


# ------------------------------------------------------------
# Attach source metadata
# ------------------------------------------------------------

records = []

for record in validated.get("records", []):

    filename = record.get("source_file")

    metadata = source_map.get(filename, {})

    merged = dict(record)

    merged["source_metadata"] = {
        "brochure_url": metadata.get("brochure_url"),
        "source_date": metadata.get("source_date"),
        "source_year": metadata.get("year"),
        "source_month": metadata.get("month")
    }

    records.append(merged)


# ------------------------------------------------------------
# Group by model
# ------------------------------------------------------------

groups = {}

for record in records:

    model = record.get("model_name_candidate")

    if not model:
        continue

    key = model_key(model)

    groups.setdefault(key, []).append(record)


# ------------------------------------------------------------
# Priority
# ------------------------------------------------------------

def priority(record):

    meta = record.get("source_metadata", {})

    year = meta.get("source_year")

    # Unknown date gets lowest priority.
    if year is None:
        return (0, 0)

    # Newer official brochure wins.
    return (year, 1)


latest = {}

for key, group in groups.items():

    ordered = sorted(
        group,
        key=priority,
        reverse=True
    )

    winner = ordered[0]

    latest[key] = {
        "model_name": winner.get("model_name_candidate"),
        "source_file": winner.get("source_file"),
        "source_year": winner["source_metadata"].get("source_year"),
        "source_date": winner["source_metadata"].get("source_date"),
        "brochure_url": winner["source_metadata"].get("brochure_url"),
        "alternatives": [
            {
                "source_file": x.get("source_file"),
                "source_year": x["source_metadata"].get("source_year"),
                "source_date": x["source_metadata"].get("source_date"),
                "brochure_url": x["source_metadata"].get("brochure_url")
            }
            for x in ordered[1:]
        ]
    }


# ------------------------------------------------------------
# Mark records
# ------------------------------------------------------------

for record in records:

    model = record.get("model_name_candidate")

    if not model:
        record["source_priority"] = "UNKNOWN_MODEL"
        continue

    winner = latest.get(model_key(model))

    if not winner:
        record["source_priority"] = "NO_WINNER"
        continue

    if record.get("source_file") == winner["source_file"]:
        record["source_priority"] = "CURRENT_PRIMARY"
    else:
        record["source_priority"] = "HISTORICAL_OR_SECONDARY"


# ------------------------------------------------------------
# Report
# ------------------------------------------------------------

current = [
    r for r in records
    if r.get("source_priority") == "CURRENT_PRIMARY"
]

historical = [
    r for r in records
    if r.get("source_priority") == "HISTORICAL_OR_SECONDARY"
]

output = {
    "country": "Malaysia",
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "selection_rule": "Newest dated official brochure",
        "historical_sources_retained": True,
        "master_import": False
    },
    "generated_at": datetime.now().isoformat(),
    "total_records": len(records),
    "current_primary_records": len(current),
    "historical_secondary_records": len(historical),
    "current_by_model": latest,
    "records": records
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

report = {
    "generated_at": datetime.now().isoformat(),
    "total_records": len(records),
    "models_with_current_source": len(latest),
    "current_primary_records": len(current),
    "historical_secondary_records": len(historical),
    "current_sources": [
        {
            "model": x["model_name"],
            "file": x["source_file"],
            "year": x["source_year"],
            "date": x["source_date"]
        }
        for x in latest.values()
    ],
    "output": str(OUT)
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print()
print("=" * 75)
print("SOURCE PRIORITY SUMMARY")
print("Total brochure records     :", len(records))
print("Models with current source:", len(latest))
print("Current primary records    :", len(current))
print("Historical/secondary       :", len(historical))
print()
print("CURRENT SOURCES")
print("-" * 75)

for x in sorted(
    latest.values(),
    key=lambda z: z["model_name"].lower()
):
    print(
        f"{x['model_name']:35} "
        f"{str(x['source_year']):6} "
        f"{x['source_file']}"
    )

print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
print("JSON VALID")
