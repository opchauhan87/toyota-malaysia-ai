#!/usr/bin/env python3

import json
import os
import shutil
from datetime import datetime

BASE = "/opt/toyota-malaysia-ai"
MASTER = os.path.join(BASE, "data/toyota_models.json")
SEED = os.path.join(BASE, "data/toyota_bulk_seed.json")
BACKUP_DIR = os.path.join(BASE, "backups")
REPORT_DIR = os.path.join(BASE, "reports")

os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------------------------------------
# Load master
# ---------------------------------------------------------

if os.path.exists(MASTER):
    with open(MASTER, "r", encoding="utf-8") as f:
        master = json.load(f)
else:
    master = {
        "country": "Malaysia",
        "currency": "MYR",
        "last_updated": "",
        "source_policy": {
            "primary": "Toyota Malaysia Official",
            "secondary": [],
            "price_must_be_verified": True
        },
        "models": []
    }

# ---------------------------------------------------------
# Load seed
# ---------------------------------------------------------

if not os.path.exists(SEED):
    print(f"ERROR: Seed file not found: {SEED}")
    raise SystemExit(1)

with open(SEED, "r", encoding="utf-8") as f:
    seed = json.load(f)

# ---------------------------------------------------------
# Backup before import
# ---------------------------------------------------------

backup_name = (
    "toyota_models.bulk-"
    + datetime.now().strftime("%Y%m%d-%H%M%S")
    + ".json"
)

backup_path = os.path.join(BACKUP_DIR, backup_name)

shutil.copy2(MASTER, backup_path)

print("=" * 60)
print("TOYOTA MALAYSIA BULK IMPORT ENGINE")
print("=" * 60)
print(f"Backup : {backup_path}")
print()

# ---------------------------------------------------------
# Existing model index
# ---------------------------------------------------------

existing = {}

for model in master.get("models", []):
    name = str(model.get("model_name", "")).strip()

    if name:
        existing[name.lower()] = model

added = 0
updated = 0
skipped = 0
duplicates = 0

# ---------------------------------------------------------
# Merge function
# ---------------------------------------------------------

def merge_missing(target, source):
    changed = False

    for key, value in source.items():

        if key == "model_name":
            continue

        if key not in target:
            target[key] = value
            changed = True
            continue

        # Fill empty values only
        if target[key] in ("", None, [], {}):
            if value not in ("", None, [], {}):
                target[key] = value
                changed = True

    return changed


# ---------------------------------------------------------
# Import models
# ---------------------------------------------------------

for incoming in seed.get("models", []):

    model_name = str(
        incoming.get("model_name", "")
    ).strip()

    if not model_name:
        continue

    key = model_name.lower()

    # NEW MODEL
    if key not in existing:

        incoming.setdefault(
            "brand",
            "Toyota"
        )

        incoming.setdefault(
            "market",
            "Malaysia"
        )

        incoming.setdefault(
            "knowledge_status",
            "MODEL_INDEXED"
        )

        incoming.setdefault(
            "last_verified",
            datetime.now().strftime("%Y-%m-%d")
        )

        master["models"].append(incoming)
        existing[key] = incoming

        added += 1

        print(f"[ADD]     {model_name}")

    # EXISTING MODEL
    else:

        current = existing[key]

        if merge_missing(current, incoming):
            updated += 1
            print(f"[UPDATE]  {model_name}")
        else:
            skipped += 1
            print(f"[KEEP]    {model_name}")


# ---------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------

seen = set()

for model in master.get("models", []):

    name = str(
        model.get("model_name", "")
    ).strip().lower()

    if not name:
        continue

    if name in seen:
        duplicates += 1

    seen.add(name)


# ---------------------------------------------------------
# Metadata
# ---------------------------------------------------------

master["last_updated"] = datetime.now().strftime("%Y-%m-%d")

master["bulk_import"] = {
    "enabled": True,
    "last_run": NOW,
    "source": "Toyota Malaysia Official",
    "seed_file": "data/toyota_bulk_seed.json",
    "duplicate_protection": True,
    "preserve_existing_data": True
}


# ---------------------------------------------------------
# Save safely
# ---------------------------------------------------------

temp_file = MASTER + ".tmp"

with open(
    temp_file,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        master,
        f,
        indent=2,
        ensure_ascii=False
    )

# Validate generated JSON before replacing master
with open(
    temp_file,
    "r",
    encoding="utf-8"
) as f:

    json.load(f)

os.replace(temp_file, MASTER)


# ---------------------------------------------------------
# Generate report
# ---------------------------------------------------------

status_count = {}

for model in master.get("models", []):

    status = model.get(
        "knowledge_status",
        "NOT_SET"
    )

    status_count[status] = (
        status_count.get(status, 0) + 1
    )


report = {
    "run_at": NOW,
    "models_added": added,
    "models_updated": updated,
    "models_kept": skipped,
    "duplicates": duplicates,
    "total_models": len(master.get("models", [])),
    "status_summary": status_count,
    "json_valid": True
}

report_file = os.path.join(
    REPORT_DIR,
    "bulk_import_latest.json"
)

with open(
    report_file,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        report,
        f,
        indent=2
    )


# ---------------------------------------------------------
# Final output
# ---------------------------------------------------------

print()
print("=" * 60)
print("BULK IMPORT COMPLETE")
print("=" * 60)

print(f"Models added    : {added}")
print(f"Models updated  : {updated}")
print(f"Models kept     : {skipped}")
print(f"Duplicates      : {duplicates}")
print(
    f"Total models    : "
    f"{len(master.get('models', []))}"
)

print()
print("STATUS")
print("-" * 60)

for status, count in sorted(status_count.items()):
    print(f"{status:25} : {count}")

print()
print(f"Master  : {MASTER}")
print(f"Report  : {report_file}")
print(f"Backup  : {backup_path}")
print()
print("JSON VALID")
print("=" * 60)
