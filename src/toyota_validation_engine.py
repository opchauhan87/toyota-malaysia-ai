#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_structured_candidates.json"
OUT = BASE / "data/toyota_validated_candidates.json"
REPORT = BASE / "reports/toyota_validation_report.json"

OUT.parent.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)


def normalize(value):
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def unique(values):
    seen = set()
    result = []

    for value in values:
        key = normalize(str(value))
        if key and key not in seen:
            seen.add(key)
            result.append(value)

    return result


def brochure_year(filename):
    years = re.findall(r"\b(20\d{2})\b", filename)

    if years:
        return max(int(x) for x in years)

    # Current Toyota Malaysia brochures often use month folders
    months = {
        "january": 2026,
        "february": 2026,
        "march": 2026,
        "april": 2026,
        "may": 2026,
        "june": 2026,
        "july": 2026,
        "august": 2026,
        "september": 2026,
    }

    name = filename.lower()

    for month, year in months.items():
        if month in name:
            return year

    return None


def expected_model_from_filename(filename):
    s = normalize(filename)

    rules = [
        ("GR Corolla", ["gr corolla"]),
        ("GR Yaris", ["gr yaris"]),
        ("GR86", ["gr86"]),
        ("Corolla Cross HEV GR Sport", ["corolla cross hev gr"]),
        ("Corolla Cross HEV", ["corolla cross hev"]),
        ("Corolla Cross", ["corolla cross"]),
        ("Corolla GR Sport", ["corolla gr sport"]),
        ("Vios HEV GR Sport", ["vios hev gr sport"]),
        ("Vios HEV", ["vios hev"]),
        ("Vios", ["vios"]),
        ("Yaris Cross HEV", ["yaris cross", "hev"]),
        ("Yaris Cross", ["yaris cross"]),
        ("Yaris", ["yaris"]),
        ("Camry HEV", ["camry hev"]),
        ("Camry", ["camry"]),
        ("Innova Zenix", ["innova zenix"]),
        ("Fortuner", ["fortuner"]),
        ("Harrier HEV", ["harrier hev"]),
        ("Harrier", ["harrier"]),
        ("Hilux BEV", ["hilux bev"]),
        ("Hilux GR Sport", ["hilux gr"]),
        ("Hilux", ["hilux"]),
        ("Hiace SLWB", ["slwb"]),
        ("Hiace", ["hiace"]),
        ("bZ4X", ["bz4x"]),
        ("Urban Cruiser BEV", ["urban cruiser"]),
        ("Alphard", ["alphard"]),
        ("Vellfire HEV", ["vellfire hev"]),
        ("Vellfire", ["vellfire"]),
        ("Veloz", ["veloz"]),
        ("Corolla", ["corolla"]),
    ]

    for model, keys in rules:
        if all(k in s for k in keys):
            return model

    return None


def validate_record(record):

    issues = []
    warnings = []
    score = 0

    filename = record.get("source_file", "")
    model = record.get("model_name_candidate")

    technical = record.get("technical_specifications", {})
    safety = record.get("safety_features_candidates", [])
    features = record.get("feature_candidates", [])
    variants = record.get("variants_candidates", [])

    expected = expected_model_from_filename(filename)

    # ---------------------------------------------------------
    # Model validation
    # ---------------------------------------------------------

    if model:
        score += 20
    else:
        issues.append("MODEL_NOT_IDENTIFIED")

    if expected and model:

        if normalize(expected) == normalize(model):
            score += 20
        else:
            warnings.append(
                f"FILENAME_MODEL_MISMATCH:{expected}!={model}"
            )

    elif expected:
        score += 10

    # ---------------------------------------------------------
    # Technical data
    # ---------------------------------------------------------

    displacement = technical.get(
        "displacement_candidates", []
    )

    power = technical.get(
        "power_candidates", []
    )

    torque = technical.get(
        "torque_candidates", []
    )

    transmission = technical.get(
        "transmission_candidates", []
    )

    if displacement:
        score += 10
    else:
        warnings.append("NO_DISPLACEMENT_CANDIDATE")

    if power:
        score += 5
    else:
        warnings.append("NO_POWER_CANDIDATE")

    if torque:
        score += 5
    else:
        warnings.append("NO_TORQUE_CANDIDATE")

    if transmission:
        score += 5

    # ---------------------------------------------------------
    # Safety
    # ---------------------------------------------------------

    if len(safety) >= 3:
        score += 10
    elif safety:
        score += 5
        warnings.append("LIMITED_SAFETY_DATA")
    else:
        warnings.append("NO_SAFETY_DATA")

    # ---------------------------------------------------------
    # Features
    # ---------------------------------------------------------

    if len(features) >= 3:
        score += 10
    elif features:
        score += 5
        warnings.append("LIMITED_FEATURE_DATA")
    else:
        warnings.append("NO_FEATURE_DATA")

    # ---------------------------------------------------------
    # Variants
    # ---------------------------------------------------------

    if variants:
        score += 5
    else:
        warnings.append("NO_VARIANT_CANDIDATE")

    # ---------------------------------------------------------
    # Suspicious values
    # ---------------------------------------------------------

    suspicious_cc = []

    for value in displacement:
        try:
            n = float(value)

            # Normal displacement range for Toyota passenger/commercial
            if not (600 <= n <= 7000):
                suspicious_cc.append(value)

        except Exception:
            pass

    if suspicious_cc:
        issues.append(
            "SUSPICIOUS_DISPLACEMENT:" +
            ",".join(map(str, suspicious_cc))
        )

    # ---------------------------------------------------------
    # Determine status
    # ---------------------------------------------------------

    if issues:
        status = "REVIEW_REQUIRED"
    elif score >= 75:
        status = "VALID_CANDIDATE"
    else:
        status = "REVIEW_REQUIRED"

    return {
        "validation_status": status,
        "confidence_score": score,
        "expected_model_from_filename": expected,
        "issues": unique(issues),
        "warnings": unique(warnings)
    }


print("TOYOTA MALAYSIA VALIDATION ENGINE")
print("=" * 70)

with open(INPUT, "r", encoding="utf-8") as f:
    data = json.load(f)

records = data.get("records", [])

print("Candidate records :", len(records))
print()

validated = []

valid = 0
review = 0

# -------------------------------------------------------------
# Validate each record
# -------------------------------------------------------------

for i, record in enumerate(records, 1):

    validation = validate_record(record)

    merged = dict(record)
    merged["validation"] = validation

    validated.append(merged)

    status = validation["validation_status"]
    score = validation["confidence_score"]
    model = record.get("model_name_candidate") or "UNKNOWN"

    if status == "VALID_CANDIDATE":
        valid += 1
    else:
        review += 1

    print(
        f"[{i:02d}/{len(records)}] "
        f"{model:32} "
        f"score={score:3d} "
        f"{status}"
    )

    if validation["issues"]:
        print(
            "        ISSUES :",
            ", ".join(validation["issues"])
        )

    if validation["warnings"]:
        print(
            "        WARNINGS:",
            ", ".join(validation["warnings"][:5])
        )


# -------------------------------------------------------------
# Duplicate detection
# -------------------------------------------------------------

model_map = {}

for record in validated:

    model = record.get("model_name_candidate")

    if not model:
        continue

    key = normalize(model)

    model_map.setdefault(key, []).append(
        record["source_file"]
    )

duplicates = {
    model: files
    for model, files in model_map.items()
    if len(files) > 1
}


# -------------------------------------------------------------
# Latest brochure selection
# -------------------------------------------------------------

latest_by_model = {}

for record in validated:

    model = record.get("model_name_candidate")

    if not model:
        continue

    key = normalize(model)
    year = brochure_year(record["source_file"])

    current = latest_by_model.get(key)

    if current is None:
        latest_by_model[key] = {
            "model_name": model,
            "source_file": record["source_file"],
            "brochure_year": year
        }
        continue

    current_year = current.get("brochure_year")

    if year and (
        not current_year or year > current_year
    ):
        latest_by_model[key] = {
            "model_name": model,
            "source_file": record["source_file"],
            "brochure_year": year
        }


# -------------------------------------------------------------
# Final output
# -------------------------------------------------------------

output = {
    "country": "Malaysia",
    "currency": "MYR",
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "candidate_data": True,
        "master_import_allowed": False,
        "manual_or_rule_validation_required": True,
        "older_brochures_retained": True
    },
    "generated_at": datetime.now().isoformat(),
    "total_records": len(validated),
    "valid_candidates": valid,
    "review_required": review,
    "duplicate_models": duplicates,
    "latest_brochure_by_model": latest_by_model,
    "records": validated
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


report = {
    "generated_at": datetime.now().isoformat(),
    "total_records": len(validated),
    "valid_candidates": valid,
    "review_required": review,
    "duplicate_model_groups": len(duplicates),
    "duplicate_models": duplicates,
    "models_with_latest_source": len(latest_by_model),
    "output": str(OUT)
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print()
print("=" * 70)
print("VALIDATION SUMMARY")
print("Total records          :", len(validated))
print("Valid candidates       :", valid)
print("Review required        :", review)
print("Duplicate model groups :", len(duplicates))
print("Latest source models   :", len(latest_by_model))
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED   : NO")
print("JSON VALID")
