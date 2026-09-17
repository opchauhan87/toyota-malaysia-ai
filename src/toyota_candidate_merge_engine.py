#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

STRUCTURED = BASE / "data/toyota_structured_candidates.json"
CONTEXT = BASE / "data/toyota_context_candidates.json"
TABLE = BASE / "data/toyota_spec_table_candidates.json"

OUT = BASE / "data/toyota_merged_candidates.json"
REPORT = BASE / "reports/toyota_candidate_merge_report.json"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def unique(values):
    out = []
    seen = set()

    for v in values:
        key = str(v).strip().lower()

        if key and key not in seen:
            seen.add(key)
            out.append(v)

    return out


print("TOYOTA CANDIDATE MERGE ENGINE")
print("=" * 75)

structured = load(STRUCTURED).get("records", [])
context = load(CONTEXT).get("records", [])
table = load(TABLE).get("records", [])

context_map = {
    x.get("source_file"): x
    for x in context
}

table_map = {
    x.get("source_file"): x
    for x in table
}

merged = []

for base in structured:

    filename = base.get("source_file")
    ctx = context_map.get(filename, {})
    tbl = table_map.get(filename, {})

    bt = base.get("technical_specifications", {})
    ct = ctx.get("technical_specifications", {})
    tt = tbl.get("technical_specifications", {})

    power = unique(
        bt.get("power_candidates", [])
        + ct.get("power_ps_candidates", [])
        + tt.get("power_ps_candidates", [])
    )

    torque = unique(
        bt.get("torque_candidates", [])
        + ct.get("torque_nm_candidates", [])
        + tt.get("torque_nm_candidates", [])
    )

    displacement = unique(
        bt.get("displacement_candidates", [])
        + ct.get("displacement_cc_candidates", [])
        + tt.get("displacement_cc_candidates", [])
    )

    transmission = unique(
        bt.get("transmission_candidates", [])
        + ct.get("transmission_candidates", [])
        + tt.get("transmission_candidates", [])
    )

    dimensions = (
        tbl.get("dimensions", {})
        .get("vehicle_dimensions_candidates", [])
        or
        ctx.get("dimensions", {})
        .get("vehicle_dimensions_candidates", [])
    )

    evidence = {
        "structured": base.get("evidence", {}),
        "context": ctx.get("evidence", {}),
        "spec_table": tbl.get("evidence", {})
    }

    record = {
        "model_name_candidate":
            base.get("model_name_candidate"),

        "source_file": filename,

        "source_priority":
            base.get("source_priority")
            or ctx.get("source_priority")
            or tbl.get("source_priority"),

        "source_metadata":
            base.get("source_metadata")
            or ctx.get("source_metadata")
            or tbl.get("source_metadata"),

        "candidate_status": "MERGED_CANDIDATE",

        "technical_specifications": {
            "power_ps_candidates": power,
            "torque_nm_candidates": torque,
            "displacement_cc_candidates": displacement,
            "transmission_candidates": transmission,
            "drivetrain_candidates":
                ct.get("drivetrain_candidates", []),
            "fuel_consumption_candidates":
                ct.get("fuel_consumption_candidates", [])
        },

        "dimensions": {
            "vehicle_dimensions_candidates": dimensions,
            "wheelbase_candidates_mm":
                ctx.get("dimensions", {})
                .get("wheelbase_candidates_mm", [])
        },

        "safety":
            base.get("safety", {}),

        "variants_candidates":
            unique(
                base.get("variants_candidates", [])
                + ctx.get("variants_candidates", [])
            ),

        "evidence": evidence
    }

    merged.append(record)

    print(
        f"{str(record['model_name_candidate']):32} "
        f"PS={len(power):2d} "
        f"Nm={len(torque):2d} "
        f"CC={len(displacement):2d} "
        f"Trans={len(transmission):2d}"
    )


output = {
    "generated_at": datetime.now().isoformat(),
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "candidate_only": True,
        "no_hallucination": True,
        "master_import": False
    },
    "total_records": len(merged),
    "records": merged
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


model_groups = {}

for r in merged:
    model = r.get("model_name_candidate")
    model_groups.setdefault(model, []).append(r)


report = {
    "generated_at": datetime.now().isoformat(),
    "input_structured_records": len(structured),
    "input_context_records": len(context),
    "input_table_records": len(table),
    "merged_records": len(merged),
    "distinct_model_candidates": len(model_groups),
    "duplicate_model_groups": {
        k: len(v)
        for k, v in model_groups.items()
        if len(v) > 1
    },
    "master_modified": False,
    "output": str(OUT)
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print()
print("=" * 75)
print("MERGE SUMMARY")
print("Structured records     :", len(structured))
print("Context records        :", len(context))
print("Table records          :", len(table))
print("Merged records         :", len(merged))
print("Distinct models        :", len(model_groups))
print("Duplicate model groups :", len(report["duplicate_model_groups"]))
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
print("JSON VALID")
