#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")
INPUT = BASE / "data/toyota_source_prioritized.json"
TEXT_DIR = BASE / "data/brochure_ocr"
OUT = BASE / "data/toyota_context_candidates.json"
REPORT = BASE / "reports/toyota_context_extraction_report.json"


def unique(values):
    out = []
    seen = set()

    for value in values:
        value = str(value).strip()
        key = value.lower()

        if value and key not in seen:
            seen.add(key)
            out.append(value)

    return out


def number(value):
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def blocks_near_labels(text, labels, radius=250):
    blocks = []

    for label in labels:
        for m in re.finditer(label, text, re.I):
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + radius)
            blocks.append(text[start:end])

    return unique(blocks)


def extract_power(text):
    blocks = blocks_near_labels(
        text,
        [
            r"MAX\.?\s*OUTPUT",
            r"MAXIMUM\s+OUTPUT",
            r"MAX\.?\s*POWER",
            r"MAXIMUM\s+POWER",
            r"\bHORSEPOWER\b",
            r"\bPOWER\b"
        ],
        220
    )

    values = []

    for block in blocks:
        # ONLY PS / hp. Never kW.
        matches = re.findall(
            r"\b(\d{2,3}(?:\.\d+)?)\s*(?:PS|HP|BHP)\b",
            block,
            re.I
        )

        for x in matches:
            n = number(x)
            if n is not None and 50 <= n <= 600:
                values.append(str(int(n)) if n.is_integer() else str(n))

    return unique(values), blocks


def extract_torque(text):
    blocks = blocks_near_labels(
        text,
        [
            r"MAX\.?\s*TORQUE",
            r"MAXIMUM\s+TORQUE",
            r"\bTORQUE\b"
        ],
        220
    )

    values = []

    for block in blocks:
        matches = re.findall(
            r"\b(\d{2,4}(?:\.\d+)?)\s*(?:Nm|N\.m)\b",
            block,
            re.I
        )

        for x in matches:
            n = number(x)
            if n is not None and 50 <= n <= 900:
                values.append(str(int(n)) if n.is_integer() else str(n))

    return unique(values), blocks


def extract_displacement(text):
    blocks = blocks_near_labels(
        text,
        [
            r"\bDISPLACEMENT\b",
            r"ENGINE\s+CAPACITY",
            r"ENGINE\s+MODEL"
        ],
        300
    )

    cc = []
    litres = []

    for block in blocks:

        for x in re.findall(
            r"\b(\d{3,5})\s*(?:cc|cm3)\b",
            block,
            re.I
        ):
            n = number(x)
            if n is not None and 600 <= n <= 7000:
                cc.append(str(int(n)))

        for x in re.findall(
            r"\b(\d(?:\.\d+)?)\s*(?:L|LITRE|LITER|LITRES|LITERS)\b",
            block,
            re.I
        ):
            n = number(x)
            if n is not None and 0.6 <= n <= 8:
                litres.append(str(x))
                cc.append(str(int(round(n * 1000))))

    return unique(cc), unique(litres), blocks


def extract_transmission(text):
    blocks = blocks_near_labels(
        text,
        [
            r"\bTRANSMISSION\b",
            r"TRANSMISSION\s+TYPE",
            r"\bGEARBOX\b"
        ],
        300
    )

    values = []

    patterns = [
        r"\b\d+\s*[- ]\s*speed[^.\n]{0,100}",
        r"\bE-CVT\b",
        r"\beCVT\b",
        r"\bD-CVT\b",
        r"\bCVT\b",
        r"\bMANUAL\b",
        r"\bAUTOMATIC\b"
    ]

    for block in blocks:
        for pattern in patterns:
            values.extend(re.findall(pattern, block, re.I))

    return unique(values), blocks


def extract_drivetrain(text):
    blocks = blocks_near_labels(
        text,
        [
            r"\bDRIVETRAIN\b",
            r"DRIVE\s+SYSTEM",
            r"WHEEL\s+DRIVE"
        ],
        220
    )

    values = []

    for block in blocks:
        values.extend(
            re.findall(
                r"\b(?:FWD|RWD|AWD|4WD|4X4)\b",
                block,
                re.I
            )
        )

    return unique(values), blocks


def extract_fuel(text):
    blocks = blocks_near_labels(
        text,
        [
            r"FUEL\s+CONSUMPTION",
            r"FUEL\s+ECONOMY",
            r"FUEL\s+EFFICIENCY"
        ],
        220
    )

    values = []

    for block in blocks:
        values.extend(
            re.findall(
                r"\b\d+(?:\.\d+)?\s*(?:L/100KM|KM/L)\b",
                block,
                re.I
            )
        )

    return unique(values), blocks


def extract_dimensions(text):
    blocks = blocks_near_labels(
        text,
        [
            r"\bDIMENSIONS\b",
            r"OVERALL\s+DIMENSIONS",
            r"MEASUREMENTS"
        ],
        500
    )

    dimensions = []
    wheelbases = []

    for block in blocks:

        matches = re.findall(
            r"(\d{3,5})\s*[x×]\s*(\d{3,5})\s*[x×]\s*(\d{3,5})\s*mm",
            block,
            re.I
        )

        for a, b, c in matches:
            dimensions.append({
                "length_mm": int(a),
                "width_mm": int(b),
                "height_mm": int(c)
            })

        wb = re.findall(
            r"(?:wheelbase|wheel\s*base)[^\d]{0,80}(\d{3,5})\s*mm",
            block,
            re.I
        )

        wheelbases.extend(wb)

        # OCR often separates dimension values:
        # 1,475mm ... 2,550mm ... 1,730mm ... 4,140mm
        if not matches:
            nums = re.findall(
                r"\b(\d{1,2},\d{3}|\d{4,5})\s*mm\b",
                block,
                re.I
            )

            nums = [int(x.replace(",", "")) for x in nums]

            # Only create a candidate if there are plausible
            # vehicle dimension numbers in the same block.
            plausible = [
                x for x in nums
                if 1300 <= x <= 6000
            ]

            if len(plausible) >= 3:
                dimensions.append({
                    "raw_dimension_numbers_mm": unique(
                        [str(x) for x in plausible]
                    )
                })

    return dimensions, unique(wheelbases), blocks


def extract_airbags(text):
    blocks = blocks_near_labels(
        text,
        [r"\bAIRBAGS?\b"],
        180
    )

    values = []

    for block in blocks:
        values.extend(
            re.findall(
                r"\b(\d+)\s*(?:airbags|airbag)\b",
                block,
                re.I
            )
        )

    return unique(values), blocks


def extract_variants(text):
    patterns = [
        r"\b\d\.\d[A-Z]+\b",
        r"\b\d\.\d\s*[A-Z]+\b",
        r"\bGR\s+SPORT\b",
        r"\bHEV\b",
        r"\bBEV\b",
        r"\bM/T\b",
        r"\bA/T\b"
    ]

    values = []

    for pattern in patterns:
        values.extend(re.findall(pattern, text, re.I))

    return unique(values)


print("TOYOTA CONTEXT-AWARE SPEC EXTRACTION V2")
print("=" * 75)

with open(INPUT, encoding="utf-8") as f:
    source_data = json.load(f)

records = source_data.get("records", [])
results = []

for i, source in enumerate(records, 1):

    filename = source["source_file"]
    path = TEXT_DIR / filename

    if not path.exists():
        print(f"[{i:02d}] MISSING: {filename}")
        continue

    text = path.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    power, power_evidence = extract_power(text)
    torque, torque_evidence = extract_torque(text)
    cc, litre, displacement_evidence = extract_displacement(text)
    transmission, transmission_evidence = extract_transmission(text)
    drivetrain, drivetrain_evidence = extract_drivetrain(text)
    fuel, fuel_evidence = extract_fuel(text)
    dimensions, wheelbase, dimension_evidence = extract_dimensions(text)
    airbags, airbag_evidence = extract_airbags(text)
    variants = extract_variants(text)

    result = {
        "model_name_candidate": source.get("model_name_candidate"),
        "source_file": filename,
        "source_priority": source.get("source_priority"),
        "source_metadata": source.get("source_metadata", {}),
        "extraction_status": "CONTEXT_CANDIDATE_V2",

        "technical_specifications": {
            "power_ps_candidates": power,
            "torque_nm_candidates": torque,
            "displacement_cc_candidates": cc,
            "displacement_litre_candidates": litre,
            "transmission_candidates": transmission,
            "drivetrain_candidates": drivetrain,
            "fuel_consumption_candidates": fuel
        },

        "dimensions": {
            "vehicle_dimensions_candidates": dimensions,
            "wheelbase_candidates_mm": wheelbase
        },

        "safety": {
            "airbag_count_candidates": airbags
        },

        "variants_candidates": variants,

        "evidence": {
            "power": power_evidence[:8],
            "torque": torque_evidence[:8],
            "displacement": displacement_evidence[:8],
            "transmission": transmission_evidence[:8],
            "drivetrain": drivetrain_evidence[:8],
            "fuel": fuel_evidence[:8],
            "dimensions": dimension_evidence[:8],
            "airbags": airbag_evidence[:8]
        }
    }

    results.append(result)

    print(
        f"[{i:02d}/{len(records)}] "
        f"{str(source.get('model_name_candidate')):32} "
        f"PS={len(power):2d} "
        f"Nm={len(torque):2d} "
        f"CC={len(cc):2d} "
        f"Trans={len(transmission):2d} "
        f"Dim={len(dimensions):2d}"
    )


output = {
    "country": "Malaysia",
    "currency": "MYR",
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "candidate_only": True,
        "no_hallucination": True,
        "master_import": False
    },
    "generated_at": datetime.now().isoformat(),
    "total_records": len(results),
    "records": results
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

report = {
    "generated_at": datetime.now().isoformat(),
    "total_records": len(results),
    "with_power": sum(bool(r["technical_specifications"]["power_ps_candidates"]) for r in results),
    "with_torque": sum(bool(r["technical_specifications"]["torque_nm_candidates"]) for r in results),
    "with_displacement": sum(bool(r["technical_specifications"]["displacement_cc_candidates"]) for r in results),
    "with_transmission": sum(bool(r["technical_specifications"]["transmission_candidates"]) for r in results),
    "with_dimensions": sum(bool(r["dimensions"]["vehicle_dimensions_candidates"]) for r in results),
    "with_variants": sum(bool(r["variants_candidates"]) for r in results),
    "master_modified": False,
    "output": str(OUT)
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print()
print("=" * 75)
print("CONTEXT EXTRACTION V2 SUMMARY")
print("Records               :", len(results))
print("With power            :", report["with_power"])
print("With torque           :", report["with_torque"])
print("With displacement     :", report["with_displacement"])
print("With transmission     :", report["with_transmission"])
print("With dimensions       :", report["with_dimensions"])
print("With variants         :", report["with_variants"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
print("JSON VALID")
