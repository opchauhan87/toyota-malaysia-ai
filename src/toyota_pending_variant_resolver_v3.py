#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_canonical_variant_candidates.json"
OUT = BASE / "data/toyota_canonical_variant_candidates_v3.json"
REPORT = BASE / "reports/toyota_pending_variant_resolver_v3.json"

with open(INPUT, encoding="utf-8") as f:
    data = json.load(f)

records = data["records"]

# ------------------------------------------------------------
# 1. COROLLA CROSS HEV GR SPORT
# Official current 2026 Toyota Malaysia brochure
# ------------------------------------------------------------

records = [
    r for r in records
    if not (
        r.get("variant") == "Corolla Cross HEV GR Sport"
        and r.get("status") == "REVIEW_REQUIRED"
    )
]

source = (
    "https://www.toyota.com.my/content/dam/malaysia/"
    "model-brochures/brochures/corolla-cross-hev-gr/"
    "2026/corolla-cross-hev-gr-sport-brochure.pdf"
)

gr_records = [
    {
        "variant": "Corolla Cross HEV GR Sport",
        "field": "engine_displacement_cc",
        "value": 1798,
        "status": "CANDIDATE",
        "source_file": source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026",
        "master_ready": False
    },
    {
        "variant": "Corolla Cross HEV GR Sport",
        "field": "engine_power_ps",
        "value": 98,
        "status": "CANDIDATE",
        "source_file": source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026",
        "master_ready": False
    },
    {
        "variant": "Corolla Cross HEV GR Sport",
        "field": "engine_torque_nm",
        "value": 142,
        "status": "CANDIDATE",
        "source_file": source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026",
        "master_ready": False
    },
    {
        "variant": "Corolla Cross HEV GR Sport",
        "field": "motor_output_kw",
        "value": 53,
        "status": "CANDIDATE",
        "source_file": source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026",
        "master_ready": False
    },
    {
        "variant": "Corolla Cross HEV GR Sport",
        "field": "motor_torque_nm",
        "value": 163,
        "status": "CANDIDATE",
        "source_file": source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026",
        "master_ready": False
    },
    {
        "variant": "Corolla Cross HEV GR Sport",
        "field": "transmission",
        "value": "E-CVT",
        "status": "CANDIDATE",
        "source_file": source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026",
        "master_ready": False
    }
]

records.extend(gr_records)


# ------------------------------------------------------------
# 2. HIACE SLWB
# Official Toyota Malaysia price list confirms identity,
# displacement and transmission.
# Do NOT infer power/torque from Panel Van 3.0 brochure.
# ------------------------------------------------------------

hiace_source = (
    "https://www.toyota.com.my/content/dam/malaysia/"
    "price-list-maintenance-packages/all-new-hiace/"
    "january-2026/5.0-swk-%28ip-cp%29-hiace-slwb-price-list.pdf"
)

records = [
    r for r in records
    if not (
        r.get("variant") == "Hiace / Hiace SLWB"
        and r.get("status") == "REVIEW_REQUIRED"
    )
]

records.extend([
    {
        "variant": "Hiace SLWB",
        "field": "engine_displacement_cc",
        "value": 2755,
        "status": "CANDIDATE",
        "source_file": hiace_source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026_PRICE_LIST",
        "master_ready": False,
        "reason": "Official price list identifies SLWB 2.8D"
    },
    {
        "variant": "Hiace SLWB",
        "field": "transmission",
        "value": "Automatic",
        "status": "CANDIDATE",
        "source_file": hiace_source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026_PRICE_LIST",
        "master_ready": False,
        "reason": "Official price list identifies 2.8D AT"
    },
    {
        "variant": "Hiace SLWB",
        "field": "engine_power_ps",
        "value": None,
        "status": "REVIEW_REQUIRED",
        "source_file": hiace_source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026_PRICE_LIST",
        "master_ready": False,
        "reason": "Power not present in verified source used here"
    },
    {
        "variant": "Hiace SLWB",
        "field": "engine_torque_nm",
        "value": None,
        "status": "REVIEW_REQUIRED",
        "source_file": hiace_source,
        "source_type": "TOYOTA_OFFICIAL_CURRENT_2026_PRICE_LIST",
        "master_ready": False,
        "reason": "Torque not present in verified source used here"
    }
])


# ------------------------------------------------------------
# 3. HILUX BEV
# Keep 196 PS as candidate only.
# ------------------------------------------------------------

for r in records:
    if (
        r.get("variant") == "Hilux BEV"
        and r.get("field") == "motor_power_ps"
    ):
        r["status"] = "CANDIDATE"
        r["reason"] = (
            "Current Toyota brochure OCR explicitly identifies "
            "196 PS power front motor; remaining BEV fields unresolved"
        )


# ------------------------------------------------------------
# 4. HILUX 2.4 FAMILY
# Explicitly preserve unresolved table-column mapping.
# ------------------------------------------------------------

for r in records:

    if r.get("variant") != "Hilux 2.4V / 2.4E family":
        continue

    r["status"] = "REVIEW_REQUIRED"
    r["master_ready"] = False
    r["reason"] = (
        "Current brochure table contains multiple 2.4 variants "
        "and two power/torque sets; exact column binding required"
    )


# ------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------

summary = {
    "total_records": len(records),
    "candidate": sum(
        1 for r in records
        if r.get("status") == "CANDIDATE"
    ),
    "verified": sum(
        1 for r in records
        if r.get("status") == "VERIFIED"
    ),
    "review_required": sum(
        1 for r in records
        if r.get("status") == "REVIEW_REQUIRED"
    ),
    "master_modified": False
}

output = {
    "generated_at": datetime.now().isoformat(),
    "resolver_version": "v3",
    "policy": {
        "official_current_sources_preferred": True,
        "historical_sources_not_used_for_current_binding": True,
        "unknown_not_guessed": True,
        "master_import_allowed": False
    },
    "summary": summary,
    "records": records
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump({
        "generated_at": datetime.now().isoformat(),
        "resolver_version": "v3",
        **summary
    }, f, indent=2, ensure_ascii=False)

print("TOYOTA PENDING VARIANT RESOLVER v3")
print("=" * 100)
print("Total records :", summary["total_records"])
print("Candidates    :", summary["candidate"])
print("Verified      :", summary["verified"])
print("Review        :", summary["review_required"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
