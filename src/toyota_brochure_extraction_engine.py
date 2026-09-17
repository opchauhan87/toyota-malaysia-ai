#!/usr/bin/env python3

import json
import re
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")
PDF_DIR = BASE / "data/brochures"
OUT = BASE / "data/toyota_brochure_extracted.json"
REPORT = BASE / "reports/toyota_brochure_extraction_report.json"

OUT.parent.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

print("TOYOTA MALAYSIA BULK BROCHURE EXTRACTION ENGINE")
print("=" * 65)

pdfs = sorted(PDF_DIR.glob("*.pdf"))

print("PDF files found :", len(pdfs))
print()

records = []
success = 0
failed = 0

def clean_text(text):
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_pdf(pdf):
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())

        return clean_text(result.stdout)

    except Exception as e:
        raise RuntimeError(str(e))

def find_first(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.M)
        if m:
            return m.group(1).strip()
    return None

for i, pdf in enumerate(pdfs, 1):

    print(f"[{i:02d}/{len(pdfs)}] {pdf.name}")

    record = {
        "source_file": pdf.name,
        "source_path": str(pdf),
        "source_type": "Toyota Malaysia Official Brochure",
        "extracted_at": datetime.now().isoformat(),
        "status": "FAILED",
        "model_name": None,
        "raw_text_length": 0,
        "technical": {},
        "dimensions": {},
        "safety": {},
        "features": {},
        "warranty": {},
        "colours": {},
        "raw_text": ""
    }

    try:
        text = extract_pdf(pdf)

        record["raw_text_length"] = len(text)

        # Keep full extracted text for the next structured parser.
        record["raw_text"] = text

        # Basic model identification.
        model = find_first(text, [
            r"\b(GR\s*86)\b",
            r"\b(GR\s*Corolla)\b",
            r"\b(GR\s*Yaris)\b",
            r"\b(Corolla Cross)\b",
            r"\b(Hilux)\b",
            r"\b(Corolla)\b",
            r"\b(Vios)\b",
            r"\b(Yaris Cross)\b",
            r"\b(Yaris)\b",
            r"\b(Camry)\b",
            r"\b(Veloz)\b",
            r"\b(Innova Zenix)\b",
            r"\b(Fortuner)\b",
            r"\b(Harrier)\b",
            r"\b(Hiace)\b",
            r"\b(bZ4X)\b",
            r"\b(Urban Cruiser)\b",
            r"\b(Alphard)\b",
            r"\b(Vellfire)\b"
        ])

        record["model_name"] = model

        # Candidate technical information.
        engine_cc = re.findall(
            r"(\d{3,5})\s*(?:cc|CC)",
            text
        )

        power = re.findall(
            r"(\d+(?:\.\d+)?)\s*(?:PS|hp|HP|kW)",
            text
        )

        torque = re.findall(
            r"(\d+(?:\.\d+)?)\s*(?:Nm|N\.m)",
            text
        )

        fuel = re.findall(
            r"(\d+(?:\.\d+)?)\s*(?:L/100km|l/100km|km/L)",
            text,
            re.I
        )

        if engine_cc:
            record["technical"]["engine_cc_candidates"] = sorted(
                set(engine_cc)
            )

        if power:
            record["technical"]["power_candidates"] = sorted(
                set(power)
            )

        if torque:
            record["technical"]["torque_candidates"] = sorted(
                set(torque)
            )

        if fuel:
            record["technical"]["fuel_consumption_candidates"] = sorted(
                set(fuel)
            )

        # Dimensions candidates.
        dimensions = re.findall(
            r"(\d{3,5})\s*[x×]\s*(\d{3,5})\s*[x×]\s*(\d{3,5})\s*mm",
            text,
            re.I
        )

        if dimensions:
            record["dimensions"]["candidates"] = [
                {
                    "length_mm": x[0],
                    "width_mm": x[1],
                    "height_mm": x[2]
                }
                for x in dimensions
            ]

        wheelbase = re.findall(
            r"(?:wheelbase|wheel base)[^\d]{0,30}(\d{3,5})\s*mm",
            text,
            re.I
        )

        if wheelbase:
            record["dimensions"]["wheelbase_candidates"] = sorted(
                set(wheelbase)
            )

        # Safety keyword extraction.
        safety_keywords = [
            "Toyota Safety Sense",
            "Pre-Collision System",
            "PCS",
            "Lane Departure Alert",
            "LDA",
            "Lane Tracing Assist",
            "LTA",
            "Adaptive Cruise Control",
            "Dynamic Radar Cruise Control",
            "Blind Spot Monitor",
            "BSM",
            "Rear Cross Traffic Alert",
            "RCTA",
            "Automatic High Beam",
            "AHB",
            "Vehicle Stability Control",
            "VSC",
            "Traction Control",
            "TRC",
            "Anti-lock Braking System",
            "ABS",
            "Electronic Brake-force Distribution",
            "EBD",
            "Brake Assist",
            "BA",
            "Hill-start Assist",
            "HAC",
            "airbag",
            "ISOFIX"
        ]

        found_safety = []

        lower_text = text.lower()

        for keyword in safety_keywords:
            if keyword.lower() in lower_text:
                found_safety.append(keyword)

        record["safety"]["keywords_found"] = sorted(
            set(found_safety)
        )

        # Feature keyword extraction.
        feature_keywords = [
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
            "360",
            "Parking Sensor",
            "Electronic Parking Brake",
            "Auto Hold",
            "Dual Zone",
            "Automatic Air Conditioning",
            "Power Seat",
            "Leather",
            "LED",
            "Sunroof",
            "Power Tailgate",
            "Head-Up Display"
        ]

        found_features = []

        for keyword in feature_keywords:
            if keyword.lower() in lower_text:
                found_features.append(keyword)

        record["features"]["keywords_found"] = sorted(
            set(found_features)
        )

        # Warranty.
        warranty_matches = re.findall(
            r".{0,100}(?:warranty|warranted).{0,200}",
            text,
            re.I
        )

        if warranty_matches:
            record["warranty"]["text_candidates"] = [
                clean_text(x) for x in warranty_matches[:20]
            ]

        # Colours.
        colour_keywords = [
            "White",
            "Black",
            "Silver",
            "Grey",
            "Gray",
            "Red",
            "Blue",
            "Bronze",
            "Brown",
            "Turquoise",
            "Yellow",
            "Orange"
        ]

        found_colours = []

        for keyword in colour_keywords:
            if re.search(r"\b" + re.escape(keyword) + r"\b", text, re.I):
                found_colours.append(keyword)

        record["colours"]["keyword_candidates"] = sorted(
            set(found_colours)
        )

        record["status"] = "OK"
        success += 1

        print(
            f"        OK | text={len(text):,} chars | "
            f"engine={len(engine_cc)} | "
            f"safety={len(found_safety)} | "
            f"features={len(found_features)}"
        )

    except Exception as e:
        failed += 1
        record["error"] = str(e)
        print("        FAILED:", e)

    records.append(record)

output = {
    "country": "Malaysia",
    "currency": "MYR",
    "source_policy": {
        "primary": "Toyota Malaysia Official",
        "document_type": "Official Model Brochure",
        "values_are_candidates_until_validated": True
    },
    "generated_at": datetime.now().isoformat(),
    "total_pdfs": len(pdfs),
    "successful": success,
    "failed": failed,
    "records": records
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

report = {
    "generated_at": datetime.now().isoformat(),
    "total_pdfs": len(pdfs),
    "successful": success,
    "failed": failed,
    "output": str(OUT),
    "records_with_text": sum(
        1 for r in records if r["raw_text_length"] > 0
    ),
    "records_with_engine_candidates": sum(
        1 for r in records
        if r["technical"].get("engine_cc_candidates")
    ),
    "records_with_safety_candidates": sum(
        1 for r in records
        if r["safety"].get("keywords_found")
    ),
    "records_with_feature_candidates": sum(
        1 for r in records
        if r["features"].get("keywords_found")
    )
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print()
print("=" * 65)
print("EXTRACTION SUMMARY")
print("PDFs found              :", len(pdfs))
print("Successful              :", success)
print("Failed                  :", failed)
print("With text               :", report["records_with_text"])
print("With engine candidates  :", report["records_with_engine_candidates"])
print("With safety candidates  :", report["records_with_safety_candidates"])
print("With feature candidates :", report["records_with_feature_candidates"])
print()
print("Output :", OUT)
print("Report :", REPORT)
print("JSON VALID")
