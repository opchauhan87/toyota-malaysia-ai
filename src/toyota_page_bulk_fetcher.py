#!/usr/bin/env python3

import json
import os
import re
import urllib.request
from datetime import datetime

BASE = "/opt/toyota-malaysia-ai"

INPUT = f"{BASE}/data/toyota_catalogue_details.json"
OUTPUT = f"{BASE}/data/toyota_official_raw_pages.json"
REPORT = f"{BASE}/reports/toyota_page_fetch_report.json"

HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/153 Safari/537.36"
}


def fetch(url):

    req = urllib.request.Request(
        url,
        headers=HEADERS
    )

    with urllib.request.urlopen(
        req,
        timeout=30
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="ignore"
        )


def strip_html(html):

    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S
    )

    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.I | re.S
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


with open(INPUT, "r", encoding="utf-8") as f:
    source = json.load(f)

records = source.get("records", [])

raw_pages = []

success = 0
failed = 0

print("=" * 70)
print("TOYOTA MALAYSIA OFFICIAL PAGE BULK FETCHER")
print("=" * 70)
print(f"Pages to fetch : {len(records)}")
print()

for index, record in enumerate(records, 1):

    name = record.get(
        "model_name",
        "UNKNOWN"
    )

    url = record.get(
        "official_url"
    )

    print(
        f"[{index:02d}/{len(records):02d}] "
        f"{name}"
    )

    if not url:
        print("    ERROR: URL missing")
        failed += 1
        continue

    try:

        html = fetch(url)
        text = strip_html(html)

        raw_pages.append({
            "model_name": name,
            "official_url": url,
            "source": "Toyota Malaysia Official",
            "fetched_at":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            "http_fetch": "SUCCESS",
            "html_length": len(html),
            "text_length": len(text),
            "raw_text": text
        })

        success += 1

        print(
            f"    OK "
            f"(HTML {len(html):,} bytes)"
        )

    except Exception as e:

        raw_pages.append({
            "model_name": name,
            "official_url": url,
            "source": "Toyota Malaysia Official",
            "fetched_at":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            "http_fetch": "FAILED",
            "error": str(e)
        })

        failed += 1

        print(
            f"    FAILED: {e}"
        )


result = {
    "source": "Toyota Malaysia Official",
    "generated_at":
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    "total_pages": len(records),
    "successful": success,
    "failed": failed,
    "pages": raw_pages
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


report = {
    "generated_at": result["generated_at"],
    "total_pages": len(records),
    "successful": success,
    "failed": failed,
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
        indent=2,
        ensure_ascii=False
    )


print()
print("=" * 70)
print("BULK FETCH COMPLETE")
print("=" * 70)
print(f"Total pages : {len(records)}")
print(f"Successful  : {success}")
print(f"Failed      : {failed}")
print()
print(f"Raw data : {OUTPUT}")
print(f"Report   : {REPORT}")
print("=" * 70)
