#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_merged_candidates.json"
PRIORITY = BASE / "data/toyota_source_prioritized.json"

OUT = BASE / "data/toyota_primary_candidates.json"
REPORT = BASE / "reports/toyota_primary_candidate_report.json"


def unique(values):
    result = []
    seen = set()

    for v in values:
        key = str(v).strip().lower()

        if key and key not in seen:
            seen.add(key)
            result.append(v)

    return result


with open(INPUT, encoding="utf-8") as f:
    merged = json.load(f).get("records", [])

with open(PRIORITY, encoding="utf-8") as f:
    priority = json.load(f).get("records", [])


# filename -> authoritative priority
priority_map = {
    r.get("source_file"): r.get("source_priority")
    for r in priority
}


# Group merged candidates by model.
groups = {}

for record in merged:
    model = record.get("model_name_candidate")

    groups.setdefault(model, []).append(record)


primary_records = []
report_groups = {}

for model, records in groups.items():

    enriched = []

    for record in records:

        filename = record.get("source_file")

        source_priority = priority_map.get(
            filename,
            record.get("source_priority")
        )

        record = dict(record)
        record["source_priority"] = source_priority

        # Base quality score.
        score = 0

        if source_priority == "CURRENT_PRIMARY":
            score += 50
        elif source_priority == "HISTORICAL_OR_SECONDARY":
            score += 10

        specs = record.get(
            "technical_specifications", {}
        )

        if specs.get("power_ps_candidates"):
            score += 10

        if specs.get("torque_nm_candidates"):
            score += 10

        if specs.get("displacement_cc_candidates"):
            score += 10

        if specs.get("transmission_candidates"):
            score += 5

        if record.get("variants_candidates"):
            score += 5

        if record.get("evidence"):
            score += 5

        record["candidate_score"] = score

        enriched.append(record)

    # Current primary always wins over historical.
    current = [
        r for r in enriched
        if r.get("source_priority") == "CURRENT_PRIMARY"
    ]

    if current:
        selected = max(
            current,
            key=lambda x: x.get("candidate_score", 0)
        )
    else:
        selected = max(
            enriched,
            key=lambda x: x.get("candidate_score", 0)
        )

    selected = dict(selected)

    selected["selection_status"] = (
        "CURRENT_PRIMARY_SELECTED"
        if current
        else "BEST_AVAILABLE_SELECTED"
    )

    selected["historical_sources"] = [
        {
            "source_file": r.get("source_file"),
            "candidate_score": r.get("candidate_score"),
            "source_priority": r.get("source_priority")
        }
        for r in enriched
        if r.get("source_file") != selected.get("source_file")
    ]

    primary_records.append(selected)

    report_groups[model] = {
        "total_candidates": len(enriched),
        "current_primary_candidates": len(current),
        "selected_source": selected.get("source_file"),
        "selected_priority": selected.get("source_priority"),
        "selected_score": selected.get("candidate_score"),
        "historical_sources": [
            r.get("source_file")
            for r in enriched
            if r.get("source_file") != selected.get("source_file")
        ]
    }


output = {
    "generated_at": datetime.now().isoformat(),
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "current_primary_preferred": True,
        "historical_sources_retained": True,
        "candidate_only": True,
        "master_import": False,
        "no_hallucination": True
    },
    "total_models": len(primary_records),
    "records": primary_records
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


report = {
    "generated_at": datetime.now().isoformat(),
    "input_records": len(merged),
    "selected_models": len(primary_records),
    "models_with_current_primary": sum(
        1
        for x in primary_records
        if x.get("selection_status") == "CURRENT_PRIMARY_SELECTED"
    ),
    "models_best_available_only": sum(
        1
        for x in primary_records
        if x.get("selection_status") == "BEST_AVAILABLE_SELECTED"
    ),
    "groups": report_groups,
    "master_modified": False,
    "output": str(OUT)
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print("TOYOTA PRIMARY CANDIDATE ENGINE")
print("=" * 75)

for model, info in report_groups.items():
    print(
        f"{model:35} "
        f"candidates={info['total_candidates']} "
        f"current={info['current_primary_candidates']} "
        f"selected={info['selected_source']} "
        f"score={info['selected_score']}"
    )

print()
print("=" * 75)
print("PRIMARY CANDIDATE SUMMARY")
print("Input records             :", report["input_records"])
print("Selected models           :", report["selected_models"])
print("Current primary selected  :", report["models_with_current_primary"])
print("Best available only       :", report["models_best_available_only"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
print("JSON VALID")
