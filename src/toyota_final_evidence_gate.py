#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

CANDIDATES = BASE / "data/toyota_canonical_variant_candidates_v3.json"
MASTER = BASE / "data/toyota_models.json"

OUT = BASE / "data/toyota_final_evidence_gate.json"
REPORT = BASE / "reports/toyota_final_evidence_gate.json"

with open(CANDIDATES, encoding="utf-8") as f:
    candidates = json.load(f)

with open(MASTER, encoding="utf-8") as f:
    master = json.load(f)["models"]

master_map = {
    m.get("model_name"): m
    for m in master
}


def flatten_values(obj):
    if isinstance(obj, dict):
        out = []
        for v in obj.values():
            out.extend(flatten_values(v))
        return out

    if isinstance(obj, list):
        out = []
        for v in obj:
            out.extend(flatten_values(v))
        return out

    return [obj]


def find_existing(model, variant, field):
    """
    Search master recursively for an exact/related field.
    This is audit-only; no modification.
    """
    text = json.dumps(
        model,
        ensure_ascii=False
    ).lower()

    variant_found = variant.lower() in text

    aliases = {
        "engine_power_ps": [
            "engine_power_ps",
            "power_ps",
            "power"
        ],
        "engine_torque_nm": [
            "engine_torque_nm",
            "torque_nm",
            "torque"
        ],
        "engine_displacement_cc": [
            "engine_displacement_cc",
            "displacement_cc",
            "displacement"
        ],
        "transmission": [
            "transmission"
        ],
        "motor_power_ps": [
            "motor_power_ps",
            "motor_power"
        ],
        "motor_torque_nm": [
            "motor_torque_nm",
            "motor_torque"
        ],
        "combined_power_ps": [
            "combined_power_ps",
            "combined_power"
        ]
    }

    field_aliases = aliases.get(field, [field])

    field_found = any(
        x in text
        for x in field_aliases
    )

    return variant_found, field_found


results = []

for r in candidates["records"]:

    variant = r.get("variant")
    field = r.get("field")
    value = r.get("value")

    matched_model = None

    for model_name, model in master_map.items():

        if variant.startswith(model_name):
            matched_model = model
            break

    if matched_model:
        variant_found, field_found = find_existing(
            matched_model,
            variant,
            field
        )
    else:
        variant_found = False
        field_found = False

    if r.get("status") == "REVIEW_REQUIRED":
        gate = "REVIEW_REQUIRED"

    elif not variant_found:
        gate = "REVIEW_REQUIRED"

    elif not field_found:
        gate = "NEW_FIELD_CANDIDATE"

    else:
        gate = "EXISTING_FIELD_REQUIRES_COMPARISON"

    results.append({
        "variant": variant,
        "field": field,
        "candidate_value": value,
        "candidate_status": r.get("status"),
        "source": r.get("source_file"),
        "master_model_found": bool(matched_model),
        "variant_context_found": variant_found,
        "similar_field_found": field_found,
        "gate_status": gate
    })


summary = {
    "total": len(results),
    "review_required": sum(
        1 for r in results
        if r["gate_status"] == "REVIEW_REQUIRED"
    ),
    "new_field_candidate": sum(
        1 for r in results
        if r["gate_status"] == "NEW_FIELD_CANDIDATE"
    ),
    "existing_field_comparison": sum(
        1 for r in results
        if r["gate_status"] == "EXISTING_FIELD_REQUIRES_COMPARISON"
    ),
    "master_modified": False
}


output = {
    "generated_at": datetime.now().isoformat(),
    "gate_version": "v1",
    "summary": summary,
    "records": results
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump({
        "generated_at": datetime.now().isoformat(),
        "gate_version": "v1",
        **summary
    }, f, indent=2, ensure_ascii=False)


print("TOYOTA FINAL EVIDENCE GATE")
print("=" * 100)
print("Total                     :", summary["total"])
print("Review required           :", summary["review_required"])
print("New field candidates      :", summary["new_field_candidate"])
print("Existing field comparison :", summary["existing_field_comparison"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
