#!/usr/bin/env python3

import sys
import re
import urllib.request
from html import unescape

BASE = "https://www.toyota.com.my"

MODEL_URLS = {
    "fortuner": "/en/models/fortuner.html",
    "hilux": "/en/models/hilux.html",
    "vios": "/en/models/vios.html",
    "yaris": "/en/models/yaris.html",
    "yaris cross": "/en/models/yaris-cross.html",
    "corolla": "/en/models/corolla.html",
    "corolla cross": "/en/models/corolla-cross-hybrid-electric.html",
    "camry": "/en/models/camry-hybrid-electric.html",
    "veloz": "/en/models/veloz.html",
    "innova zenix": "/en/models/innova-zenix.html",
    "harrier": "/en/models/harrier-hybrid-electric.html",
    "vellfire": "/en/models/vellfire.html",
    "alphard": "/en/models/alphard.html",
    "hiace": "/en/models/hiace.html",
    "hiace slwb": "/en/models/hiace-slwb.html",
    "gr yaris": "/en/models/gr-yaris.html",
    "gr corolla": "/en/models/gr-corolla.html",
    "gr86": "/en/models/gr86.html",
    "bz4x": "/en/models/bz4x.html",
    "urban cruiser": "/en/models/urban-cruiser.html",
}

ALIASES = {
    "yaris cross": "yaris cross",
    "corolla cross": "corolla cross",
    "innova zenix": "innova zenix",
    "hiace slwb": "hiace slwb",
    "gr corolla": "gr corolla",
    "gr yaris": "gr yaris",
    "urban cruiser": "urban cruiser",
    "fortuner": "fortuner",
    "hilux": "hilux",
    "vios": "vios",
    "yaris": "yaris",
    "corolla": "corolla",
    "camry": "camry",
    "veloz": "veloz",
    "innova": "innova zenix",
    "harrier": "harrier",
    "vellfire": "vellfire",
    "alphard": "alphard",
    "hiace": "hiace",
    "gr86": "gr86",
    "gr 86": "gr86",
    "bz4x": "bz4x",
}

def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0 ToyotaMalaysiaVoiceAI/1.0"
        },
    )

    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8", errors="ignore")

def clean_html(html):
    html = re.sub(
        r"<script.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )
    html = re.sub(
        r"<style.*?</style>",
        " ",
        html,
        flags=re.I | re.S,
    )
    html = re.sub(r"<[^>]+>", " ", html)
    html = unescape(html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def find_model(text):
    t = text.lower()

    for alias in sorted(ALIASES, key=len, reverse=True):
        if alias in t:
            return ALIASES[alias]

    return None

def normalize_question(text):
    t = (text or "").lower()

    replacements = {
        "horse power": "horsepower",
        "fast forward": "horsepower",
        "fast forwards": "horsepower",
        "fast-forward": "horsepower",
        "power": "horsepower",
        "tork": "torque",
        "torgue": "torque",
        "storm": "torque",
        "stom": "torque",
        "talk": "torque",
        "engine cc": "engine displacement",
        "engine size": "engine displacement",
    }

    for old, new in replacements.items():
        t = t.replace(old, new)

    return t

def extract_fortuner_variants(html):
    """
    Toyota Malaysia Fortuner page contains structured
    variant JSON in the HTML.

    Extract only variant blocks where the official page
    itself associates the model name with the specification.
    """

    variants = []

    pattern = re.compile(
        r'"name"\s*:\s*"([^"]*Fortuner[^"]*)"'
        r'.{0,12000}?'
        r'"specs"\s*:\s*\[(.*?)\]',
        re.I | re.S,
    )

    for match in pattern.finditer(html):

        name = match.group(1).strip()
        specs = match.group(2)

        torque = re.search(
            r'"stat"\s*:\s*"([\d,]+)\s*NM',
            specs,
            re.I,
        )

        engine = re.search(
            r'"stat"\s*:\s*"([^"]+)"',
            specs,
            re.I,
        )

        if torque:
            value = torque.group(1).replace(",", "")

            item = {
                "name": name,
                "torque": value,
            }

            if engine:
                item["engine"] = engine.group(1).strip()

            variants.append(item)

    return variants

def answer_fortuner(question, html):

    q = normalize_question(question)

    variants = extract_fortuner_variants(html)

    if not variants:
        return None

    # ---------------------------------------------------------
    # TORQUE
    # ---------------------------------------------------------
    if "torque" in q:

        parts = []

        for v in variants:
            if v.get("torque"):
                parts.append(
                    f"{v['name']} produces "
                    f"{v['torque']} Nm of torque"
                )

        if parts:
            return (
                "According to Toyota Malaysia, "
                + "; ".join(parts)
                + "."
            )

    # ---------------------------------------------------------
    # HORSEPOWER / POWER
    #
    # Toyota's current Fortuner page can contain the engine/
    # variant information in its structured HTML, while the
    # detailed power figure may appear elsewhere on the page.
    # Look around each Fortuner variant block rather than
    # searching the whole page and guessing.
    # ---------------------------------------------------------
    if "horsepower" in q or "power" in q or "ps" in q:

        power_by_variant = []

        # Variant-specific patterns.
        variant_patterns = [
            (
                r'"name"\s*:\s*"([^"]*Fortuner[^"]*)".{0,25000}?'
                r'(?:Max\s*Power|Maximum\s*Power|Max\s*Output|'
                r'Maximum\s*Output)[^0-9]{0,100}'
                r'(\d{2,3})\s*PS',
                re.I | re.S,
            ),
            (
                r'"name"\s*:\s*"([^"]*Fortuner[^"]*)".{0,25000}?'
                r'"stat"\s*:\s*"(\d{2,3})\s*PS',
                re.I | re.S,
            ),
        ]

        for pattern, flags in variant_patterns:

            for match in re.finditer(pattern, html, flags):

                name = match.group(1).strip()
                value = match.group(2)

                item = (name, value)

                if item not in power_by_variant:
                    power_by_variant.append(item)

        if power_by_variant:

            parts = [
                f"{name} produces {value} PS"
                for name, value in power_by_variant
            ]

            return (
                "According to Toyota Malaysia, "
                + "; ".join(parts)
                + "."
            )

        # -----------------------------------------------------
        # Fallback for current Fortuner official page:
        # extract known official "Max Power" / "Max Output"
        # values from the raw Toyota page.
        # -----------------------------------------------------
        values = []

        power_patterns = [
            r'Max\s*Power[^0-9]{0,100}(\d{2,3})\s*PS',
            r'Maximum\s*Power[^0-9]{0,100}(\d{2,3})\s*PS',
            r'Max\s*Output[^0-9]{0,100}(\d{2,3})\s*PS',
            r'Maximum\s*Output[^0-9]{0,100}(\d{2,3})\s*PS',
        ]

        for pattern in power_patterns:

            for match in re.finditer(
                pattern,
                html,
                re.I | re.S,
            ):

                value = match.group(1)

                if value not in values:
                    values.append(value)

        if values:

            return (
                "According to Toyota Malaysia, the "
                "verified Fortuner power figures are "
                + ", ".join(v + " PS" for v in values)
                + "."
            )

    return None

def answer_from_page(model, question, html):

    if model == "fortuner":
        answer = answer_fortuner(question, html)

        if answer:
            return answer

    q = normalize_question(question)

    text = clean_html(html)

    if "torque" in q:

        values = []

        for value in re.findall(
            r"(\d{2,4})\s*NM",
            text,
            re.I,
        ):
            if value not in values:
                values.append(value)

        if values:
            return (
                f"According to Toyota Malaysia, the "
                f"verified torque figures are "
                + ", ".join(v + " Nm" for v in values)
                + "."
            )

    if "horsepower" in q or "power" in q or "ps" in q:

        values = []

        for value in re.findall(
            r"(\d{2,3})\s*PS",
            text,
            re.I,
        ):
            if value not in values:
                values.append(value)

        if values:
            return (
                f"According to Toyota Malaysia, the "
                f"verified power figures are "
                + ", ".join(v + " PS" for v in values)
                + "."
            )

    if "displacement" in q or "engine size" in q:

        values = []

        for value in re.findall(
            r"([\d,]{3,6})\s*cc",
            text,
            re.I,
        ):
            value = value.replace(",", "")

            if value not in values:
                values.append(value)

        if values:
            return (
                f"According to Toyota Malaysia, the "
                f"verified engine displacement figures are "
                + ", ".join(v + " cc" for v in values)
                + "."
            )

    return None

def main():

    if len(sys.argv) < 2:
        print(
            "I'm sorry, but I could not find a verified "
            "answer on the Toyota Malaysia website."
        )
        return

    question = " ".join(sys.argv[1:])

    model = find_model(question)

    if not model:
        print(
            "I'm sorry, but I could not identify the Toyota "
            "model from the question."
        )
        return

    path = MODEL_URLS.get(model)

    if not path:
        print(
            "I'm sorry, but this information is not currently "
            "available from the Toyota Malaysia website."
        )
        return

    try:

        html = fetch(BASE + path)

        answer = answer_from_page(
            model,
            question,
            html,
        )

        if answer:
            print(answer)
        else:
            print(
                "I'm sorry, but I could not find a verified "
                "answer for that question on the Toyota "
                "Malaysia website."
            )

    except Exception:
        print(
            "I'm sorry, but I could not retrieve the verified "
            "information from the Toyota Malaysia website."
        )

if __name__ == "__main__":
    main()
