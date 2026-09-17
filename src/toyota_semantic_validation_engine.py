#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_merged_candidates.json"
REGISTRY = BASE / "data/toyota_shared_source_registry.json"

OUT = BASE / "data/toyota_semantically_validated.json"
REPORT = BASE / "reports/toyota_semantic_validation_report.json"

with open(INPUT, encoding="utf-8") as f:
    merged = json.load(f)

with open(REGISTRY, encoding="utf-8") as f:
    registry = json.load(f)

records = merged.get("records", [])

registry_map = {
    r.get("model_name"): r
    for r in registry.get("records", [])
}


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except:
        return None


def tech(r):
    return r.get("technical_specifications", {}) or {}


def values(t, names):
    out = []
    for name in names:
        out.extend(as_list(t.get(name)))
    return out


def valid_power(vals):
    good = []
    bad = []

    for v in vals:
        n = num(v)

        if n is None:
            bad.append([v, "NON_NUMERIC"])
        elif 40 <= n <= 400:
            good.append(n)
        else:
            bad.append([v, "OUT_OF_RANGE"])

    return sorted(set(good)), bad


def valid_torque(vals):
    good = []
    bad = []

    for v in vals:
        n = num(v)

        if n is None:
            bad.append([v, "NON_NUMERIC"])
        elif 60 <= n <= 700:
            good.append(n)
        else:
            bad.append([v, "OUT_OF_RANGE"])

    return sorted(set(good)), bad


def valid_cc(vals):
    good = []
    bad = []

    for v in vals:

        s = str(v).strip()

        # Never accept arbitrary decimal values as CC
        # unless explicitly within realistic litre range.
        if "." in s:
            n = num(s)

            if n is not None and 0.8 <= n <= 6.0:
                good.append(int(round(n * 1000)))
            else:
                bad.append([v, "INVALID_LITRE_DISPLACEMENT"])

            continue

        n = num(s)

        if n is None:
            bad.append([v, "NON_NUMERIC"])
        elif 800 <= n <= 7000:
            good.append(int(n))
        else:
            bad.append([v, "INVALID_CC"])

    return sorted(set(good)), bad


def valid_trans(vals):
    good = []
    bad = []

    keywords = (
        "cvt",
        "e-cvt",
        "automatic",
        "manual",
        "shiftmatic",
        "sequential",
        "dct",
        "transmission"
    )

    for v in vals:
        s = " ".join(str(v).split())

        if any(k in s.lower() for k in keywords):
            good.append(s)
        else:
            bad.append([v, "NO_TRANSMISSION_CONTEXT"])

    return list(dict.fromkeys(good)), bad


def context_for(r):
    ev = r.get("evidence", {}) or {}

    ctx = ev.get("context", {}) or {}
    structured = ev.get("structured", {}) or {}

    chunks = []

    for section in [ctx, structured]:

        if isinstance(section, dict):

            for value in section.values():

                for item in as_list(value):

                    if isinstance(item, dict):
                        chunks.append(
                            json.dumps(
                                item,
                                ensure_ascii=False
                            )
                        )
                    else:
                        chunks.append(str(item))

    return "\n".join(chunks)


validated = []

summary = {
    "records": len(records),
    "power_valid": 0,
    "torque_valid": 0,
    "cc_valid": 0,
    "transmission_valid": 0,
    "shared_source": 0,
    "review_required": 0
}


for r in records:

    model = r.get("model_name_candidate")
    t = tech(r)

    power_raw = values(
        t,
        [
            "power_ps_candidates",
            "horsepower_ps_candidates",
            "power_candidates"
        ]
    )

    torque_raw = values(
        t,
        [
            "torque_nm_candidates",
            "torque_candidates"
        ]
    )

    cc_raw = values(
        t,
        [
            "displacement_cc_candidates",
            "displacement_candidates"
        ]
    )

    trans_raw = values(
        t,
        [
            "transmission_candidates",
            "transmission"
        ]
    )

    power, power_bad = valid_power(power_raw)
    torque, torque_bad = valid_torque(torque_raw)
    cc, cc_bad = valid_cc(cc_raw)
    trans, trans_bad = valid_trans(trans_raw)

    registry_row = registry_map.get(model, {})

    coverage = registry_row.get(
        "coverage_type"
    )

    if coverage == "SHARED_SOURCE":
        summary["shared_source"] += 1

    field_count = sum([
        bool(power),
        bool(torque),
        bool(cc),
        bool(trans)
    ])

    if field_count == 0:
        status = "REVIEW_REQUIRED"
        summary["review_required"] += 1
    else:
        status = "SEMANTIC_CANDIDATES"

    summary["power_valid"] += len(power)
    summary["torque_valid"] += len(torque)
    summary["cc_valid"] += len(cc)
    summary["transmission_valid"] += len(trans)

    validated.append({
        "model_name": model,
        "source_file": r.get("source_file"),
        "source_priority": r.get("source_priority"),
        "coverage_type": coverage,

        "validation_status": status,

        "technical_candidates": {
            "power_ps": power,
            "torque_nm": torque,
            "displacement_cc": cc,
            "transmission": trans
        },

        "rejected": {
            "power": power_bad,
            "torque": torque_bad,
            "displacement": cc_bad,
            "transmission": trans_bad
        },

        "source_context": context_for(r)[:8000],

        "policy": {
            "candidate_only": True,
            "not_master_ready": True,
            "variant_context_required": True,
            "shared_source_requires_separate_variant_validation": True
        }
    })


output = {
    "generated_at": datetime.now().isoformat(),
    "record_count": len(validated),
    "records": validated
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


report = {
    "generated_at": datetime.now().isoformat(),
    **summary,
    "master_modified": False
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print("TOYOTA SEMANTIC VALIDATION ENGINE")
print("=" * 90)

print("Records              :", summary["records"])
print("Valid power          :", summary["power_valid"])
print("Valid torque         :", summary["torque_valid"])
print("Valid displacement   :", summary["cc_valid"])
print("Valid transmission   :", summary["transmission_valid"])
print("Shared-source        :", summary["shared_source"])
print("Review required      :", summary["review_required"])

print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
