#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

MASTER = BASE / "data/toyota_models.json"
VALIDATED = BASE / "data/toyota_validated_candidates.json"
REGISTRY = BASE / "data/toyota_shared_source_registry.json"

OUT = BASE / "data/toyota_canonical_candidates.json"
REPORT = BASE / "reports/toyota_canonical_candidate_report.json"


with open(MASTER, encoding="utf-8") as f:
    master = json.load(f)

with open(VALIDATED, encoding="utf-8") as f:
    validated = json.load(f)["records"]

with open(REGISTRY, encoding="utf-8") as f:
    registry = json.load(f)["records"]


master_models = [
    m.get("model_name")
    for m in master.get("models", [])
]

registry_map = {
    r.get("model_name"): r
    for r in registry
}


candidate_map = {}

for r in validated:
    candidate_map.setdefault(
        r.get("model_name"),
        []
    ).append(r)


# Explicit canonical mapping.
# These mappings control SOURCE association only.
# They do NOT copy specifications between models.
shared_source_map = {
    "Yaris Cross": {
        "candidate_models": ["Yaris Cross HEV"],
        "source_file": "all-new-yaris-cross-hev-e-brochure.txt",
        "reason": "Shared current Yaris Cross brochure contains both petrol and HEV powertrain sections."
    },

    "Hilux": {
        "candidate_models": ["Hilux GR Sport"],
        "source_file": "hilux-gr-s-rogue-e-brochure.txt",
        "reason": "Current Hilux brochure explicitly contains base 2.4 and 2.8 Rogue variants."
    },

    "Vellfire": {
        "candidate_models": ["Alphard", "Vellfire"],
        "source_file": "vellfire-alphard-e-brochure.txt",
        "reason": "Combined current brochure contains separate Alphard and Vellfire sections."
    },

    "Vellfire HEV": {
        "candidate_models": ["Vellfire"],
        "source_file": "vellfire-alphard-e-brochure.txt",
        "reason": "Official Vellfire HEV model page is primary; combined brochure provides supporting Vellfire HEV evidence."
    },

    "Hiace SLWB": {
        "candidate_models": ["Hiace"],
        "source_file": "hiace-e-brochure.txt",
        "reason": "Official Hiace SLWB model URL is primary; current Hiace brochure is supporting source."
    },

    "Camry": {
        "candidate_models": [],
        "source_file": "camry-e-brochure.txt",
        "reason": "Official Camry ICE model page is primary; brochure is supporting source."
    },

    "Corolla Cross": {
        "candidate_models": [],
        "source_file": "corolla-cross-hev-e-brochure.txt",
        "reason": "Official Corolla Cross model page is primary; HEV brochure is not used to copy petrol specifications."
    }
}


records = []
used_candidate_keys = set()

for model in master_models:

    reg = registry_map.get(model, {})

    # Direct primary candidate.
    direct = candidate_map.get(model, [])

    if direct:
        # Prefer current primary.
        selected = None

        for c in direct:
            if c.get("source_priority") == "CURRENT_PRIMARY":
                selected = c
                break

        if selected is None:
            selected = direct[0]

        records.append({
            "canonical_model": model,
            "candidate_model": selected.get("model_name"),
            "source_file": selected.get("source_file"),
            "source_priority": selected.get("source_priority"),
            "coverage_type": reg.get("coverage_type"),
            "registry_status": reg.get("status"),
            "candidate_status": selected.get("validation_status"),
            "technical_candidates": selected.get("technical"),
            "rejected_candidates": selected.get("rejected_candidates"),
            "canonicalization": "DIRECT",
            "master_import_allowed": False
        })

        used_candidate_keys.add(
            (
                selected.get("model_name"),
                selected.get("source_file")
            )
        )

        continue

    # Explicit shared-source mapping.
    mapping = shared_source_map.get(model)

    if mapping:

        source_file = mapping["source_file"]

        candidates = []

        for candidate_model in mapping["candidate_models"]:

            for c in candidate_map.get(candidate_model, []):

                if c.get("source_file") == source_file:
                    candidates.append(c)

        # Candidate evidence is retained, but NEVER copied automatically.
        evidence = []

        for c in candidates:
            evidence.append({
                "candidate_model": c.get("model_name"),
                "source_file": c.get("source_file"),
                "source_priority": c.get("source_priority"),
                "validation_status": c.get("validation_status"),
                "technical": c.get("technical"),
                "rejected_candidates": c.get("rejected_candidates")
            })

            used_candidate_keys.add(
                (
                    c.get("model_name"),
                    c.get("source_file")
                )
            )

        records.append({
            "canonical_model": model,
            "candidate_model": None,
            "source_file": source_file,
            "source_priority": "CURRENT_PRIMARY_OR_OFFICIAL_WEB",
            "coverage_type": reg.get("coverage_type"),
            "registry_status": reg.get("status"),
            "canonicalization": "SHARED_SOURCE",
            "shared_source_reason": mapping["reason"],
            "source_candidates": evidence,
            "technical_candidates": {},
            "master_import_allowed": False
        })

        continue

    # No source.
    records.append({
        "canonical_model": model,
        "candidate_model": None,
        "source_file": None,
        "source_priority": None,
        "coverage_type": reg.get("coverage_type"),
        "registry_status": reg.get("status"),
        "canonicalization": "UNRESOLVED",
        "technical_candidates": {},
        "master_import_allowed": False
    })


# Candidate records not consumed by canonical master mapping.
unused = []

for c in validated:

    key = (
        c.get("model_name"),
        c.get("source_file")
    )

    if key not in used_candidate_keys:
        unused.append({
            "model_name": c.get("model_name"),
            "source_file": c.get("source_file"),
            "source_priority": c.get("source_priority")
        })


output = {
    "generated_at": datetime.now().isoformat(),
    "canonical_model_count": len(records),
    "records": records,
    "unused_candidate_records": unused,
    "policy": {
        "canonical_master_models_are_authoritative": True,
        "shared_source_requires_variant_context": True,
        "no_cross_model_spec_copy": True,
        "no_price_import": True,
        "master_modified": False
    }
}


with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


summary = {
    "generated_at": datetime.now().isoformat(),
    "master_models": len(master_models),
    "canonical_records": len(records),
    "direct": sum(
        1 for r in records
        if r["canonicalization"] == "DIRECT"
    ),
    "shared_source": sum(
        1 for r in records
        if r["canonicalization"] == "SHARED_SOURCE"
    ),
    "unresolved": sum(
        1 for r in records
        if r["canonicalization"] == "UNRESOLVED"
    ),
    "unused_candidate_records": len(unused),
    "master_modified": False
}


with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)


print("TOYOTA CANONICAL CANDIDATE ENGINE")
print("=" * 90)

print("Master models              :", summary["master_models"])
print("Canonical records          :", summary["canonical_records"])
print("Direct                     :", summary["direct"])
print("Shared source              :", summary["shared_source"])
print("Unresolved                 :", summary["unresolved"])
print("Unused candidate records   :", summary["unused_candidate_records"])

print()
print("UNUSED CANDIDATES:")

for x in unused:
    print(
        " ",
        x["model_name"],
        "|",
        x["source_file"],
        "|",
        x["source_priority"]
    )

print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
