#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_merged_candidates.json"
REGISTRY = BASE / "data/toyota_shared_source_registry.json"

OUT = BASE / "data/toyota_validated_candidates.json"
REPORT = BASE / "reports/toyota_candidate_validation_report.json"


with open(INPUT, encoding="utf-8") as f:
    merged = json.load(f)

with open(REGISTRY, encoding="utf-8") as f:
    registry = json.load(f)


records = merged.get("records", [])

registry_map = {
    r.get("model_name"): r
    for r in registry.get("records", [])
}


def as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def to_number(value):
    try:
        return float(
            str(value)
            .replace(",", "")
            .strip()
        )
    except Exception:
        return None


def get_technical(r):
    return (
        r.get("technical_specifications")
        or r.get("technical")
        or {}
    )


def candidate_values(tech, names):
    result = []

    for name in names:
        if name in tech:
            result.extend(as_list(tech.get(name)))

    return result


def validate_power(values):
    valid = []
    rejected = []

    for raw in values:
        n = to_number(raw)

        if n is None:
            rejected.append({
                "value": raw,
                "reason": "NOT_NUMERIC"
            })
            continue

        # Passenger/commercial Toyota Malaysia engine outputs.
        if 40 <= n <= 400:
            valid.append(n)
        else:
            rejected.append({
                "value": raw,
                "reason": "POWER_OUT_OF_RANGE"
            })

    return sorted(set(valid)), rejected


def validate_torque(values):
    valid = []
    rejected = []

    for raw in values:
        n = to_number(raw)

        if n is None:
            rejected.append({
                "value": raw,
                "reason": "NOT_NUMERIC"
            })
            continue

        if 60 <= n <= 700:
            valid.append(n)
        else:
            rejected.append({
                "value": raw,
                "reason": "TORQUE_OUT_OF_RANGE"
            })

    return sorted(set(valid)), rejected


def validate_cc(values):
    valid = []
    rejected = []

    for raw in values:
        s = str(raw).strip()

        # Litre displacement.
        if "." in s:
            n = to_number(s)

            if n is not None and 0.6 <= n <= 6.0:
                valid.append(int(round(n * 1000)))
            else:
                rejected.append({
                    "value": raw,
                    "reason": "LITRE_DISPLACEMENT_OUT_OF_RANGE"
                })

            continue

        n = to_number(s)

        if n is None:
            rejected.append({
                "value": raw,
                "reason": "NOT_NUMERIC"
            })
            continue

        # CC values must be realistic engine displacement.
        if 600 <= n <= 7000:
            valid.append(int(n))
        else:
            rejected.append({
                "value": raw,
                "reason": "CC_OUT_OF_RANGE"
            })

    return sorted(set(valid)), rejected


def validate_transmission(values):
    valid = []
    rejected = []

    keywords = [
        "cvt",
        "e-cvt",
        "automatic",
        "manual",
        "shiftmatic",
        "sequential",
        "direct shift"
    ]

    for raw in values:
        text = str(raw).strip()

        if any(k in text.lower() for k in keywords):
            valid.append(text)
        else:
            rejected.append({
                "value": raw,
                "reason": "NO_TRANSMISSION_KEYWORD"
            })

    return valid, rejected


validated = []

summary = {
    "records": len(records),
    "power_candidates": 0,
    "valid_power": 0,
    "rejected_power": 0,
    "torque_candidates": 0,
    "valid_torque": 0,
    "rejected_torque": 0,
    "cc_candidates": 0,
    "valid_cc": 0,
    "rejected_cc": 0,
    "transmission_candidates": 0,
    "valid_transmission": 0,
    "rejected_transmission": 0,
    "shared_source_review": 0,
    "review_required": 0
}


for r in records:

    model = r.get("model_name_candidate")

    tech = get_technical(r)

    power_raw = candidate_values(
        tech,
        [
            "power_ps_candidates",
            "horsepower_ps_candidates",
            "power_candidates"
        ]
    )

    torque_raw = candidate_values(
        tech,
        [
            "torque_nm_candidates",
            "torque_candidates"
        ]
    )

    cc_raw = candidate_values(
        tech,
        [
            "displacement_cc_candidates",
            "displacement_candidates"
        ]
    )

    trans_raw = candidate_values(
        tech,
        [
            "transmission_candidates",
            "transmission"
        ]
    )

    power, power_rejected = validate_power(power_raw)
    torque, torque_rejected = validate_torque(torque_raw)
    cc, cc_rejected = validate_cc(cc_raw)
    trans, trans_rejected = validate_transmission(trans_raw)

    reg = registry_map.get(model, {})

    shared = (
        reg.get("coverage_type") == "SHARED_SOURCE"
    )

    if shared:
        summary["shared_source_review"] += 1

    field_count = sum([
        bool(power),
        bool(torque),
        bool(cc),
        bool(trans)
    ])

    if field_count == 0:
        status = "REVIEW_REQUIRED"
        summary["review_required"] += 1
    elif shared:
        status = "SHARED_SOURCE_CONTEXT_REQUIRED"
    else:
        status = "CANDIDATES_VALIDATED"

    summary["power_candidates"] += len(power_raw)
    summary["valid_power"] += len(power)
    summary["rejected_power"] += len(power_rejected)

    summary["torque_candidates"] += len(torque_raw)
    summary["valid_torque"] += len(torque)
    summary["rejected_torque"] += len(torque_rejected)

    summary["cc_candidates"] += len(cc_raw)
    summary["valid_cc"] += len(cc)
    summary["rejected_cc"] += len(cc_rejected)

    summary["transmission_candidates"] += len(trans_raw)
    summary["valid_transmission"] += len(trans)
    summary["rejected_transmission"] += len(trans_rejected)

    validated.append({
        "model_name": model,
        "source_file": r.get("source_file"),
        "source_priority": r.get("source_priority"),
        "coverage_type": reg.get("coverage_type"),

        "validation_status": status,

        "technical": {
            "power_ps_valid": power,
            "torque_nm_valid": torque,
            "displacement_cc_valid": cc,
            "transmission_valid": trans
        },

        "rejected_candidates": {
            "power": power_rejected,
            "torque": torque_rejected,
            "displacement": cc_rejected,
            "transmission": trans_rejected
        },

        "policy": {
            "candidate_only": True,
            "context_required_for_shared_source": shared,
            "master_import_allowed": False
        }
    })


output = {
    "generated_at": datetime.now().isoformat(),
    "records": validated
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


report = {
    "generated_at": datetime.now().isoformat(),
    **summary,
    "master_modified": False,
    "output": str(OUT)
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print("TOYOTA CANDIDATE VALIDATION ENGINE")
print("=" * 90)

print("Records                 :", summary["records"])

print()
print("POWER")
print("  candidates            :", summary["power_candidates"])
print("  valid                 :", summary["valid_power"])
print("  rejected              :", summary["rejected_power"])

print()
print("TORQUE")
print("  candidates            :", summary["torque_candidates"])
print("  valid                 :", summary["valid_torque"])
print("  rejected              :", summary["rejected_torque"])

print()
print("DISPLACEMENT")
print("  candidates            :", summary["cc_candidates"])
print("  valid                 :", summary["valid_cc"])
print("  rejected              :", summary["rejected_cc"])

print()
print("TRANSMISSION")
print("  candidates            :", summary["transmission_candidates"])
print("  valid                 :", summary["valid_transmission"])
print("  rejected              :", summary["rejected_transmission"])

print()
print("Shared-source review    :", summary["shared_source_review"])
print("Review required         :", summary["review_required"])

print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
