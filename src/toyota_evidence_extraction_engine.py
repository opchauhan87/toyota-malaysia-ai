#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

MASTER = BASE / "data/toyota_models.json"
REGISTRY = BASE / "data/toyota_shared_source_registry.json"
PRIMARY = BASE / "data/toyota_primary_candidates.json"
OCR_DIR = BASE / "data/brochure_ocr"

OUT = BASE / "data/toyota_evidence_candidates.json"
REPORT = BASE / "reports/toyota_evidence_extraction_report.json"


with open(MASTER, encoding="utf-8") as f:
    master = json.load(f)

with open(REGISTRY, encoding="utf-8") as f:
    registry = json.load(f)

with open(PRIMARY, encoding="utf-8") as f:
    primary = json.load(f)


registry_by_model = {
    r.get("model_name"): r
    for r in registry.get("records", [])
}

primary_by_model = {
    r.get("model_name_candidate"): r
    for r in primary.get("records", [])
}


def read_ocr(filename):
    if not filename:
        return ""

    p = OCR_DIR / filename

    if not p.exists():
        return ""

    return p.read_text(
        encoding="utf-8",
        errors="ignore"
    )


def numbers(pattern, text):
    return re.findall(pattern, text, re.I)


def unique(values):
    out = []
    seen = set()

    for value in values:
        key = str(value).lower()

        if key not in seen:
            seen.add(key)
            out.append(value)

    return out


def extract_power(text):
    patterns = [
        r"(?:MAX\.?\s*OUTPUT|MAX\s+POWER)[^\n]{0,120}?"
        r"(\d{2,3})\s*PS",

        r"(\d{2,3})\s*PS\s*/\s*[\d,\- ]+\s*rpm",

        r"OUTPUT[^\n]{0,80}?(\d{2,3})\s*/\s*[\d,\- ]+\s*PS",
    ]

    values = []

    for p in patterns:
        values.extend(numbers(p, text))

    return unique(values)


def extract_torque(text):
    patterns = [
        r"(?:MAX\.?\s*TORQUE|MAX\s+TORQUE)[^\n]{0,120}?"
        r"(\d{2,3})\s*Nm",

        r"(\d{2,3})\s*Nm\s*/\s*[\d,\- ]+\s*rpm",

        r"TORQUE[^\n]{0,80}?(\d{2,3})\s*/\s*[\d,\- ]+\s*Nm",
    ]

    values = []

    for p in patterns:
        values.extend(numbers(p, text))

    return unique(values)


def extract_displacement(text):
    patterns = [
        r"Displacement\s+cc[^\n]{0,120}?([\d,]{3,5})",

        r"(\d(?:\.\d)?)\s*L(?:ITRE|ITER)?"
        r"(?:\s+(?:ENGINE|TURBO|DOHC|DYNAMIC|PETROL|DIESEL))?",
    ]

    values = []

    for p in patterns:
        values.extend(numbers(p, text))

    # Convert litre values to cc.
    converted = []

    for value in values:

        if "." in value:
            try:
                litre = float(value)
                converted.append(str(int(litre * 1000)))
            except:
                pass
        else:
            converted.append(value.replace(",", ""))

    return unique(converted)


def extract_transmission(text):
    patterns = [
        r"(\d+[- ]speed[^\n]{0,120})",
        r"(Continuously Variable Transmission[^\n]{0,180})",
        r"(Electronic Continuously Variable Transmission[^\n]{0,180})",
        r"(E-CVT[^\n]{0,100})",
        r"(Direct Shift[- ]?CVT[^\n]{0,120})",
        r"(6-speed Automatic[^\n]{0,150})",
        r"(8-speed Automatic[^\n]{0,150})",
        r"(10-speed[^\n]{0,150})",
    ]

    values = []

    for p in patterns:
        values.extend(re.findall(p, text, re.I))

    return unique(
        [" ".join(v.split())[:250] for v in values]
    )


def extract_fuel(text):
    fuel = []

    if re.search(r"\bPETROL\b|\bGASOLINE\b", text, re.I):
        fuel.append("Petrol")

    if re.search(r"\bDIESEL\b", text, re.I):
        fuel.append("Diesel")

    if re.search(r"\bHYBRID ELECTRIC\b|\bHEV\b", text, re.I):
        fuel.append("Hybrid Electric")

    if re.search(r"\bBEV\b|\bBATTERY ELECTRIC\b", text, re.I):
        fuel.append("Battery Electric")

    return unique(fuel)


def extract_battery(text):
    values = []

    patterns = [
        r"(?:Battery Type|Type)\s+([^\n]{0,100}Battery)",
        r"(\d+(?:\.\d+)?)\s*kWh",
        r"(\d+(?:\.\d+)?)\s*Ah",
        r"(\d+(?:\.\d+)?)\s*V(?:oltage)?",
    ]

    for p in patterns:
        values.extend(re.findall(p, text, re.I))

    return unique(
        [" ".join(v.split()) for v in values]
    )


def evidence_snippets(text, terms, limit=5):

    lines = text.splitlines()
    snippets = []

    for i, line in enumerate(lines):

        if not any(
            re.search(re.escape(term), line, re.I)
            for term in terms
        ):
            continue

        start = max(0, i - 2)
        end = min(len(lines), i + 5)

        block = []

        for n in range(start, end):
            clean = " ".join(lines[n].split())

            if clean:
                block.append(clean)

        snippet = " ".join(block)

        if snippet:
            snippets.append(snippet[:1200])

        if len(snippets) >= limit:
            break

    return unique(snippets)


records = []

for model in [
    m.get("model_name")
    for m in master.get("models", [])
]:

    reg = registry_by_model.get(model, {})
    prim = primary_by_model.get(model, {})

    source_file = (
        reg.get("source_file")
        or prim.get("source_file")
    )

    source_type = reg.get(
        "coverage_type",
        "UNKNOWN"
    )

    text = read_ocr(source_file)

    record = {
        "model_name": model,
        "source_type": source_type,
        "source_file": source_file,
        "source_priority": (
            reg.get("source_priority")
            or prim.get("source_priority")
        ),
        "evidence_status": (
            "OCR_AVAILABLE"
            if text
            else "NO_OCR_SOURCE"
        ),
        "technical_candidates": {
            "power_ps": extract_power(text),
            "torque_nm": extract_torque(text),
            "displacement_cc": extract_displacement(text),
            "transmission": extract_transmission(text),
            "fuel_type": extract_fuel(text),
            "battery": extract_battery(text),
        },
        "evidence": {
            "model_terms": evidence_snippets(
                text,
                [model],
                3
            ) if text else [],
            "power": evidence_snippets(
                text,
                ["MAX. OUTPUT", "MAX POWER", "PS"],
                3
            ) if text else [],
            "torque": evidence_snippets(
                text,
                ["MAX. TORQUE", "Nm"],
                3
            ) if text else [],
            "specification": evidence_snippets(
                text,
                ["SPECIFICATIONS", "MAIN SPECIFICATIONS"],
                3
            ) if text else [],
        },
        "policy": {
            "candidate_only": True,
            "price_import": False,
            "master_import": False,
            "variant_inference": False,
            "unknown_allowed": True
        }
    }

    records.append(record)


output = {
    "generated_at": datetime.now().isoformat(),
    "record_count": len(records),
    "records": records
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


summary = {
    "generated_at": datetime.now().isoformat(),
    "master_models": len(records),
    "ocr_available": sum(
        1 for r in records
        if r["evidence_status"] == "OCR_AVAILABLE"
    ),
    "no_ocr_source": sum(
        1 for r in records
        if r["evidence_status"] == "NO_OCR_SOURCE"
    ),
    "with_power_candidates": sum(
        1 for r in records
        if r["technical_candidates"]["power_ps"]
    ),
    "with_torque_candidates": sum(
        1 for r in records
        if r["technical_candidates"]["torque_nm"]
    ),
    "with_displacement_candidates": sum(
        1 for r in records
        if r["technical_candidates"]["displacement_cc"]
    ),
    "with_transmission_candidates": sum(
        1 for r in records
        if r["technical_candidates"]["transmission"]
    ),
    "master_modified": False
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)


print("TOYOTA EVIDENCE EXTRACTION ENGINE")
print("=" * 80)

print("Master models             :", summary["master_models"])
print("OCR available             :", summary["ocr_available"])
print("No OCR source             :", summary["no_ocr_source"])
print("Power candidates          :", summary["with_power_candidates"])
print("Torque candidates         :", summary["with_torque_candidates"])
print("Displacement candidates   :", summary["with_displacement_candidates"])
print("Transmission candidates   :", summary["with_transmission_candidates"])

print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
