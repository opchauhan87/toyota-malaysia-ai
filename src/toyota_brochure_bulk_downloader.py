#!/usr/bin/env python3

import json
import urllib.request
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("/opt/toyota-malaysia-ai")
SOURCE = BASE_DIR / "data/toyota_brochure_sources.json"
OUT_DIR = BASE_DIR / "data/brochures"
REPORT = BASE_DIR / "reports/toyota_brochure_download_report.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

with open(SOURCE, "r", encoding="utf-8") as f:
    sources = json.load(f)

print("TOYOTA MALAYSIA BULK BROCHURE DOWNLOADER")
print("=" * 60)
print("Brochures to download :", len(sources))
print()

results = []

for i, item in enumerate(sources, 1):
    url = item["brochure_url"]
    filename = url.split("/")[-1]

    # Clean URL-encoded names
    filename = filename.replace("%20", "_")

    # Avoid problematic filesystem names
    filename = "".join(
        c if c.isalnum() or c in "._-" else "_"
        for c in filename
    )

    output = OUT_DIR / filename

    result = {
        "url": url,
        "filename": filename,
        "path": str(output),
        "status": "FAILED",
        "size_bytes": 0,
        "downloaded_at": datetime.now().isoformat()
    }

    print(f"[{i:02d}/{len(sources)}] {filename}")

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()

        if not data.startswith(b"%PDF"):
            raise ValueError("Downloaded file is not a valid PDF")

        with open(output, "wb") as f:
            f.write(data)

        result["status"] = "OK"
        result["size_bytes"] = len(data)

        print(f"        OK  {len(data):,} bytes")

    except Exception as e:
        result["error"] = str(e)
        print(f"        FAILED: {e}")

    results.append(result)

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

ok = sum(1 for x in results if x["status"] == "OK")
failed = len(results) - ok

print()
print("=" * 60)
print("DOWNLOAD SUMMARY")
print("Total   :", len(results))
print("Success :", ok)
print("Failed  :", failed)
print()
print("PDF directory :", OUT_DIR)
print("Report        :", REPORT)

if failed == 0:
    print("STATUS        : ALL PDFs DOWNLOADED")
else:
    print("STATUS        : SOME DOWNLOADS FAILED")

print("JSON VALID")
