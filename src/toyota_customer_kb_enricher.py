#!/usr/bin/env python3

import json
import os
from datetime import datetime

BASE = "/opt/toyota-malaysia-ai"

KB = f"{BASE}/data/toyota_customer_kb.json"
CAND = f"{BASE}/data/toyota_canonical_variant_candidates_v3.json"

BACKUP_DIR = f"{BASE}/backups"
REPORT_DIR = f"{BASE}/reports"

os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

with open(KB, encoding="utf-8") as f:
    kb = json.load(f)

with open(CAND, encoding="utf-8") as f:
    candidates = json.load(f)["records"]

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

backup = f"{BACKUP_DIR}/toyota_customer_kb.before-enrichment-{timestamp}.json"

with open(backup, "w", encoding="utf-8") as f:
    json.dump(kb, f, indent=2, ensure_ascii=False)

FIELD_MAP = {
    "engine_displacement_cc": "engine_displacement_cc",
    "engine_power_ps": "engine_power_ps",
    "engine_torque_nm": "engine_torque_nm",
    "hev_engine_power_ps": "hev_engine_power_ps",
    "hev_engine_torque_nm": "hev_engine_torque_nm",
    "motor_power_ps": "motor_power_ps",
    "motor_output_kw": "motor_output_kw",
    "motor_torque_nm": "motor_torque_nm",
    "combined_power_ps": "combined_power_ps",
    "transmission": "transmission",
}

updated = []
skipped = []
unmatched = []

for c in candidates:

    variant_name = c.get("variant")
    field = c.get("field")
    value = c.get("value")
    source_file = c.get("source_file")

    if not variant_name or not field or value is None:
        skipped.append(c)
        continue

    target = None

    # Exact variant match
    for model in kb.get("models", []):
        for variant in model.get("variants", []):

            name = (
                variant.get("variant_name")
                or variant.get("name")
                or variant.get("variant")
            )

            if name:
                kb_name = name.strip().lower()
                candidate_name = variant_name.strip().lower()

                # Toyota variant naming normalization:
                # "Vios 1.5E" == "Vios 1.5E AT"
                kb_norm = kb_name.replace(" at", "").strip()
                candidate_norm = candidate_name.replace(" at", "").strip()

                if kb_norm == candidate_norm:
                    target = variant
                    break

        if target:
            break

    if not target:
        unmatched.append(c)
        continue

    target_field = FIELD_MAP.get(field)

    if not target_field:
        skipped.append(c)
        continue

    old = target.get(target_field)

    # Never overwrite an existing non-null value automatically.
    if old is not None:
        skipped.append({
            **c,
            "reason": "existing_value_preserved",
            "existing_value": old
        })
        continue

    target[target_field] = value

    # Preserve evidence information
    evidence = target.setdefault("technical_evidence", [])

    evidence.append({
        "field": target_field,
        "value": value,
        "source_file": source_file,
        "status": "VERIFIED_SOURCE_CANDIDATE"
    })

    updated.append({
        "variant": variant_name,
        "field": target_field,
        "value": value,
        "source_file": source_file
    })


# Customer policy remains English-only
kb["source_policy"]["customer_review"] = False
kb["source_policy"]["never_expose_review_status"] = True
kb["source_policy"]["no_guessing"] = True

kb["customer_response_policy"] = {
    "review_required": False,
    "answer_verified_only": True,
    "never_guess": True,
    "never_expose_internal_status": True,
    "language": "English",
    "unknown_response": (
        "I'm sorry, but this information is not currently available "
        "in the verified Toyota Malaysia knowledge base."
    )
}

with open(KB, "w", encoding="utf-8") as f:
    json.dump(kb, f, indent=2, ensure_ascii=False)

report = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "candidate_records": len(candidates),
    "fields_added": len(updated),
    "existing_values_preserved": len([
        x for x in skipped
        if x.get("reason") == "existing_value_preserved"
    ]),
    "unmatched_candidates": len(unmatched),
    "skipped": len(skipped),
    "customer_review_required": False,
    "language": "English",
    "master_modified": False,
    "backup": backup,
    "output": KB
}

report_path = f"{REPORT_DIR}/toyota_customer_kb_enrichment-{timestamp}.json"

with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print("=" * 80)
print("TOYOTA CUSTOMER KB ENRICHMENT")
print("=" * 80)
print("Candidate records       :", len(candidates))
print("Technical fields added  :", len(updated))
print("Existing values kept    :", report["existing_values_preserved"])
print("Unmatched candidates    :", len(unmatched))
print("Customer review         : DISABLED")
print("Language                : ENGLISH")
print("Master modified         : NO")
print()
print("Backup :", backup)
print("KB     :", KB)
print("Report :", report_path)
