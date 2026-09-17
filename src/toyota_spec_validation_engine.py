#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_source_prioritized.json"
OUT = BASE / "data/toyota_verified_candidates.json"
REPORT = BASE / "reports/toyota_spec_validation_report.json"

OUT.parent.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def unique(values):
    seen = set()
    result = []

    for value in values:
        key = norm(value)

        if key and key not in seen:
            seen.add(key)
            result.append(value)

    return result


# ------------------------------------------------------------
# Model-specific sanity ranges
# These are VALIDATION ranges, not values to invent.
# ------------------------------------------------------------

MODEL_RANGES = {
    "Vios": {
        "cc": (1300, 1700),
        "ps": (70, 140),
        "nm": (100, 180)
    },
    "Yaris": {
        "cc": (1300, 1700),
        "ps": (70, 140),
        "nm": (100, 180)
    },
    "Yaris Cross": {
        "cc": (1300, 1700),
        "ps": (70, 150),
        "nm": (100, 200)
    },
    "Corolla": {
        "cc": (1500, 2000),
        "ps": (100, 180),
        "nm": (130, 220)
    },
    "Corolla GR Sport": {
        "cc": (1500, 2000),
        "ps": (100, 180),
        "nm": (130, 220)
    },
    "Corolla Cross": {
        "cc": (1500, 2000),
        "ps": (100, 200),
        "nm": (130, 250)
    },
    "Corolla Cross HEV": {
        "cc": (1400, 2000),
        "ps": (80, 220),
        "nm": (100, 300)
    },
    "Corolla Cross HEV GR Sport": {
        "cc": (1400, 2000),
        "ps": (80, 220),
        "nm": (100, 300)
    },
    "Camry": {
        "cc": (1800, 3000),
        "ps": (120, 260),
        "nm": (150, 350)
    },
    "Camry HEV": {
        "cc": (1800, 3000),
        "ps": (120, 260),
        "nm": (150, 350)
    },
    "Veloz": {
        "cc": (1300, 1700),
        "ps": (70, 130),
        "nm": (100, 180)
    },
    "Innova Zenix": {
        "cc": (1800, 2500),
        "ps": (120, 200),
        "nm": (150, 300)
    },
    "Fortuner": {
        "cc": (2000, 3000),
        "ps": (120, 220),
        "nm": (250, 550)
    },
    "Harrier HEV": {
        "cc": (1800, 2500),
        "ps": (120, 250),
        "nm": (150, 400)
    },
    "Hilux": {
        "cc": (1800, 3000),
        "ps": (100, 220),
        "nm": (250, 600)
    },
    "Hilux GR Sport": {
        "cc": (1800, 3000),
        "ps": (100, 250),
        "nm": (250, 650)
    },
    "Hilux BEV": {
        "cc": (0, 100),
        "ps": (50, 400),
        "nm": (50, 700)
    },
    "Hiace": {
        "cc": (2000, 3000),
        "ps": (100, 180),
        "nm": (150, 450)
    },
    "Hiace SLWB": {
        "cc": (2000, 3000),
        "ps": (100, 180),
        "nm": (150, 450)
    },
    "bZ4X": {
        "cc": (0, 100),
        "ps": (100, 350),
        "nm": (100, 500)
    },
    "Urban Cruiser BEV": {
        "cc": (0, 100),
        "ps": (80, 350),
        "nm": (100, 600)
    },
    "Alphard": {
        "cc": (2000, 3000),
        "ps": (100, 300),
        "nm": (150, 450)
    },
    "Vellfire": {
        "cc": (2000, 3000),
        "ps": (100, 300),
        "nm": (150, 450)
    },
    "Vellfire HEV": {
        "cc": (2000, 3000),
        "ps": (100, 300),
        "nm": (150, 450)
    },
    "GR Yaris": {
        "cc": (1400, 1700),
        "ps": (200, 350),
        "nm": (250, 500)
    },
    "GR Corolla": {
        "cc": (1400, 1800),
        "ps": (200, 350),
        "nm": (250, 500)
    },
    "GR86": {
        "cc": (1800, 2500),
        "ps": (180, 250),
        "nm": (180, 300)
    }
}


def numbers(values):
    output = []

    for value in values or []:
        try:
            output.append(float(value))
        except Exception:
            pass

    return output


def validate_numeric(model, technical):

    issues = []
    warnings = []

    ranges = MODEL_RANGES.get(model)

    if not ranges:
        warnings.append("NO_MODEL_SPECIFIC_RANGE")
        return issues, warnings

    # ---------------------------------------------------------
    # Displacement
    # Supports both:
    #   1496
    #   1.5L
    # ---------------------------------------------------------

    raw_cc = technical.get(
        "displacement_candidates", []
    )

    cc_values = []

    for value in raw_cc:
        try:
            raw = str(value).strip().lower()
            raw = raw.replace("cc", "").strip()

            if raw.endswith("l"):
                litres = float(raw[:-1])

                if 0.6 <= litres <= 7.0:
                    cc_values.append(litres * 1000)
            else:
                number = float(raw)

                if 600 <= number <= 7000:
                    cc_values.append(number)

        except Exception:
            pass

    if cc_values:
        low, high = ranges["cc"]

        bad = [
            x for x in cc_values
            if not (low <= x <= high)
        ]

        if bad:
            issues.append(
                "SUSPICIOUS_CC:" +
                ",".join(str(x) for x in bad)
            )

    # ---------------------------------------------------------
    # Power
    # ---------------------------------------------------------

    power_values = numbers(
        technical.get("power_candidates", [])
    )

    if power_values:
        low, high = ranges["ps"]

        bad = [
            x for x in power_values
            if not (low <= x <= high)
        ]

        if bad:
            issues.append(
                "SUSPICIOUS_PS:" +
                ",".join(str(x) for x in bad)
            )

    # ---------------------------------------------------------
    # Torque
    # ---------------------------------------------------------

    torque_values = numbers(
        technical.get("torque_candidates", [])
    )

    if torque_values:
        low, high = ranges["nm"]

        bad = [
            x for x in torque_values
            if not (low <= x <= high)
        ]

        if bad:
            issues.append(
                "SUSPICIOUS_NM:" +
                ",".join(str(x) for x in bad)
            )

    return issues, warnings


def validate_dimensions(dimensions):

    issues = []
    warnings = []

    candidates = dimensions.get(
        "vehicle_dimensions_candidates", []
    )

    for item in candidates:

        try:
            length = int(item["length_mm"])
            width = int(item["width_mm"])
            height = int(item["height_mm"])

            if not (2500 <= length <= 6000):
                issues.append(
                    f"SUSPICIOUS_LENGTH:{length}"
                )

            if not (1200 <= width <= 2500):
                issues.append(
                    f"SUSPICIOUS_WIDTH:{width}"
                )

            if not (1200 <= height <= 3000):
                issues.append(
                    f"SUSPICIOUS_HEIGHT:{height}"
                )

        except Exception:
            issues.append("INVALID_DIMENSION_RECORD")

    for value in dimensions.get(
        "wheelbase_candidates_mm", []
    ):

        try:
            value = int(value)

            if not (1800 <= value <= 4000):
                issues.append(
                    f"SUSPICIOUS_WHEELBASE:{value}"
                )

        except Exception:
            issues.append("INVALID_WHEELBASE")

    return issues, warnings


def validate_variants(variants):

    issues = []
    warnings = []

    if not variants:
        warnings.append("NO_VARIANT_DATA")
        return issues, warnings

    # Check for OCR garbage / extremely long candidate strings.
    for value in variants:

        if len(str(value)) > 80:
            issues.append("VARIANT_TEXT_TOO_LONG")

    return issues, warnings


def calculate_score(
    technical,
    dimensions,
    safety,
    features,
    variants,
    source_priority,
    issues,
    warnings
):

    score = 0

    if source_priority == "CURRENT_PRIMARY":
        score += 20
    elif source_priority == "HISTORICAL_OR_SECONDARY":
        score += 5

    if technical.get("displacement_candidates"):
        score += 15

    if technical.get("power_candidates"):
        score += 10

    if technical.get("torque_candidates"):
        score += 10

    if technical.get("transmission_candidates"):
        score += 5

    if technical.get("drivetrain_candidates"):
        score += 5

    if dimensions.get("vehicle_dimensions_candidates"):
        score += 5

    if safety:
        score += 10

    if features:
        score += 10

    if variants:
        score += 5

    score -= min(len(issues) * 15, 45)
    score -= min(len(warnings) * 2, 10)

    return max(0, min(score, 100))


print("TOYOTA MALAYSIA SPECIFICATION VALIDATION ENGINE")
print("=" * 75)

with open(INPUT, encoding="utf-8") as f:
    data = json.load(f)

records = data.get("records", [])

print("Records :", len(records))
print()

validated = []

valid = 0
review = 0
historical = 0
current = 0

for i, record in enumerate(records, 1):

    model = record.get("model_name_candidate")
    technical = record.get("technical_specifications", {})
    dimensions = record.get("dimensions", {})
    safety = record.get("safety_features_candidates", [])
    features = record.get("feature_candidates", [])
    variants = record.get("variants_candidates", [])
    source_priority = record.get("source_priority")

    issues = []
    warnings = []

    # Source checks
    if source_priority == "CURRENT_PRIMARY":
        current += 1

    elif source_priority == "HISTORICAL_OR_SECONDARY":
        historical += 1
        warnings.append("HISTORICAL_SOURCE")

    else:
        warnings.append("UNKNOWN_SOURCE_PRIORITY")

    # Model check
    if not model:
        issues.append("MODEL_UNKNOWN")

    # Technical validation
    x, y = validate_numeric(model, technical)
    issues.extend(x)
    warnings.extend(y)

    # Dimension validation
    x, y = validate_dimensions(dimensions)
    issues.extend(x)
    warnings.extend(y)

    # Variant validation
    x, y = validate_variants(variants)
    issues.extend(x)
    warnings.extend(y)

    issues = unique(issues)
    warnings = unique(warnings)

    score = calculate_score(
        technical,
        dimensions,
        safety,
        features,
        variants,
        source_priority,
        issues,
        warnings
    )

    # A historical source can NEVER become final verified.
    if source_priority == "HISTORICAL_OR_SECONDARY":
        status = "HISTORICAL_REVIEW"

    elif issues:
        status = "REVIEW_REQUIRED"

    elif score >= 75:
        status = "VERIFIED_CANDIDATE"

    else:
        status = "REVIEW_REQUIRED"

    if status == "VERIFIED_CANDIDATE":
        valid += 1
    else:
        review += 1

    result = dict(record)

    result["spec_validation"] = {
        "status": status,
        "confidence_score": score,
        "issues": issues,
        "warnings": warnings,
        "source_priority": source_priority
    }

    # Explicit provenance for future LLM/voice layer
    result["provenance"] = {
        "source_file": record.get("source_file"),
        "source_type": record.get("source_type"),
        "brochure_url": record.get(
            "source_metadata", {}
        ).get("brochure_url"),
        "source_date": record.get(
            "source_metadata", {}
        ).get("source_date"),
        "source_year": record.get(
            "source_metadata", {}
        ).get("source_year")
    }

    validated.append(result)

    print(
        f"[{i:02d}/{len(records)}] "
        f"{str(model):32} "
        f"score={score:3d} "
        f"{status}"
    )

    if issues:
        print(
            "        ISSUES:",
            ", ".join(issues)
        )

    if warnings:
        print(
            "        WARNINGS:",
            ", ".join(warnings[:6])
        )


# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

output = {
    "country": "Malaysia",
    "currency": "MYR",
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "brochure_data_is_source_backed": True,
        "candidate_data_requires_final_review": True,
        "historical_sources_never_auto_promoted": True,
        "master_import": False,
        "unknown_values": None,
        "no_hallucination": True
    },
    "generated_at": datetime.now().isoformat(),
    "total_records": len(validated),
    "verified_candidates": valid,
    "review_required": review,
    "current_sources": current,
    "historical_sources": historical,
    "records": validated
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


report = {
    "generated_at": datetime.now().isoformat(),
    "total_records": len(validated),
    "verified_candidates": valid,
    "review_required": review,
    "current_sources": current,
    "historical_sources": historical,
    "records_with_provenance": sum(
        1 for r in validated
        if r.get("provenance", {}).get("brochure_url")
    ),
    "output": str(OUT),
    "master_modified": False
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print()
print("=" * 75)
print("SPEC VALIDATION SUMMARY")
print("Total records          :", len(validated))
print("Verified candidates    :", valid)
print("Review required        :", review)
print("Current sources        :", current)
print("Historical sources     :", historical)
print("With provenance        :", report["records_with_provenance"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
print("JSON VALID")
