#!/usr/bin/env python3

import json
import os
from datetime import datetime

BASE = "/opt/toyota-malaysia-ai"

MASTER = f"{BASE}/data/toyota_models.json"
CANDIDATES = f"{BASE}/data/toyota_canonical_variant_candidates_v3.json"

OUT = f"{BASE}/data/toyota_customer_kb.json"
REPORT = f"{BASE}/reports/toyota_customer_kb_build.json"

with open(MASTER, encoding="utf-8") as f:
    master = json.load(f)

with open(CANDIDATES, encoding="utf-8") as f:
    candidate_data = json.load(f)

models = master.get("models", [])
candidates = candidate_data.get("records", [])

# Candidate lookup
candidate_map = {}

for c in candidates:
    model = c.get("model_name")
    variant = c.get("variant_name")

    if not model:
        continue

    key = (model.lower().strip(), (variant or "").lower().strip())

    candidate_map[key] = c


def clean_value(v):
    if v is None:
        return None

    if isinstance(v, list):
        return v if v else None

    if isinstance(v, dict):
        return v if v else None

    return v


def copy_if_present(dst, src, field):
    value = clean_value(src.get(field))
    if value is not None:
        dst[field] = value


customer_models = []

for model in models:

    out_model = {
        "model_name": model.get("model_name"),
        "model_id": model.get("id"),
        "country": "Malaysia",
        "currency": "MYR",
        "source_policy": {
            "primary": "Toyota Malaysia Official",
            "no_guessing": True,
            "unknown_fields_are_null": True
        },
        "customer_answer_policy": {
            "review_required": False,
            "unknown_response": (
                "Verified information for this item is currently "
                "not available in the approved Toyota Malaysia knowledge base."
            )
        }
    }

    # Preserve existing model-level data
    for field in [
        "body_type",
        "fuel_type",
        "price",
        "starting_price",
        "engine",
        "performance",
        "transmission",
        "dimensions",
        "safety",
        "features",
        "warranty",
        "source",
        "status"
    ]:
        if field in model:
            out_model[field] = model[field]

    variants = model.get("variants", [])

    customer_variants = []

    # Existing master variants
    for v in variants:

        variant_name = (
            v.get("variant_name")
            or v.get("name")
            or v.get("variant")
        )

        cv = dict(v)

        # Match candidate
        match = candidate_map.get(
            (
                model.get("model_name", "").lower().strip(),
                (variant_name or "").lower().strip()
            )
        )

        if match:
            for field in [
                "engine_displacement_cc",
                "engine_power_ps",
                "engine_torque_nm",
                "hev_engine_power_ps",
                "hev_engine_torque_nm",
                "motor_power_ps",
                "motor_output_kw",
                "motor_torque_nm",
                "combined_power_ps",
                "transmission"
            ]:
                copy_if_present(cv, match, field)

            if match.get("source_url"):
                cv["technical_source"] = match["source_url"]

        customer_variants.append(cv)

    # Candidate variants not already represented in master
    existing_names = {
        str(
            v.get("variant_name")
            or v.get("name")
            or v.get("variant")
            or ""
        ).lower().strip()
        for v in customer_variants
    }

    model_name = model.get("model_name", "").lower().strip()

    for c in candidates:

        if c.get("model_name", "").lower().strip() != model_name:
            continue

        variant_name = c.get("variant_name")

        if not variant_name:
            continue

        if variant_name.lower().strip() in existing_names:
            continue

        nv = {
            "variant_name": variant_name
        }

        for field in [
            "fuel_type",
            "price",
            "engine_displacement_cc",
            "engine_power_ps",
            "engine_torque_nm",
            "hev_engine_power_ps",
            "hev_engine_torque_nm",
            "motor_power_ps",
            "motor_output_kw",
            "motor_torque_nm",
            "combined_power_ps",
            "transmission"
        ]:
            copy_if_present(nv, c, field)

        if c.get("source_url"):
            nv["technical_source"] = c["source_url"]

        customer_variants.append(nv)
        existing_names.add(variant_name.lower().strip())

    if customer_variants:
        out_model["variants"] = customer_variants

    customer_models.append(out_model)


customer_kb = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "schema_version": "customer-kb-1.0",
    "country": "Malaysia",
    "currency": "MYR",
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "secondary": [],
        "no_hallucination": True,
        "unknown_values": None,
        "review_required_for_customer": False
    },
    "customer_response_policy": {
        "answer_verified_information_only": True,
        "never_guess": True,
        "never_expose_internal_review_status": True,
        "unknown_response": (
            "Verified information for this item is currently "
            "not available in the approved Toyota Malaysia knowledge base."
        )
    },
    "total_models": len(customer_models),
    "models": customer_models
}


os.makedirs(os.path.dirname(OUT), exist_ok=True)
os.makedirs(os.path.dirname(REPORT), exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(customer_kb, f, indent=2, ensure_ascii=False)

report = {
    "generated_at": customer_kb["generated_at"],
    "master_models": len(models),
    "customer_kb_models": len(customer_models),
    "candidate_records": len(candidates),
    "master_modified": False,
    "review_required_customer_side": False,
    "output": OUT
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print("=" * 80)
print("TOYOTA CUSTOMER KB BUILD")
print("=" * 80)
print("Master models       :", len(models))
print("Customer KB models  :", len(customer_models))
print("Candidates processed:", len(candidates))
print("Customer review     : DISABLED")
print("Master modified     : NO")
print()
print("OUTPUT :", OUT)
print("REPORT :", REPORT)
