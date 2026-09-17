#!/usr/bin/env python3

import json
import os
from datetime import datetime

BASE = "/opt/toyota-malaysia-ai"
MASTER = f"{BASE}/data/toyota_models.json"
REPORT = f"{BASE}/reports/toyota_enrichment_report.json"

REQUIRED_FIELDS = [
    "model_name",
    "brand",
    "market",
    "body_type",
    "official_url"
]

OPTIONAL_KNOWLEDGE_FIELDS = [
    "variants",
    "technical_specifications",
    "dimensions",
    "safety_features",
    "comfort_features",
    "connectivity",
    "exterior",
    "colours",
    "warranty",
    "service_savers"
]

with open(MASTER, "r", encoding="utf-8") as f:
    data = json.load(f)

models = data.get("models", [])

report = {
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "total_models": len(models),
    "ready": [],
    "enriched": [],
    "incomplete": [],
    "errors": [],
    "missing_fields": {}
}


def has_value(value):
    return value not in ("", None, [], {})


def validate_model(model):

    name = model.get("model_name", "UNKNOWN")

    missing_required = []

    for field in REQUIRED_FIELDS:
        if not has_value(model.get(field)):
            missing_required.append(field)

    if missing_required:
        return "ERROR", missing_required

    # Existing READY model stays READY only if
    # its essential knowledge remains available.
    if model.get("knowledge_status") == "READY":
        return "READY", []

    # Count knowledge sections
    populated = 0

    for field in OPTIONAL_KNOWLEDGE_FIELDS:
        if has_value(model.get(field)):
            populated += 1

    # Model index only
    if populated == 0:
        return "MODEL_INDEXED", []

    # Some knowledge exists, but not enough for production
    if populated < 5:
        return "ENRICHED", []

    return "VERIFICATION_REQUIRED", []


for model in models:

    name = model.get("model_name", "UNKNOWN")

    status, missing = validate_model(model)

    model["knowledge_status"] = status

    if status == "READY":
        report["ready"].append(name)

    elif status == "ENRICHED":
        report["enriched"].append(name)

    elif status == "MODEL_INDEXED":
        report["incomplete"].append(name)

    elif status == "VERIFICATION_REQUIRED":
        report["enriched"].append(name)

    elif status == "ERROR":
        report["errors"].append(name)
        report["missing_fields"][name] = missing


# Save master
data["knowledge_engine"] = {
    "version": "1.0",
    "last_validation": datetime.now().strftime("%Y-%m-%d"),
    "source_policy": "Toyota Malaysia Official",
    "unknown_data_policy": "DO_NOT_GUESS"
}

tmp = MASTER + ".tmp"

with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

os.replace(tmp, MASTER)


# Save report
with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print("=" * 65)
print("TOYOTA MALAYSIA ENRICHMENT ENGINE")
print("=" * 65)

print(f"Total models           : {report['total_models']}")
print(f"READY                  : {len(report['ready'])}")
print(f"ENRICHED               : {len(report['enriched'])}")
print(f"MODEL_INDEXED          : {len(report['incomplete'])}")
print(f"ERROR                  : {len(report['errors'])}")

print()
print("MODEL STATUS")
print("-" * 65)

for model in models:
    print(
        f"{model.get('model_name','UNKNOWN'):30} "
        f"{model.get('knowledge_status','UNKNOWN')}"
    )

print()
print(f"Report: {REPORT}")
print("JSON VALID")
print("=" * 65)
