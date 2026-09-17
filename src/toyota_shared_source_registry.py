#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

MASTER = BASE / "data/toyota_models.json"
CATALOGUE = BASE / "data/toyota_catalogue_details.json"
BROCHURES = BASE / "data/toyota_brochure_sources.json"
PRIMARY = BASE / "data/toyota_primary_candidates.json"

OUT = BASE / "data/toyota_shared_source_registry.json"
REPORT = BASE / "reports/toyota_shared_source_registry.json"


with open(MASTER, encoding="utf-8") as f:
    master = json.load(f)

with open(CATALOGUE, encoding="utf-8") as f:
    catalogue = json.load(f)

with open(BROCHURES, encoding="utf-8") as f:
    brochures = json.load(f)

with open(PRIMARY, encoding="utf-8") as f:
    primary = json.load(f)


master_models = [
    m.get("model_name")
    for m in master.get("models", [])
]

primary_by_model = {
    r.get("model_name_candidate"): r
    for r in primary.get("records", [])
}


# Explicit mappings based ONLY on sources already collected.
# These are source relationships, NOT spec/price imports.
shared_mappings = {
    "Yaris Cross": {
        "source_model": "Yaris Cross HEV",
        "source_file": "all-new-yaris-cross-hev-e-brochure.txt",
        "status": "SHARED_SOURCE_REVIEW",
        "reason": "Official Yaris Cross and Yaris Cross HEV catalogue URLs exist; current brochure is named for Yaris Cross HEV. Do not copy HEV specs into petrol model."
    },

    "Hiace SLWB": {
        "source_model": "Hiace",
        "source_file": "hiace-e-brochure.txt",
        "status": "SHARED_SOURCE_REVIEW",
        "reason": "Official Hiace SLWB model URL exists and current Hiace brochure exists, but OCR did not directly identify Hiace SLWB."
    },

    "Vellfire": {
        "source_model": "Alphard",
        "source_file": "vellfire-alphard-e-brochure.txt",
        "status": "SHARED_SOURCE_CONFIRMED",
        "reason": "Current official brochure is explicitly combined for Vellfire and Alphard; OCR contains Vellfire evidence."
    },

    "Vellfire HEV": {
        "source_model": "Alphard",
        "source_file": "vellfire-alphard-e-brochure.txt",
        "status": "SHARED_SOURCE_REVIEW",
        "reason": "Official Vellfire HEV model URL exists and combined Vellfire/Alphard brochure exists, but OCR did not directly identify the exact 'Vellfire HEV' label."
    },

    "Hilux": {
        "source_model": "Hilux GR Sport",
        "source_file": "hilux-gr-s-rogue-e-brochure.txt",
        "status": "REVIEW_REQUIRED",
        "reason": "OCR contains Hilux evidence, but GR Sport brochure must not automatically be treated as base Hilux specification source."
    },

    "Camry": {
        "source_model": "Camry HEV",
        "source_file": "camry-e-brochure.txt",
        "status": "REVIEW_REQUIRED",
        "reason": "Official Camry ICE URL exists, but the current primary candidate is Camry HEV. ICE brochure/source needs explicit evidence before importing ICE specifications."
    },

    "Corolla Cross": {
        "source_model": "Corolla Cross HEV",
        "source_file": "corolla-cross-hev-e-brochure.txt",
        "status": "REVIEW_REQUIRED",
        "reason": "Official Corolla Cross URL exists, but HEV brochure must not automatically be treated as base 1.8V specification source."
    }
}


registry = {
    "generated_at": datetime.now().isoformat(),
    "policy": {
        "primary_source": "Toyota Malaysia Official",
        "shared_source_allowed": True,
        "shared_source_requires_evidence": True,
        "do_not_copy_variant_specs": True,
        "do_not_copy_prices": True,
        "unknown_remains_unknown": True,
        "master_modified": False
    },
    "records": []
}


for model in master_models:

    if model in primary_by_model:
        p = primary_by_model[model]

        registry["records"].append({
            "model_name": model,
            "coverage_type": "DIRECT_PRIMARY",
            "status": "PRIMARY_COVERED",
            "source_model": model,
            "source_file": p.get("source_file"),
            "source_priority": p.get("source_priority"),
            "candidate_score": p.get("candidate_score")
        })

    elif model in shared_mappings:

        x = shared_mappings[model]

        registry["records"].append({
            "model_name": model,
            "coverage_type": "SHARED_SOURCE",
            **x
        })

    else:

        registry["records"].append({
            "model_name": model,
            "coverage_type": "MISSING",
            "status": "REVIEW_REQUIRED",
            "reason": "No direct primary candidate or explicit shared-source mapping."
        })


with open(OUT, "w", encoding="utf-8") as f:
    json.dump(registry, f, indent=2, ensure_ascii=False)


summary = {
    "generated_at": datetime.now().isoformat(),
    "master_models": len(master_models),
    "direct_primary": sum(
        1 for r in registry["records"]
        if r["coverage_type"] == "DIRECT_PRIMARY"
    ),
    "shared_source": sum(
        1 for r in registry["records"]
        if r["coverage_type"] == "SHARED_SOURCE"
    ),
    "missing": sum(
        1 for r in registry["records"]
        if r["coverage_type"] == "MISSING"
    ),
    "shared_source_confirmed": sum(
        1 for r in registry["records"]
        if r["coverage_type"] == "SHARED_SOURCE"
        and r["status"] == "SHARED_SOURCE_CONFIRMED"
    ),
    "shared_source_review": sum(
        1 for r in registry["records"]
        if r["coverage_type"] == "SHARED_SOURCE"
        and r["status"] == "SHARED_SOURCE_REVIEW"
    ),
    "review_required": sum(
        1 for r in registry["records"]
        if r["status"] == "REVIEW_REQUIRED"
    ),
    "master_modified": False
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)


print("TOYOTA SHARED SOURCE REGISTRY")
print("=" * 80)

for r in registry["records"]:
    print(
        f"{r['model_name']:30} "
        f"{r['coverage_type']:16} "
        f"{r['status']}"
    )

print()
print("=" * 80)
print("SUMMARY")
print("Master models          :", summary["master_models"])
print("Direct primary         :", summary["direct_primary"])
print("Shared source          :", summary["shared_source"])
print("Shared confirmed       :", summary["shared_source_confirmed"])
print("Shared review          :", summary["shared_source_review"])
print("Missing                :", summary["missing"])
print("Review required        :", summary["review_required"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
