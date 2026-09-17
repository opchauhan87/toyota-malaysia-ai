#!/usr/bin/env python3

import json
from pathlib import Path

BASE = Path("/opt/toyota-malaysia-ai")

with open(BASE / "data/toyota_merged_candidates.json", encoding="utf-8") as f:
    merged = json.load(f)["records"]

targets = {
    "Vios": [
        "toyota-vios-e-brochure.txt",
        "toyota-vios-hev-e-brochure.txt",
        "toyota-vios-hev-gr-sport-e-brochure.txt",
    ],
    "Yaris Cross": [
        "all-new-yaris-cross-hev-e-brochure.txt",
    ],
    "Camry": [
        "Camry-HEV-Brochure.txt",
        "camry-e-brochure.txt",
    ],
    "Corolla Cross": [
        "corolla-cross-hev-e-brochure.txt",
        "corolla-cross-hev-gr-sport-e-brochure.txt",
    ],
    "Hilux": [
        "hilux-gr-s-rogue-e-brochure.txt",
        "hilux-bev-e-brochure.txt",
    ],
    "Vellfire": [
        "vellfire-alphard-e-brochure.txt",
    ],
    "Hiace": [
        "hiace-e-brochure.txt",
    ],
}

print("TOYOTA VARIANT CONTEXT AUDIT")
print("=" * 100)

for family, files in targets.items():

    print()
    print("=" * 100)
    print("FAMILY:", family)

    for filename in files:

        rows = [
            r for r in merged
            if r.get("source_file") == filename
        ]

        if not rows:
            print()
            print("SOURCE:", filename)
            print("  Candidate record: NONE")
            continue

        for r in rows:

            print()
            print("SOURCE:", filename)
            print("CANDIDATE:", r.get("model_name_candidate"))
            print("PRIORITY:", r.get("source_priority"))

            print()
            print("VARIANT CANDIDATES:")

            for x in r.get("variants_candidates", []):
                print("  -", x)

            print()
            print("POWER CANDIDATES:")
            print(
                " ",
                r.get("technical_specifications", {})
                 .get("power_ps_candidates", [])
            )

            print("TORQUE CANDIDATES:")
            print(
                " ",
                r.get("technical_specifications", {})
                 .get("torque_nm_candidates", [])
            )

            print("DISPLACEMENT CANDIDATES:")
            print(
                " ",
                r.get("technical_specifications", {})
                 .get("displacement_cc_candidates", [])
            )

            print("TRANSMISSION CANDIDATES:")
            print(
                " ",
                r.get("technical_specifications", {})
                 .get("transmission_candidates", [])
            )

            context = (
                r.get("evidence", {})
                 .get("context", {})
            )

            print()
            print("CONTEXT EVIDENCE:")

            for key, vals in context.items():

                if key in [
                    "power",
                    "torque",
                    "engine",
                    "specification",
                    "transmission"
                ]:

                    for value in vals[:5]:
                        print(
                            f"  [{key}]",
                            " ".join(str(value).split())[:1000]
                        )

print()
print("=" * 100)
print("MASTER JSON MODIFIED : NO")
