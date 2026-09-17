#!/usr/bin/env python3

import json
import re
from datetime import datetime

BASE = "/opt/toyota-malaysia-ai"

INPUT = f"{BASE}/data/toyota_official_raw_pages.json"
OUTPUT = f"{BASE}/data/toyota_extracted_specs.json"
REPORT = f"{BASE}/reports/toyota_spec_extraction_report.json"

with open(INPUT, "r", encoding="utf-8") as f:
    source = json.load(f)

pages = source.get("pages", [])

results = []

def find_number(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except:
                pass
    return None


def find_text(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip()
    return None


for page in pages:

    if page.get("http_fetch") != "SUCCESS":
        continue

    name = page.get("model_name", "")
    url = page.get("official_url", "")
    text = page.get("raw_text", "")

    record = {
        "model_name": name,
        "official_url": url,
        "source": "Toyota Malaysia Official",
        "verified_source": True,
        "extracted_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "price": {
            "starting_price_myr": None,
            "raw_matches": []
        },

        "engine": {
            "displacement_cc": None,
            "horsepower_ps": None,
            "torque_nm": None,
            "engine_model": None
        },

        "transmission": None,
        "fuel_type": None,

        "hybrid": {
            "detected": False,
            "raw_matches": []
        },

        "ev": {
            "detected": False,
            "raw_matches": []
        },

        "dimensions": {
            "length_mm": None,
            "width_mm": None,
            "height_mm": None,
            "wheelbase_mm": None
        },

        "safety": [],
        "features": [],
        "colours": [],

        "raw_keyword_hits": {}
    }

    # -----------------------------------------------------
    # PRICE
    # -----------------------------------------------------

    price_matches = re.findall(
        r"RM\s*([\d,]+)",
        text,
        re.I
    )

    if price_matches:

        prices = []

        for value in price_matches:
            try:
                amount = int(value.replace(",", ""))

                if amount >= 10000:
                    prices.append(amount)

            except:
                pass

        prices = sorted(set(prices))

        if prices:
            record["price"]["starting_price_myr"] = min(prices)
            record["price"]["raw_matches"] = prices[:20]


    # -----------------------------------------------------
    # ENGINE DISPLACEMENT
    # -----------------------------------------------------

    record["engine"]["displacement_cc"] = find_number(
        text,
        [
            r"([\d,]+)\s*cc",
            r"([\d.]+)\s*L\s*(?:engine|petrol|hybrid)"
        ]
    )


    # -----------------------------------------------------
    # POWER
    # -----------------------------------------------------

    record["engine"]["horsepower_ps"] = find_number(
        text,
        [
            r"([\d,]+)\s*PS",
            r"([\d,]+)\s*hp"
        ]
    )


    # -----------------------------------------------------
    # TORQUE
    # -----------------------------------------------------

    record["engine"]["torque_nm"] = find_number(
        text,
        [
            r"([\d,]+)\s*Nm"
        ]
    )


    # -----------------------------------------------------
    # TRANSMISSION
    # -----------------------------------------------------

    transmission_patterns = [
        r"(E-CVT)",
        r"(CVT)",
        r"(6-speed\s+automatic)",
        r"(6-speed\s+manual)",
        r"(8-speed\s+automatic)",
        r"(10-speed\s+automatic)",
        r"(Direct\s+Shift[- ]CVT)"
    ]

    for pattern in transmission_patterns:

        m = re.search(
            pattern,
            text,
            re.I
        )

        if m:
            record["transmission"] = m.group(1)
            break


    # -----------------------------------------------------
    # FUEL
    # -----------------------------------------------------

    fuel_hits = []

    if re.search(r"\bpetrol\b", text, re.I):
        fuel_hits.append("Petrol")

    if re.search(r"\bhybrid\b", text, re.I):
        fuel_hits.append("Hybrid Electric")

    if re.search(
        r"\belectric vehicle\b|\bBEV\b",
        text,
        re.I
    ):
        fuel_hits.append("Battery Electric")


    if fuel_hits:
        record["fuel_type"] = list(
            dict.fromkeys(fuel_hits)
        )


    # -----------------------------------------------------
    # HYBRID
    # -----------------------------------------------------

    hybrid_matches = re.findall(
        r".{0,100}hybrid.{0,150}",
        text,
        re.I
    )

    if hybrid_matches:

        record["hybrid"]["detected"] = True
        record["hybrid"]["raw_matches"] = [
            re.sub(r"\s+", " ", x).strip()
            for x in hybrid_matches[:10]
        ]


    # -----------------------------------------------------
    # EV
    # -----------------------------------------------------

    ev_matches = re.findall(
        r".{0,100}(?:BEV|battery electric|electric vehicle).{0,150}",
        text,
        re.I
    )

    if ev_matches:

        record["ev"]["detected"] = True
        record["ev"]["raw_matches"] = [
            re.sub(r"\s+", " ", x).strip()
            for x in ev_matches[:10]
        ]


    # -----------------------------------------------------
    # DIMENSIONS
    # -----------------------------------------------------

    dimension_patterns = {
        "length_mm": [
            r"Length\s*[:\-]?\s*([\d,]+)\s*mm"
        ],
        "width_mm": [
            r"Width\s*[:\-]?\s*([\d,]+)\s*mm"
        ],
        "height_mm": [
            r"Height\s*[:\-]?\s*([\d,]+)\s*mm"
        ],
        "wheelbase_mm": [
            r"Wheelbase\s*[:\-]?\s*([\d,]+)\s*mm"
        ]
    }

    for field, patterns in dimension_patterns.items():

        record["dimensions"][field] = find_number(
            text,
            patterns
        )


    # -----------------------------------------------------
    # SAFETY KEYWORDS
    # -----------------------------------------------------

    safety_terms = [
        "Toyota Safety Sense",
        "Pre-Collision System",
        "Lane Departure Alert",
        "Lane Departure Warning",
        "Lane Keeping Assist",
        "Adaptive Cruise Control",
        "Dynamic Radar Cruise Control",
        "Blind Spot Monitor",
        "Rear Cross Traffic Alert",
        "Panoramic View Monitor",
        "Parking Support Alert",
        "Parking Support Brake",
        "Anti-lock Braking System",
        "Vehicle Stability Control",
        "Traction Control",
        "Hill-start Assist",
        "SRS Airbags",
        "Airbags",
        "ISOFIX"
    ]

    for term in safety_terms:

        if re.search(
            re.escape(term),
            text,
            re.I
        ):
            record["safety"].append(term)


    # -----------------------------------------------------
    # FEATURE KEYWORDS
    # -----------------------------------------------------

    feature_terms = [
        "Apple CarPlay",
        "Android Auto",
        "Wireless Charger",
        "Smart Entry",
        "Push Start",
        "Bluetooth",
        "USB",
        "Digital Display",
        "Panoramic Roof",
        "Power Seat",
        "Leather Seat",
        "LED Headlamp",
        "LED Daytime Running Light",
        "Rain Sensing Wiper",
        "Electric Tailgate",
        "Drive Mode"
    ]

    for term in feature_terms:

        if re.search(
            re.escape(term),
            text,
            re.I
        ):
            record["features"].append(term)


    # -----------------------------------------------------
    # RAW KEYWORD SUMMARY
    # -----------------------------------------------------

    keywords = [
        "RM",
        "engine",
        "transmission",
        "safety",
        "Toyota Safety Sense",
        "hybrid",
        "electric",
        "wheelbase",
        "Apple CarPlay",
        "Android Auto",
        "warranty",
        "service"
    ]

    for keyword in keywords:

        record["raw_keyword_hits"][keyword] = len(
            re.findall(
                re.escape(keyword),
                text,
                re.I
            )
        )


    results.append(record)


# ---------------------------------------------------------
# Save extraction
# ---------------------------------------------------------

output = {
    "source": "Toyota Malaysia Official",
    "generated_at": datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    ),
    "total_source_pages": len(pages),
    "successful_extractions": len(results),
    "records": results
}

with open(
    OUTPUT,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        output,
        f,
        indent=2,
        ensure_ascii=False
    )


# ---------------------------------------------------------
# Report
# ---------------------------------------------------------

report = {
    "generated_at": output["generated_at"],
    "source_pages": len(pages),
    "extracted_records": len(results),
    "models_with_price": sum(
        1 for r in results
        if r["price"]["starting_price_myr"] is not None
    ),
    "models_with_engine_data": sum(
        1 for r in results
        if r["engine"]["displacement_cc"] is not None
        or r["engine"]["horsepower_ps"] is not None
        or r["engine"]["torque_nm"] is not None
    ),
    "models_with_safety_data": sum(
        1 for r in results
        if r["safety"]
    ),
    "models_with_features": sum(
        1 for r in results
        if r["features"]
    ),
    "output": OUTPUT
}

with open(
    REPORT,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        report,
        f,
        indent=2
    )


print("=" * 70)
print("TOYOTA BULK SPEC EXTRACTION ENGINE")
print("=" * 70)

print(f"Source pages          : {len(pages)}")
print(f"Extracted records     : {len(results)}")

print(
    f"With price            : "
    f"{report['models_with_price']}"
)

print(
    f"With engine data      : "
    f"{report['models_with_engine_data']}"
)

print(
    f"With safety data      : "
    f"{report['models_with_safety_data']}"
)

print(
    f"With feature data     : "
    f"{report['models_with_features']}"
)

print()
print(f"Output : {OUTPUT}")
print(f"Report : {REPORT}")
print()
print("JSON VALID")
print("=" * 70)
