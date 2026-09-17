#!/usr/bin/env python3

import json
import re
import urllib.request
from urllib.parse import urljoin
from pathlib import Path
from datetime import datetime

BASE = "https://www.toyota.com.my"
URL = BASE + "/en/online-showroom/explore-config.html"

OUT = Path("/opt/toyota-malaysia-ai/data/toyota_brochure_sources.json")

print("TOYOTA MALAYSIA BULK BROCHURE DISCOVERY")
print("=" * 55)

req = urllib.request.Request(
    URL,
    headers={
        "User-Agent": "Mozilla/5.0"
    }
)

with urllib.request.urlopen(req, timeout=30) as r:
    html = r.read().decode("utf-8", errors="ignore")

print("Downloaded HTML :", len(html), "bytes")

# Find brochure PDF paths
pdfs = re.findall(
    r'Brochure:\s*(?:Download Brochure|DOWNLOAD BROCHURE)\s*-\s*([^<\n]+?\.pdf)',
    html,
    flags=re.I
)

# Fallback: catch any Toyota Malaysia brochure PDF
if not pdfs:
    pdfs = re.findall(
        r'(/content/dam/malaysia/model-brochures/[^"\']+?\.pdf)',
        html,
        flags=re.I
    )

results = []

for pdf in pdfs:
    pdf = pdf.strip()

    if not pdf.startswith("http"):
        pdf = urljoin(BASE, pdf)

    if pdf not in [x["brochure_url"] for x in results]:
        results.append({
            "brochure_url": pdf,
            "source": URL,
            "discovered_at": datetime.now().isoformat()
        })

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("Unique brochures :", len(results))
print("Output            :", OUT)
print()

for i, item in enumerate(results, 1):
    print(f"{i:02d}. {item['brochure_url']}")

print()
print("JSON VALID")
