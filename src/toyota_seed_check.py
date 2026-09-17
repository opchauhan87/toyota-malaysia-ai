#!/usr/bin/env python3

import json

SEED = "data/toyota_bulk_seed.json"

with open(SEED, "r", encoding="utf-8") as f:
    data = json.load(f)

models = data.get("models", [])

seen = {}
duplicates = []

for m in models:
    name = m.get("model_name", "").strip()

    if not name:
        print("[ERROR] Model without model_name")
        continue

    key = name.lower()

    if key in seen:
        duplicates.append(name)
    else:
        seen[key] = m

print("=" * 60)
print("TOYOTA BULK SEED CHECK")
print("=" * 60)

print(f"Total records : {len(models)}")
print(f"Unique models : {len(seen)}")
print(f"Duplicates    : {len(duplicates)}")

if duplicates:
    print()
    print("DUPLICATES:")
    for x in duplicates:
        print(" -", x)

print()
print("MODELS:")
for name in seen:
    print(" -", seen[name]["model_name"])

print()
print("=" * 60)

if duplicates:
    print("STATUS: NEEDS FIX")
    raise SystemExit(1)

print("STATUS: STRUCTURE OK")
