#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")
TEXT_DIR = BASE / "data/brochure_ocr"
OUT = BASE / "data/toyota_structured_candidates.json"
REPORT = BASE / "reports/toyota_structured_extraction_report.json"

OUT.parent.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

def clean(s):
    return re.sub(r"\s+", " ", s).strip()

def unique(items):
    seen = set()
    out = []
    for x in items:
        x = clean(x)
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out

def matches(text, patterns):
    found = []
    for p in patterns:
        found.extend(re.findall(p, text, re.I))
    return unique(found)

def context_lines(text, keywords, radius=2):
    lines = text.splitlines()
    result = []

    for i, line in enumerate(lines):
        if any(k.lower() in line.lower() for k in keywords):
            start = max(0, i - radius)
            end = min(len(lines), i + radius + 1)
            block = "\n".join(lines[start:end]).strip()
            if block:
                result.append(block)

    return unique(result)

def identify_model(filename, text):
    s = (filename + "\n" + text[:15000]).lower()

    # Most specific first
    rules = [
        ("Corolla Cross HEV GR Sport", ["corolla cross", "gr sport"]),
        ("Corolla Cross HEV", ["corolla cross", "hybrid"]),
        ("Corolla Cross", ["corolla cross"]),
        ("GR Corolla", ["gr corolla"]),
        ("GR Yaris", ["gr yaris"]),
        ("GR86", ["gr86", "gr 86"]),
        ("Vios HEV GR Sport", ["vios", "hev", "gr sport"]),
        ("Vios HEV", ["vios", "hybrid"]),
        ("Vios", ["vios"]),
        ("Yaris Cross HEV", ["yaris cross", "hybrid"]),
        ("Yaris Cross", ["yaris cross"]),
        ("Yaris", ["yaris"]),
        ("Corolla GR Sport", ["corolla", "gr sport"]),
        ("Corolla", ["corolla"]),
        ("Camry HEV", ["camry", "hybrid"]),
        ("Camry", ["camry"]),
        ("Veloz", ["veloz"]),
        ("Innova Zenix", ["innova zenix"]),
        ("Fortuner", ["fortuner"]),
        ("Harrier HEV", ["harrier", "hybrid"]),
        ("Harrier", ["harrier"]),
        ("Hilux BEV", ["hilux", "bev"]),
        ("Hilux GR Sport", ["hilux", "gr sport"]),
        ("Hilux", ["hilux"]),
        ("Hiace SLWB", ["slwb"]),
        ("Hiace", ["hiace"]),
        ("bZ4X", ["bz4x"]),
        ("Urban Cruiser BEV", ["urban cruiser", "bev"]),
        ("Alphard", ["alphard"]),
        ("Vellfire HEV", ["vellfire", "hybrid"]),
        ("Vellfire", ["vellfire"]),
    ]

    for model, required in rules:
        if all(x in s for x in required):
            return model

    return None

def extract_engine(text):
    data = {}

    cc = matches(text, [
        r"\b(\d{3,5})\s*cc\b",
        r"\b(\d\.\d)\s*L\b"
    ])

    ps = matches(text, [
        r"\b(\d+(?:\.\d+)?)\s*PS\b",
        r"\b(\d+(?:\.\d+)?)\s*hp\b"
    ])

    nm = matches(text, [
        r"\b(\d+(?:\.\d+)?)\s*Nm\b",
        r"\b(\d+(?:\.\d+)?)\s*N\.m\b"
    ])

    if cc:
        data["displacement_candidates"] = cc
    if ps:
        data["power_candidates"] = ps
    if nm:
        data["torque_candidates"] = nm

    transmission = matches(text, [
        r"\b(e-?CVT)\b",
        r"\b(CVT)\b",
        r"\b(automatic transmission)\b",
        r"\b(6-speed automatic)\b",
        r"\b(8-speed automatic)\b",
        r"\b(10-speed automatic)\b",
        r"\b(6-speed manual)\b",
        r"\b(7-speed[^,\n]*)"
    ])

    if transmission:
        data["transmission_candidates"] = transmission

    fuel = matches(text, [
        r"\b(\d+(?:\.\d+)?)\s*L/100km\b",
        r"\b(\d+(?:\.\d+)?)\s*km/L\b"
    ])

    if fuel:
        data["fuel_consumption_candidates"] = fuel

    drive = matches(text, [
        r"\b(FWD)\b",
        r"\b(RWD)\b",
        r"\b(4WD)\b",
        r"\b(AWD)\b"
    ])

    if drive:
        data["drivetrain_candidates"] = drive

    return data

def extract_dimensions(text):
    data = {}

    dims = re.findall(
        r"(\d{3,5})\s*[x×]\s*(\d{3,5})\s*[x×]\s*(\d{3,5})\s*mm",
        text,
        re.I
    )

    if dims:
        data["vehicle_dimensions_candidates"] = [
            {
                "length_mm": int(a),
                "width_mm": int(b),
                "height_mm": int(c)
            }
            for a, b, c in dims
        ]

    wheelbase = matches(text, [
        r"(?:wheelbase|wheel base)[^\d]{0,40}(\d{3,5})\s*mm"
    ])

    if wheelbase:
        data["wheelbase_candidates_mm"] = [
            int(x) for x in wheelbase
        ]

    return data

def extract_safety(text):
    keywords = [
        "Toyota Safety Sense",
        "Pre-Collision System",
        "PCS",
        "Lane Departure Alert",
        "LDA",
        "Lane Tracing Assist",
        "LTA",
        "Dynamic Radar Cruise Control",
        "Adaptive Cruise Control",
        "DRCC",
        "Blind Spot Monitor",
        "BSM",
        "Rear Cross Traffic Alert",
        "RCTA",
        "Automatic High Beam",
        "AHB",
        "Parking Support Brake",
        "Panoramic View Monitor",
        "3D Panoramic View Monitor",
        "Vehicle Stability Control",
        "VSC",
        "Traction Control",
        "TRC",
        "ABS",
        "EBD",
        "Brake Assist",
        "BA",
        "Hill-start Assist Control",
        "HAC",
        "airbags",
        "airbag",
        "ISOFIX",
        "Tyre Pressure Warning System",
        "TPWS"
    ]

    found = [
        k for k in keywords
        if k.lower() in text.lower()
    ]

    return unique(found)

def extract_features(text):
    keywords = [
        "Apple CarPlay",
        "Android Auto",
        "Wireless Charger",
        "Bluetooth",
        "USB",
        "Smart Entry",
        "Push Start",
        "Digital Display",
        "Multi Information Display",
        "Panoramic View Monitor",
        "Parking Sensor",
        "Parking Clearance Sonar",
        "Electronic Parking Brake",
        "Auto Hold",
        "Dual Zone",
        "Automatic Air Conditioning",
        "Power Seat",
        "Leather",
        "LED",
        "Sunroof",
        "Power Tailgate",
        "Head-Up Display",
        "Remote Air Conditioning",
        "Toyota Vios",
        "Toyota VTS"
    ]

    return unique([
        k for k in keywords
        if k.lower() in text.lower()
    ])

def extract_warranty(text):
    blocks = context_lines(
        text,
        ["warranty", "warranted", "unlimited mileage"],
        radius=3
    )
    return blocks[:20]

def extract_variants(text):
    # Capture common Toyota Malaysia variant naming patterns.
    patterns = [
        r"\b\d\.\d[A-Z]\b",
        r"\b\d\.\d[A-Z]+\b",
        r"\bGR Sport\b",
        r"\bHybrid Electric\b",
        r"\bHEV\b",
        r"\bBEV\b",
        r"\bM/T\b",
        r"\bA/T\b"
    ]

    found = []
    for p in patterns:
        found.extend(re.findall(p, text, re.I))

    return unique(found)

print("TOYOTA MALAYSIA STRUCTURED EXTRACTION ENGINE")
print("=" * 70)

files = sorted(TEXT_DIR.glob("*.txt"))

print("Text files found :", len(files))
print()

records = []

for i, file in enumerate(files, 1):

    text = file.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    model = identify_model(file.name, text)

    record = {
        "source_file": file.name,
        "source_type": "Toyota Malaysia Official Brochure",
        "extracted_at": datetime.now().isoformat(),
        "model_name_candidate": model,
        "text_length": len(text),
        "variants_candidates": extract_variants(text),
        "technical_specifications": extract_engine(text),
        "dimensions": extract_dimensions(text),
        "safety_features_candidates": extract_safety(text),
        "feature_candidates": extract_features(text),
        "warranty_candidates": extract_warranty(text),
        "validation_status": "CANDIDATE_ONLY"
    }

    records.append(record)

    print(
        f"[{i:02d}/{len(files)}] "
        f"{file.name} -> "
        f"{model or 'UNKNOWN'} | "
        f"variants={len(record['variants_candidates'])} | "
        f"engine={len(record['technical_specifications'])} | "
        f"safety={len(record['safety_features_candidates'])} | "
        f"features={len(record['feature_candidates'])}"
    )

output = {
    "country": "Malaysia",
    "currency": "MYR",
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "document_type": "Official Brochure OCR/Text",
        "candidate_data_requires_validation": True,
        "unknown_values": None,
        "no_hallucination": True
    },
    "generated_at": datetime.now().isoformat(),
    "total_text_files": len(files),
    "records": records
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

report = {
    "generated_at": datetime.now().isoformat(),
    "total_files": len(files),
    "identified_models": sum(
        1 for r in records
        if r["model_name_candidate"]
    ),
    "unknown_models": sum(
        1 for r in records
        if not r["model_name_candidate"]
    ),
    "records_with_engine_data": sum(
        1 for r in records
        if r["technical_specifications"]
    ),
    "records_with_safety_data": sum(
        1 for r in records
        if r["safety_features_candidates"]
    ),
    "records_with_feature_data": sum(
        1 for r in records
        if r["feature_candidates"]
    ),
    "output": str(OUT)
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print()
print("=" * 70)
print("STRUCTURED EXTRACTION SUMMARY")
print("Text files              :", len(files))
print("Identified models       :", report["identified_models"])
print("Unknown models          :", report["unknown_models"])
print("With engine candidates  :", report["records_with_engine_data"])
print("With safety candidates  :", report["records_with_safety_data"])
print("With feature candidates :", report["records_with_feature_data"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("JSON VALID")
