#!/usr/bin/env python3

import json
import re
from datetime import datetime

BASE = "/opt/toyota-malaysia-ai"

INPUT = f"{BASE}/data/toyota_official_catalogue.json"
OUTPUT = f"{BASE}/data/toyota_catalogue_details.json"
REPORT = f"{BASE}/reports/toyota_catalogue_details.json"

with open(INPUT, "r", encoding="utf-8") as f:
    source = json.load(f)

records = source.get("records", [])


def clean(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_name(name):
    name = clean(name)

    replacements = {
        "gr86": "GR86",
        "gr corolla": "GR Corolla",
        "gr yaris": "GR Yaris",
        "bz4x": "bZ4X",
        "urban cruiser": "Urban Cruiser BEV",
        "vios hev gr sport": "Vios HEV GR Sport",
        "vios hev": "Vios HEV",
        "yaris cross hev": "Yaris Cross HEV",
        "corolla hev": "Corolla HEV",
        "corolla gr sport": "Corolla GR Sport",
        "corolla cross hev gr sport": "Corolla Cross HEV GR Sport",
        "corolla cross hev": "Corolla Cross HEV",
        "hilux gr sport": "Hilux GR Sport",
        "hilux bev": "Hilux BEV",
        "zenix hev": "Innova Zenix HEV",
        "zenix": "Innova Zenix",
        "camry hev": "Camry HEV",
        "vellfire hev": "Vellfire HEV",
        "harrier hev": "Harrier HEV",
        "cross gr sport": "Corolla Cross GR Sport"
    }

    key = name.lower()

    return replacements.get(key, name)


output_records = []
seen = set()

for item in records:

    raw_name = clean(
        item.get("model_name_candidate")
    )

    official_url = clean(
        item.get("official_url")
    )

    if not official_url:
        continue

    normalized = normalize_name(raw_name)

    key = (
        normalized.lower(),
        official_url.lower()
    )

    if key in seen:
        continue

    seen.add(key)

    record = {
        "model_name_raw": raw_name,
        "model_name": normalized,
        "official_url": official_url,
        "source": "Toyota Malaysia Official",
        "source_verified": True,
        "collected_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "brochure_url": None,

        "pricing": {
            "starting_price_myr": None,
            "price_basis": None,
            "price_market": None,
            "price_owner_type": None,
            "price_verified": False
        },

        "technical": {
            "engine": None,
            "horsepower_ps": None,
            "torque_nm": None,
            "transmission": None,
            "fuel_type": None,
            "hybrid": None,
            "battery": None
        },

        "features": [],

        "normalization_status": "SOURCE_RECORD"
    }

    output_records.append(record)


result = {
    "source": "Toyota Malaysia Official",
    "generated_at": datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    ),
    "source_records": len(output_records),
    "records": output_records
}

with open(
    OUTPUT,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        result,
        f,
        indent=2,
        ensure_ascii=False
    )


# ---------------------------------------------------------
# Report
# ---------------------------------------------------------

names = {}

for r in output_records:

    name = r["model_name"]

    names.setdefault(name, 0)
    names[name] += 1


report = {
    "generated_at": result["generated_at"],
    "source_records": len(output_records),
    "unique_normalized_names": len(names),
    "multiple_source_pages": {
        name: count
        for name, count in names.items()
        if count > 1
    }
}


with open(
    REPORT,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        report,
        f,
        indent=2,
        ensure_ascii=False
    )


print("=" * 70)
print("TOYOTA CATALOGUE DETAIL NORMALIZER")
print("=" * 70)

print(
    f"Source records          : "
    f"{len(output_records)}"
)

print(
    f"Normalized model names  : "
    f"{len(names)}"
)

print()

for name, count in names.items():

    suffix = (
        f" ({count} official pages)"
        if count > 1 else ""
    )

    print(
        f"- {name}{suffix}"
    )

print()
print(f"Output : {OUTPUT}")
print(f"Report : {REPORT}")
print()
print("JSON VALID")
print("=" * 70)
