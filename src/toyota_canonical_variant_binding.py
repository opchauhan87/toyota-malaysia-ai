#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_variant_resolved.json"
MASTER = BASE / "data/toyota_models.json"

OUT = BASE / "data/toyota_canonical_variant_candidates.json"
REPORT = BASE / "reports/toyota_canonical_variant_binding_report.json"


with open(INPUT, encoding="utf-8") as f:
    resolved = json.load(f)["records"]

with open(MASTER, encoding="utf-8") as f:
    master = json.load(f)["models"]


master_map = {
    m.get("model_name"): m
    for m in master
}


def candidate(
    variant,
    field,
    value,
    source,
    status="CANDIDATE"
):
    return {
        "variant": variant,
        "field": field,
        "value": value,
        "status": status,
        "source_file": source,
        "master_ready": status == "VERIFIED"
    }


results = []


# ------------------------------------------------------------
# CURRENT PRIMARY SOURCE ONLY
# ------------------------------------------------------------

current = [
    r for r in resolved
    if r.get("source_priority") == "CURRENT_PRIMARY"
]


# ------------------------------------------------------------
# VIOS
# ------------------------------------------------------------

for r in current:

    if r["family"] != "Vios":
        continue

    source = r["source_file"]
    fields = r["resolved_fields"]

    if source == "toyota-vios-e-brochure.txt":

        results.extend([
            candidate(
                "Vios 1.5E",
                "engine_displacement_cc",
                1496,
                source
            ),
            candidate(
                "Vios 1.5E",
                "engine_power_ps",
                106,
                source
            ),
            candidate(
                "Vios 1.5E",
                "engine_torque_nm",
                138,
                source
            ),
            candidate(
                "Vios 1.5G",
                "engine_displacement_cc",
                1496,
                source
            ),
            candidate(
                "Vios 1.5G",
                "engine_power_ps",
                106,
                source
            ),
            candidate(
                "Vios 1.5G",
                "engine_torque_nm",
                138,
                source
            ),
        ])

    elif source in [
        "toyota-vios-hev-e-brochure.txt",
        "toyota-vios-hev-gr-sport-e-brochure.txt"
    ]:

        variant = (
            "Vios 1.5 HEV GR Sport"
            if "gr-sport" in source
            else "Vios 1.5 HEV"
        )

        results.extend([
            candidate(
                variant,
                "hev_engine_power_ps",
                fields["hev_engine_power_ps"]["value"],
                source
            ),
            candidate(
                variant,
                "hev_engine_torque_nm",
                fields["hev_engine_torque_nm"]["value"],
                source
            ),
            candidate(
                variant,
                "combined_power_ps",
                fields["combined_power_ps"]["value"],
                source
            ),
        ])


# ------------------------------------------------------------
# YARIS CROSS
# ------------------------------------------------------------

for r in current:

    if r["family"] != "Yaris Cross":
        continue

    fields = r["resolved_fields"]
    source = r["source_file"]

    # Source is HEV brochure and context contains both
    # petrol and HEV powertrain sections.
    if all(
        k in fields
        for k in [
            "engine_power_ps",
            "engine_torque_nm",
            "motor_power_ps",
            "combined_power_ps"
        ]
    ):

        results.extend([
            candidate(
                "Yaris Cross 1.5S HEV",
                "engine_power_ps",
                fields["engine_power_ps"]["value"],
                source
            ),
            candidate(
                "Yaris Cross 1.5S HEV",
                "engine_torque_nm",
                fields["engine_torque_nm"]["value"],
                source
            ),
            candidate(
                "Yaris Cross 1.5S HEV",
                "motor_power_ps",
                fields["motor_power_ps"]["value"],
                source
            ),
            candidate(
                "Yaris Cross 1.5S HEV",
                "combined_power_ps",
                fields["combined_power_ps"]["value"],
                source
            ),
        ])


# ------------------------------------------------------------
# CAMRY
# ------------------------------------------------------------

for r in current:

    if r["family"] != "Camry":
        continue

    source = r["source_file"]
    fields = r["resolved_fields"]

    # Current primary HEV brochure contains both HEV and
    # petrol variant specifications.
    if source != "Camry-HEV-Brochure.txt":
        continue

    results.extend([
        candidate(
            "Camry 2.5 HEV",
            "engine_displacement_cc",
            fields["engine_displacement_cc"]["value"],
            source
        ),
        candidate(
            "Camry 2.5 HEV",
            "engine_power_ps",
            fields["hev_engine_power_ps"]["value"],
            source
        ),
        candidate(
            "Camry 2.5 HEV",
            "engine_torque_nm",
            fields["hev_engine_torque_nm"]["value"],
            source
        ),
        candidate(
            "Camry 2.5 HEV",
            "motor_power_ps",
            fields["motor_power_ps"]["value"],
            source
        ),
        candidate(
            "Camry 2.5 HEV",
            "motor_torque_nm",
            fields["motor_torque_nm"]["value"],
            source
        ),
        candidate(
            "Camry 2.5 HEV",
            "combined_power_ps",
            fields["combined_power_ps"]["value"],
            source
        ),
        candidate(
            "Camry 2.5V",
            "engine_displacement_cc",
            fields["engine_displacement_cc"]["value"],
            source
        ),
        candidate(
            "Camry 2.5V",
            "engine_power_ps",
            fields["petrol_engine_power_ps"]["value"],
            source
        ),
        candidate(
            "Camry 2.5V",
            "engine_torque_nm",
            fields["petrol_engine_torque_nm"]["value"],
            source
        ),
    ])


# ------------------------------------------------------------
# COROLLA CROSS
# ------------------------------------------------------------

for r in current:

    if r["family"] != "Corolla Cross":
        continue

    source = r["source_file"]
    fields = r["resolved_fields"]

    if source == "corolla-cross-hev-e-brochure.txt":

        results.extend([
            candidate(
                "Corolla Cross 1.8V",
                "engine_power_ps",
                fields["petrol_engine_power_ps"]["value"],
                source
            ),
            candidate(
                "Corolla Cross 1.8V",
                "engine_torque_nm",
                fields["petrol_engine_torque_nm"]["value"],
                source
            ),
            candidate(
                "Corolla Cross HEV",
                "engine_power_ps",
                fields["hev_engine_power_ps"]["value"],
                source
            ),
            candidate(
                "Corolla Cross HEV",
                "engine_torque_nm",
                fields["hev_engine_torque_nm"]["value"],
                source
            ),
        ])

    elif source == "corolla-cross-hev-gr-sport-e-brochure.txt":

        results.append({
            "variant": "Corolla Cross HEV GR Sport",
            "field": "powertrain_specifications",
            "value": None,
            "status": "REVIEW_REQUIRED",
            "source_file": source,
            "master_ready": False,
            "reason": "OCR labels/numbers insufficient for safe automatic binding"
        })


# ------------------------------------------------------------
# HILUX
# ------------------------------------------------------------

for r in current:

    if r["family"] != "Hilux":
        continue

    source = r["source_file"]
    fields = r["resolved_fields"]

    if source == "hilux-gr-s-rogue-e-brochure.txt":

        # 2.8 GR Sport / Rogue
        results.extend([
            candidate(
                "Hilux 2.8 GR Sport",
                "engine_displacement_cc",
                2755,
                source
            ),
            candidate(
                "Hilux 2.8 GR Sport",
                "engine_power_ps",
                224,
                source
            ),
            candidate(
                "Hilux 2.8 GR Sport",
                "engine_torque_nm",
                550,
                source
            ),
        ])

        # 2.4 values contain multiple variants and therefore
        # remain REVIEW_REQUIRED until table-column binding.
        results.append({
            "variant": "Hilux 2.4V / 2.4E family",
            "field": "powertrain_specifications",
            "value": {
                "displacement_cc": 2393,
                "power_ps_candidates": [204, 150],
                "torque_nm_candidates": [500, 400]
            },
            "status": "REVIEW_REQUIRED",
            "source_file": source,
            "master_ready": False,
            "reason": "Multiple 2.4 variants require column-level binding"
        })

    elif source == "hilux-bev-e-brochure.txt":

        results.append({
            "variant": "Hilux BEV",
            "field": "motor_power_ps",
            "value": 196,
            "status": "REVIEW_REQUIRED",
            "source_file": source,
            "master_ready": False,
            "reason": "OCR evidence identifies power but complete BEV specification binding is incomplete"
        })


# ------------------------------------------------------------
# VELLFIRE
# ------------------------------------------------------------

for r in current:

    if r["family"] != "Vellfire":
        continue

    source = r["source_file"]
    fields = r["resolved_fields"]

    # HEV section
    results.extend([
        candidate(
            "Vellfire 2.5 HEV",
            "engine_displacement_cc",
            fields["hev_displacement_cc"]["value"],
            source
        ),
        candidate(
            "Vellfire 2.5 HEV",
            "engine_power_ps",
            fields["hev_engine_power_ps"]["value"],
            source
        ),
        candidate(
            "Vellfire 2.5 HEV",
            "engine_torque_nm",
            fields["hev_engine_torque_nm"]["value"],
            source
        ),
        candidate(
            "Vellfire 2.5 HEV",
            "motor_power_ps",
            fields["motor_power_ps"]["value"],
            source
        ),
        candidate(
            "Vellfire 2.5 HEV",
            "motor_torque_nm",
            fields["motor_torque_nm"]["value"],
            source
        ),
        candidate(
            "Vellfire 2.5 HEV",
            "combined_power_ps",
            fields["combined_power_ps"]["value"],
            source
        ),
        candidate(
            "Vellfire 2.4T",
            "engine_displacement_cc",
            fields["turbo_displacement_cc"]["value"],
            source
        ),
        candidate(
            "Vellfire 2.4T",
            "engine_power_ps",
            fields["turbo_engine_power_ps"]["value"],
            source
        ),
        candidate(
            "Vellfire 2.4T",
            "engine_torque_nm",
            fields["turbo_engine_torque_nm"]["value"],
            source
        ),
    ])


# ------------------------------------------------------------
# HIACE
# ------------------------------------------------------------

for r in current:

    if r["family"] != "Hiace":
        continue

    source = r["source_file"]

    results.append({
        "variant": "Hiace / Hiace SLWB",
        "field": "technical_specifications",
        "value": None,
        "status": "REVIEW_REQUIRED",
        "source_file": source,
        "master_ready": False,
        "reason": "Current OCR extraction contains insufficient technical context"
    })


# ------------------------------------------------------------
# VALIDATE VARIANT EXISTENCE
# ------------------------------------------------------------

for item in results:

    variant = item["variant"]

    # Split family from variant for master lookup.
    matched = False

    for model_name, model in master_map.items():

        if variant.startswith(model_name):
            matched = True
            break

    item["master_variant_match"] = matched

    if not matched:
        item["status"] = "REVIEW_REQUIRED"
        item["master_ready"] = False
        item["reason"] = "Variant not found in current master"


# ------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------

summary = {
    "total_candidates": len(results),
    "verified_candidates": sum(
        1 for x in results
        if x["status"] == "VERIFIED"
    ),
    "candidate_fields": sum(
        1 for x in results
        if x["status"] == "CANDIDATE"
    ),
    "review_required": sum(
        1 for x in results
        if x["status"] == "REVIEW_REQUIRED"
    ),
    "master_variant_unmatched": sum(
        1 for x in results
        if not x.get("master_variant_match")
    ),
    "master_modified": False
}


output = {
    "generated_at": datetime.now().isoformat(),
    "resolver_version": "v2",
    "policy": {
        "master_import_allowed": False,
        "candidate_only": True,
        "unknown_not_guessed": True,
        "historical_source_not_used_for_current_binding": True
    },
    "summary": summary,
    "records": results
}


with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


report = {
    "generated_at": datetime.now().isoformat(),
    "resolver_version": "v2",
    **summary
}


with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print("TOYOTA CANONICAL VARIANT BINDING v2")
print("=" * 100)
print("Total candidates       :", summary["total_candidates"])
print("Verified               :", summary["verified_candidates"])
print("Candidate fields       :", summary["candidate_fields"])
print("Review required        :", summary["review_required"])
print("Unmatched master       :", summary["master_variant_unmatched"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
