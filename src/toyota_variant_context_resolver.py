#!/usr/bin/env python3

import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")

INPUT = BASE / "data/toyota_merged_candidates.json"
REGISTRY = BASE / "data/toyota_shared_source_registry.json"

OUT = BASE / "data/toyota_variant_resolved.json"
REPORT = BASE / "reports/toyota_variant_resolver_report.json"


with open(INPUT, encoding="utf-8") as f:
    merged = json.load(f)["records"]

with open(REGISTRY, encoding="utf-8") as f:
    registry = json.load(f)["records"]


# ------------------------------------------------------------
# CANONICAL FAMILY / VARIANT MAP
# ------------------------------------------------------------

FAMILIES = {
    "Vios": {
        "variants": [
            "Vios 1.5E",
            "Vios 1.5G",
            "Vios 1.5 HEV",
            "Vios 1.5 HEV GR Sport",
        ]
    },

    "Yaris Cross": {
        "variants": [
            "Yaris Cross 1.5S",
            "Yaris Cross 1.5S HEV",
        ]
    },

    "Camry": {
        "variants": [
            "Camry 2.5V",
            "Camry 2.5 HEV",
        ]
    },

    "Corolla Cross": {
        "variants": [
            "Corolla Cross 1.8V",
            "Corolla Cross HEV",
            "Corolla Cross HEV GR Sport",
        ]
    },

    "Hilux": {
        "variants": [
            "Hilux 2.8 GR Sport",
            "Hilux 2.8 Rogue",
            "Hilux 2.4V",
            "Hilux 2.4E",
            "Hilux 2.4E MT",
            "Hilux 2.4 MT",
            "Hilux BEV",
        ]
    },

    "Vellfire": {
        "variants": [
            "Vellfire 2.5 HEV",
            "Vellfire 2.4T",
        ]
    },

    "Hiace": {
        "variants": [
            "Hiace",
            "Hiace SLWB",
        ]
    },
}


# ------------------------------------------------------------
# SOURCE -> FAMILY
# ------------------------------------------------------------

SOURCE_FAMILY = {
    "toyota-vios-e-brochure.txt": "Vios",
    "toyota-vios-hev-e-brochure.txt": "Vios",
    "toyota-vios-hev-gr-sport-e-brochure.txt": "Vios",

    "all-new-yaris-cross-hev-e-brochure.txt": "Yaris Cross",

    "Camry-HEV-Brochure.txt": "Camry",
    "camry-e-brochure.txt": "Camry",

    "corolla-cross-hev-e-brochure.txt": "Corolla Cross",
    "corolla-cross-hev-gr-sport-e-brochure.txt": "Corolla Cross",

    "hilux-gr-s-rogue-e-brochure.txt": "Hilux",
    "hilux-bev-e-brochure.txt": "Hilux",

    "vellfire-alphard-e-brochure.txt": "Vellfire",

    "hiace-e-brochure.txt": "Hiace",
}


def clean(s):
    return " ".join(str(s).split())


def context_text(record):
    evidence = record.get("evidence", {}) or {}
    context = evidence.get("context", {}) or {}

    chunks = []

    for values in context.values():
        if isinstance(values, list):
            for value in values:
                chunks.append(clean(value))
        else:
            chunks.append(clean(values))

    return "\n".join(chunks)


def extract_number(text, pattern):
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    return m.group(1)


def add_field(fields, name, value, evidence, status="VERIFIED"):
    if value is None:
        return

    fields[name] = {
        "value": value,
        "status": status,
        "evidence": clean(evidence)[:1500]
    }


def resolve_vios(record):
    text = context_text(record)
    fields = {}

    # Petrol 1.5 section
    m = re.search(
        r"Displacement cc\s+1,496.*?"
        r"Max\. Output.*?\(\s*106\s*\).*?"
        r"Max\. Torque.*?138",
        text,
        re.I | re.S
    )

    if m:
        add_field(
            fields,
            "engine_displacement_cc",
            1496,
            m.group(0)
        )
        add_field(
            fields,
            "engine_power_ps",
            106,
            m.group(0)
        )
        add_field(
            fields,
            "engine_torque_nm",
            138,
            m.group(0)
        )

    # HEV engine
    m = re.search(
        r"Max\. Output.*?\(\s*91\s*\).*?"
        r"Max\. Torque.*?121",
        text,
        re.I | re.S
    )

    if m:
        add_field(fields, "hev_engine_power_ps", 91, m.group(0))
        add_field(fields, "hev_engine_torque_nm", 121, m.group(0))

    # HEV motor
    m = re.search(
        r"Combined Max\. Output.*?\(\s*111\s*\)",
        text,
        re.I | re.S
    )

    if m:
        add_field(fields, "combined_power_ps", 111, m.group(0))

    return fields


def resolve_yaris_cross(record):
    text = context_text(record)
    fields = {}

    m = re.search(
        r"Engine Power.*?\(\s*106\s*\).*?"
        r"Engine Torque.*?138.*?"
        r"Electric Motor Power.*?\(\s*80\s*\).*?"
        r"Combined Output.*?\(\s*111\s*\)",
        text,
        re.I | re.S
    )

    if m:
        block = m.group(0)
        add_field(fields, "engine_power_ps", 106, block)
        add_field(fields, "engine_torque_nm", 138, block)
        add_field(fields, "motor_power_ps", 80, block)
        add_field(fields, "combined_power_ps", 111, block)

    m = re.search(
        r"Engine Power.*?\(\s*91\s*\).*?"
        r"Engine Torque.*?121",
        text,
        re.I | re.S
    )

    if m:
        block = m.group(0)
        add_field(fields, "engine_power_ps", 91, block)
        add_field(fields, "engine_torque_nm", 121, block)

    return fields


def resolve_camry(record):
    text = context_text(record)
    fields = {}

    m = re.search(
        r"Engine.*?188.*?"
        r"221.*?"
        r"Motor.*?136.*?"
        r"208.*?"
        r"Combined Output.*?230",
        text,
        re.I | re.S
    )

    if m:
        block = m.group(0)

        add_field(fields, "hev_engine_power_ps", 188, block)
        add_field(fields, "hev_engine_torque_nm", 221, block)
        add_field(fields, "motor_power_ps", 136, block)
        add_field(fields, "motor_torque_nm", 208, block)
        add_field(fields, "combined_power_ps", 230, block)

    m = re.search(
        r"2,487.*?"
        r"188.*?"
        r"221",
        text,
        re.I | re.S
    )

    if m:
        add_field(fields, "engine_displacement_cc", 2487, m.group(0))

    m = re.search(
        r"204.*?"
        r"246",
        text,
        re.I | re.S
    )

    if m:
        add_field(fields, "petrol_engine_power_ps", 204, m.group(0))
        add_field(fields, "petrol_engine_torque_nm", 246, m.group(0))

    if re.search(r"E-CVT", text, re.I):
        add_field(fields, "hev_transmission", "E-CVT", "TRANSMISSION E-CVT")

    if re.search(r"8-speed Automatic", text, re.I):
        add_field(
            fields,
            "petrol_transmission",
            "8-speed Automatic",
            "8-speed Automatic"
        )

    return fields


def resolve_corolla_cross(record):
    text = context_text(record)
    fields = {}

    # Petrol
    m = re.search(
        r"72\s*\(\s*98\s*\).*?"
        r"103\s*\(\s*139\s*\).*?"
        r"142.*?"
        r"172",
        text,
        re.I | re.S
    )

    if m:
        block = m.group(0)
        add_field(fields, "petrol_engine_power_ps", 98, block)
        add_field(fields, "hev_engine_power_ps", 139, block)
        add_field(fields, "petrol_engine_torque_nm", 142, block)
        add_field(fields, "hev_engine_torque_nm", 172, block)

    m = re.search(r"7-speed CVT with Sequential Shiftmatic", text, re.I)

    if m:
        add_field(
            fields,
            "petrol_transmission",
            "7-speed CVT with Sequential Shiftmatic",
            m.group(0)
        )

    return fields


def resolve_corolla_cross_gr(record):
    text = context_text(record)
    fields = {}

    # Only capture values when labels survive OCR.
    patterns = [
        (
            "engine_power_ps",
            r"Max\. Output.*?Engine Only.*?(\d+)\s*PS"
        ),
        (
            "motor_power_ps",
            r"Max\. Output.*?Motor Only.*?(\d+)\s*PS"
        ),
        (
            "engine_torque_nm",
            r"Max\. Torque.*?Engine Only.*?(\d+)\s*Nm"
        ),
        (
            "motor_torque_nm",
            r"Max\. Torque.*?Motor Only.*?(\d+)\s*Nm"
        ),
    ]

    for name, pattern in patterns:
        m = re.search(pattern, text, re.I | re.S)
        if m:
            add_field(fields, name, int(m.group(1)), m.group(0))

    return fields


def resolve_hilux(record):
    text = context_text(record)
    fields = {}

    # 2.8L
    m = re.search(
        r"2,755.*?"
        r"224.*?"
        r"550",
        text,
        re.I | re.S
    )

    if m:
        block = m.group(0)
        add_field(fields, "2.8_engine_displacement_cc", 2755, block)
        add_field(fields, "2.8_engine_power_ps", 224, block)
        add_field(fields, "2.8_engine_torque_nm", 550, block)

    # 2.4 variants
    m = re.search(
        r"2,393.*?"
        r"204.*?"
        r"500.*?"
        r"150.*?"
        r"400",
        text,
        re.I | re.S
    )

    if m:
        block = m.group(0)
        add_field(fields, "2.4_engine_displacement_cc", 2393, block)
        add_field(fields, "2.4_engine_power_ps", [204, 150], block)
        add_field(fields, "2.4_engine_torque_nm", [500, 400], block)

    if re.search(r"6-speed Automatic", text, re.I):
        add_field(fields, "automatic_transmission", "6-speed Automatic",
                  "6-speed Automatic")

    if re.search(r"6-speed Manual", text, re.I):
        add_field(fields, "manual_transmission", "6-speed Manual",
                  "6-speed Manual")

    return fields


def resolve_hilux_bev(record):
    text = context_text(record)
    fields = {}

    m = re.search(
        r"POWER FRONT MOTOR.*?196PS",
        text,
        re.I | re.S
    )

    if m:
        add_field(fields, "motor_power_ps", 196, m.group(0))

    return fields


def resolve_vellfire(record):
    text = context_text(record)
    fields = {}

    # Vellfire HEV
    m = re.search(
        r"2,487.*?"
        r"138\s*\(\s*187\s*\).*?"
        r"233.*?"
        r"134\s*\(\s*182\s*\).*?"
        r"235.*?"
        r"184\s*\(\s*250\s*\)",
        text,
        re.I | re.S
    )

    if m:
        block = m.group(0)
        add_field(fields, "hev_displacement_cc", 2487, block)
        add_field(fields, "hev_engine_power_ps", 187, block)
        add_field(fields, "hev_engine_torque_nm", 233, block)
        add_field(fields, "motor_power_ps", 182, block)
        add_field(fields, "motor_torque_nm", 270,
                  "Max. Torque Nm 270")
        add_field(fields, "combined_power_ps", 250, block)

    # Vellfire petrol/turbo
    m = re.search(
        r"2,393.*?"
        r"205\s*\(\s*278\s*\).*?"
        r"430",
        text,
        re.I | re.S
    )

    if m:
        block = m.group(0)
        add_field(fields, "turbo_displacement_cc", 2393, block)
        add_field(fields, "turbo_engine_power_ps", 278, block)
        add_field(fields, "turbo_engine_torque_nm", 430, block)

    if re.search(r"E-CVT", text, re.I):
        add_field(fields, "hev_transmission", "E-CVT", "E-CVT")

    if re.search(r"7-speed Super CVT-i", text, re.I):
        add_field(
            fields,
            "turbo_transmission",
            "7-speed Super CVT-i with Sports Sequential Shiftmatic",
            "7-speed Super CVT-i with Sports Sequential Shiftmatic"
        )

    return fields


def resolve_hiace(record):
    # Current OCR context does not provide reliable technical values.
    return {}


RESOLVERS = {
    "Vios": resolve_vios,
    "Yaris Cross": resolve_yaris_cross,
    "Camry": resolve_camry,
    "Corolla Cross": resolve_corolla_cross,
    "Hilux": resolve_hilux,
    "Vellfire": resolve_vellfire,
    "Hiace": resolve_hiace,
}


# ------------------------------------------------------------
# PROCESS
# ------------------------------------------------------------

results = []
family_counts = {}

for record in merged:

    source = record.get("source_file")
    family = SOURCE_FAMILY.get(source)

    if not family:
        continue

    resolver = RESOLVERS[family]

    fields = resolver(record)

    if family == "Corolla Cross" and \
       record.get("model_name_candidate") == "Corolla Cross HEV GR Sport":
        fields = resolve_corolla_cross_gr(record)

    result = {
        "family": family,
        "source_file": source,
        "candidate_model": record.get("model_name_candidate"),
        "source_priority": record.get("source_priority"),
        "canonical_variants": FAMILIES[family]["variants"],
        "resolved_fields": fields,
        "resolver_status": "RESOLVED_FIELDS" if fields else "REVIEW_REQUIRED",
        "policy": {
            "master_ready": False,
            "automatic_master_import": False,
            "unknown_fields_must_remain_unknown": True,
            "variant_binding_required": True,
        }
    }

    results.append(result)

    family_counts.setdefault(
        family,
        {
            "records": 0,
            "resolved": 0,
            "review": 0
        }
    )

    family_counts[family]["records"] += 1

    if fields:
        family_counts[family]["resolved"] += 1
    else:
        family_counts[family]["review"] += 1


output = {
    "generated_at": datetime.now().isoformat(),
    "resolver_version": "v1",
    "record_count": len(results),
    "records": results
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)


report = {
    "generated_at": datetime.now().isoformat(),
    "resolver_version": "v1",
    "family_counts": family_counts,
    "record_count": len(results),
    "master_modified": False,
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


print("TOYOTA VARIANT CONTEXT RESOLVER v1")
print("=" * 100)

for family, count in family_counts.items():
    print(
        f"{family:20} "
        f"records={count['records']} "
        f"resolved={count['resolved']} "
        f"review={count['review']}"
    )

print()
print("Output :", OUT)
print("Report :", REPORT)
print("MASTER JSON MODIFIED : NO")
