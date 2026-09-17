#!/usr/bin/env python3

import json
import re
import os
import urllib.request
from datetime import datetime
from html import unescape

BASE = "/opt/toyota-malaysia-ai"

MASTER = f"{BASE}/data/toyota_models.json"
OUTPUT = f"{BASE}/data/toyota_official_catalogue.json"
REPORT = f"{BASE}/reports/toyota_catalogue_collection.json"

URL = "https://www.toyota.com.my/en/online-showroom/explore-config.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/153 Safari/537.36"
    )
}


def clean(text):
    if not text:
        return ""

    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def fetch(url):
    request = urllib.request.Request(
        url,
        headers=HEADERS
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="ignore"
        )


print("=" * 70)
print("TOYOTA MALAYSIA OFFICIAL CATALOGUE COLLECTOR")
print("=" * 70)

try:
    html = fetch(URL)

except Exception as e:
    print()
    print("ERROR: Unable to fetch Toyota Malaysia official catalogue")
    print(str(e))
    raise SystemExit(1)


print(f"Source fetched : {URL}")
print(f"HTML size      : {len(html):,} bytes")


# ---------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------

records = []

# Model URL + surrounding page data.
# Toyota's catalogue is rendered with repeated model-card data.
url_pattern = re.compile(
    r'(https://www\.toyota\.com\.my)?'
    r'(/(?:en/)?models/[^"\']+\.html)',
    re.I
)

found_urls = []

for match in url_pattern.finditer(html):

    relative = match.group(2)

    if relative.startswith("/en/"):
        full = "https://www.toyota.com.my" + relative
    else:
        full = "https://www.toyota.com.my" + relative

    if full not in found_urls:
        found_urls.append(full)


# ---------------------------------------------------------
# Known model names from current master
# ---------------------------------------------------------

with open(MASTER, "r", encoding="utf-8") as f:
    master = json.load(f)

known_models = {
    m.get("model_name", "").strip().lower(): m.get("model_name", "").strip()
    for m in master.get("models", [])
}


# ---------------------------------------------------------
# Build source records
# ---------------------------------------------------------

for url in found_urls:

    model_name = ""

    path = url.split("/models/", 1)[-1]

    path = path.replace(".html", "")

    parts = path.split("/")

    if parts:
        slug = parts[-1]

        slug = slug.replace(
            "-hybrid-electric",
            " HEV"
        )

        slug = slug.replace(
            "-gr-sport",
            " GR Sport"
        )

        slug = slug.replace(
            "-bev",
            " BEV"
        )

        slug = slug.replace(
            "-gr",
            " GR"
        )

        model_name = re.sub(
            r"[-_]+",
            " ",
            slug
        ).strip()

    if not model_name:
        continue

    records.append({
        "model_name_candidate": model_name,
        "official_url": url,
        "source": "Toyota Malaysia Official",
        "collected_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    })


# ---------------------------------------------------------
# Deduplicate
# ---------------------------------------------------------

unique = {}

for record in records:

    key = record["official_url"].lower()

    if key not in unique:
        unique[key] = record


records = list(unique.values())


# ---------------------------------------------------------
# Save
# ---------------------------------------------------------

output = {
    "source": "Toyota Malaysia Official",
    "catalogue_url": URL,
    "collected_at": datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    ),
    "records": records
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
    "source": URL,
    "collected_at": output["collected_at"],
    "html_bytes": len(html),
    "urls_found": len(found_urls),
    "unique_records": len(records),
    "master_models": len(
        master.get("models", [])
    )
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


print()
print("=" * 70)
print("COLLECTION COMPLETE")
print("=" * 70)

print(f"URLs found       : {len(found_urls)}")
print(f"Unique records   : {len(records)}")
print(f"Master models    : {len(master.get('models', []))}")

print()
print(f"Output : {OUTPUT}")
print(f"Report : {REPORT}")

print()
print("JSON VALID")
print("=" * 70)
