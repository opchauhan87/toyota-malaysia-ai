#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")
TEXT_DIR = BASE / "data/brochure_ocr"
SOURCE = BASE / "data/toyota_source_prioritized.json"

OUT = BASE / "data/toyota_spec_table_candidates.json"
REPORT = BASE / "reports/toyota_spec_table_extraction_report.json"


def unique(values):
    out = []
    seen = set()

    for v in values:
        v = str(v).strip()
        k = v.lower()
        if v and k not in seen:
            seen.add(k)
            out.append(v)

    return out


def extract_near(text, label, pattern, radius=500):
    results = []

    for m in re.finditer(label, text, re.I):
        block = text[m.start():m.end() + radius]

        for x in re.findall(pattern, block, re.I):
            results.append(x)

    return unique(results)


def power(text):
    values = []

    # Format 1:
    # Max. output PS / rpm 107 / 6,000
    patterns = [
        r"(?:MAX\.?\s*)?(?:OUTPUT|POWER|HORSEPOWER)"
        r"[^\n]{0,120}?\b(\d{2,3})\s*/\s*\d{1,5}",

        # Format 2:
        # 107 PS
        r"\b(\d{2,3})\s*(?:PS|HP|BHP)\b"
    ]

    for pattern in patterns:
        for x in re.findall(pattern, text, re.I):
            n = int(x)
            if 50 <= n <= 600:
                values.append(str(n))

    return unique(values)


def torque(text):
    values = []

    # Format:
    # Max. torque Nm / rpm 140 / 4,200
    patterns = [
        r"(?:MAX\.?\s*)?TORQUE"
        r"[^\n]{0,120}?\b(\d{2,4})\s*/\s*\d{1,5}",

        # Format:
        # 140 Nm
        r"\b(\d{2,4})\s*(?:Nm|N\.m)\b"
    ]

    for pattern in patterns:
        for x in re.findall(pattern, text, re.I):
            n = int(x)
            if 50 <= n <= 900:
                values.append(str(n))

    return unique(values)


def displacement(text):
    values = []

    # Format:
    # Displacement cc (mm) 1,496
    patterns_cc = [
        r"DISPLACEMENT"
        r"[^\n]{0,100}?\b([\d,]{3,7})\b",

        # Format:
        # 1496 cc
        r"\b([\d,]{3,7})\s*(?:cc|cm3)\b"
    ]

    for pattern in patterns_cc:
        for x in re.findall(pattern, text, re.I):
            try:
                n = int(x.replace(",", ""))
                if 600 <= n <= 7000:
                    values.append(str(n))
            except:
                pass

    # Format:
    # 1.5L / 2.8 Litre
    patterns_litre = [
        r"\b(\d(?:\.\d+)?)\s*"
        r"(?:L|LITRE|LITER|LITRES|LITERS)\b"
    ]

    for pattern in patterns_litre:
        for x in re.findall(pattern, text, re.I):
            try:
                n = float(x)
                if 0.6 <= n <= 8:
                    values.append(str(int(round(n * 1000))))
            except:
                pass

    return unique(values)



def dimensions(text):
    results = []

    for m in re.finditer(
        r"\bDIMENSIONS\b|\bMEASUREMENTS\b",
        text,
        re.I
    ):
        block = text[m.start():m.start() + 1800]

        # Normal OCR/table format:
        # 4140 x 1730 x 1475 mm
        for a, b, c in re.findall(
            r"([\d,]{4,5})\s*[x×]\s*"
            r"([\d,]{4,5})\s*[x×]\s*"
            r"([\d,]{4,5})\s*mm",
            block,
            re.I
        ):
            results.append({
                "length_mm": int(a.replace(",", "")),
                "width_mm": int(b.replace(",", "")),
                "height_mm": int(c.replace(",", ""))
            })

        # OCR-separated values:
        # 1,475mm ... 2,550mm ... 1,730mm ... 4,140mm
        nums = re.findall(
            r"\b([\d,]{4,5})\s*mm\b",
            block,
            re.I
        )

        nums = [
            int(x.replace(",", ""))
            for x in nums
            if 1300 <= int(x.replace(",", "")) <= 6000
        ]

        if len(nums) >= 3:
            results.append({
                "raw_candidates_mm": unique(nums)
            })

    return results


def transmission(text):
    results = []

    for m in re.finditer(
        r"(?:TRANSMISSION|Transmission Type)",
        text,
        re.I
    ):
        block = text[m.start():m.start() + 1200]

        patterns = [
            r"\b\d+\s*[- ]\s*speed[^.\n]{0,100}",
            r"\bE-CVT\b",
            r"\bCVT\b",
            r"\bD-CVT\b",
            r"\bAutomatic\b",
            r"\bManual\b"
        ]

        for p in patterns:
            results.extend(re.findall(p, block, re.I))

    return unique(results)


def find_spec_section(text):
    sections = []

    for m in re.finditer(
        r"(?:SPECIFICATIONS|MAIN SPECIFICATIONS)",
        text,
        re.I
    ):
        sections.append(
            text[m.start():m.start() + 5000]
        )

    return sections


print("TOYOTA SPECIFICATION TABLE EXTRACTION ENGINE")
print("=" * 75)

with open(SOURCE, encoding="utf-8") as f:
    source = json.load(f)

records = source.get("records", [])
results = []

for i, record in enumerate(records, 1):

    filename = record.get("source_file")
    path = TEXT_DIR / filename

    if not path.exists():
        continue

    text = path.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    sections = find_spec_section(text)

    # Prefer specification sections; fallback to full OCR.
    spec_text = "\n".join(sections)

    if len(spec_text.strip()) < 100:
        spec_text = text

    p = power(spec_text)
    t = torque(spec_text)
    d = displacement(spec_text)
    tr = transmission(spec_text)
    dm = dimensions(spec_text)

    result = {
        "model_name_candidate": record.get("model_name_candidate"),
        "source_file": filename,
        "source_priority": record.get("source_priority"),
        "source_metadata": record.get("source_metadata", {}),
        "extraction_status": "SPEC_TABLE_CANDIDATE",
        "technical_specifications": {
            "power_ps_candidates": p,
            "torque_nm_candidates": t,
            "displacement_cc_candidates": d,
            "transmission_candidates": tr
        },
        "dimensions": {
            "vehicle_dimensions_candidates": dm
        },
        "spec_section_found": bool(sections),
        "evidence": sections[:3]
    }

    results.append(result)

    print(
        f"[{i:02d}/{len(records)}] "
        f"{str(record.get('model_name_candidate')):32} "
        f"PS={len(p):2d} "
        f"Nm={len(t):2d} "
        f"CC={len(d):2d} "
        f"Trans={len(tr):2d} "
        f"Dim={len(dm):2d}"
    )


output = {
    "generated_at": datetime.now().isoformat(),
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "candidate_only": True,
        "master_import": False,
        "no_hallucination": True
    },
    "total_records": len(results),
    "records": results
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

report = {
    "generated_at": datetime.now().isoformat(),
    "total_records": len(results),
    "with_power": sum(
        bool(x["technical_specifications"]["power_ps_candidates"])
        for x in results
    ),
    "with_torque": sum(
        bool(x["technical_specifications"]["torque_nm_candidates"])
        for x in results
    ),
    "with_displacement": sum(
        bool(x["technical_specifications"]["displacement_cc_candidates"])
        for x in results
    ),
    "with_transmission": sum(
        bool(x["technical_specifications"]["transmission_candidates"])
        for x in results
    ),
    "with_dimensions": sum(
        bool(x["dimensions"]["vehicle_dimensions_candidates"])
        for x in results
    ),
    "with_spec_section": sum(
        x["spec_section_found"]
        for x in results
    ),
    "master_modified": False
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print()
print("=" * 75)
print("SPEC TABLE EXTRACTION SUMMARY")
print("Records               :", report["total_records"])
print("With power            :", report["with_power"])
print("With torque           :", report["with_torque"])
print("With displacement     :", report["with_displacement"])
print("With transmission     :", report["with_transmission"])
print("With dimensions       :", report["with_dimensions"])
print("With spec section     :", report["with_spec_section"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
