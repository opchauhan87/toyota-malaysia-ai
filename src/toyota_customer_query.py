#!/usr/bin/env python3

import json
import re
import sys

KB_PATH = "/opt/toyota-malaysia-ai/data/toyota_customer_kb.json"

with open(KB_PATH, encoding="utf-8") as f:
    KB = json.load(f)

UNKNOWN = (
    "I'm sorry, but this information is not currently available "
    "in the verified Toyota Malaysia knowledge base."
)


def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def all_text(obj):
    if isinstance(obj, dict):
        return " ".join(all_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(all_text(v) for v in obj)
    return str(obj)


def model_score(model, question):
    q = norm(question)
    name = norm(model.get("model_name", ""))

    if not name:
        return 0

    score = 0

    if name in q:
        score += 100

    # Useful aliases
    aliases = {
        "camry": ["camry hybrid", "camry hev"],
        "vios": ["vios"],
        "corolla": ["corolla"],
        "corolla cross": ["corolla cross"],
        "gr corolla": ["gr corolla", "corolla gr"],
        "gr yaris": ["gr yaris"],
        "gr86": ["gr86", "gr 86"],
        "yaris cross": ["yaris cross"],
        "hilux": ["hilux"],
        "vellfire": ["vellfire"],
        "alphard": ["alphard"],
        "hiace": ["hiace"],
    }

    for alias in aliases.get(name, []):
        if norm(alias) in q:
            score += 80

    # Search model text for question terms
    for word in set(q.split()):
        if len(word) >= 4 and word in name:
            score += 10

    return score


def find_model(question):
    ranked = []

    for model in KB.get("models", []):
        score = model_score(model, question)

        if score > 0:
            ranked.append((score, model))

    ranked.sort(key=lambda x: x[0], reverse=True)

    return ranked[0][1] if ranked else None


def variant_score(variant, question):
    q = norm(question)

    names = [
        variant.get("variant_name"),
        variant.get("name"),
        variant.get("variant"),
    ]

    score = 0

    for name in names:
        if not name:
            continue

        n = norm(name)

        if n and n in q:
            score += 100

        for word in n.split():
            if len(word) >= 3 and word in q:
                score += 5

    return score


def find_variant(model, question):
    variants = model.get("variants", [])

    ranked = []

    for variant in variants:
        score = variant_score(variant, question)

        if score:
            ranked.append((score, variant))

    ranked.sort(key=lambda x: x[0], reverse=True)

    return ranked[0][1] if ranked else None


def get(data, *keys):
    for key in keys:
        value = data.get(key)

        if value is not None and value != "":
            return value

    return None


def answer_power(data):
    parts = []

    engine = get(
        data,
        "engine_power_ps",
        "hev_engine_power_ps"
    )

    motor = get(data, "motor_power_ps")

    combined = get(data, "combined_power_ps")

    if engine is not None:
        parts.append(f"the engine produces {engine} PS")

    if motor is not None:
        parts.append(f"the electric motor produces {motor} PS")

    if combined is not None:
        parts.append(f"the combined output is {combined} PS")

    if not parts:
        return UNKNOWN

    if len(parts) == 1:
        return parts[0].capitalize() + "."

    return (
        "The " +
        ", ".join(parts[:-1]) +
        ", and " +
        parts[-1] +
        "."
    )


def answer_torque(data):
    engine = get(
        data,
        "engine_torque_nm",
        "hev_engine_torque_nm"
    )

    motor = get(data, "motor_torque_nm")

    parts = []

    if engine is not None:
        parts.append(f"engine torque is {engine} Nm")

    if motor is not None:
        parts.append(f"electric motor torque is {motor} Nm")

    if not parts:
        return UNKNOWN

    return "The " + " and ".join(parts) + "."


def answer_displacement(data):
    cc = get(data, "engine_displacement_cc")

    if cc is None:
        return UNKNOWN

    try:
        litres = float(cc) / 1000
        return (
            f"The engine displacement is {int(cc):,} cc, "
            f"or approximately {litres:.1f} litres."
        )
    except Exception:
        return f"The engine displacement is {cc} cc."


def answer_transmission(data):
    transmission = get(data, "transmission")

    if transmission is None:
        return UNKNOWN

    return f"The transmission is {transmission}."


def answer_price(data):
    price = get(
        data,
        "price",
        "starting_price",
        "selling_price",
        "otr_price"
    )

    if price is None:
        return UNKNOWN

    if isinstance(price, (int, float)):
        return f"The listed price is RM {price:,.2f}."

    return f"The listed price is RM {price}."


def answer_fuel(data):
    fuel = get(data, "fuel_type")

    if fuel is None:
        return UNKNOWN

    return f"The powertrain type is {fuel}."


def answer_general(model, data):
    parts = []

    body = get(data, "body_type")
    fuel = get(data, "fuel_type")

    if body:
        parts.append(f"body type: {body}")

    if fuel:
        parts.append(f"powertrain: {fuel}")

    if not parts:
        return UNKNOWN

    return (
        f"The Toyota {model.get('model_name')} has "
        + " and ".join(parts)
        + "."
    )


def answer_question(question):

    model = find_model(question)

    if not model:
        return (
            "Please tell me which Toyota model you are interested in."
        )

    variant = find_variant(model, question)

    # IMPORTANT:
    # If variant exists, use it.
    # Otherwise use model-level data.
    data = variant if variant else model

    q = norm(question)

    if any(x in q for x in [
        "horsepower",
        "horse power",
        "engine power",
        "power output",
        "how powerful",
        "ps"
    ]):
        return answer_power(data)

    if "torque" in q:
        return answer_torque(data)

    if any(x in q for x in [
        "engine size",
        "engine capacity",
        "engine displacement",
        "displacement",
        "cc",
        "litre engine",
        "liter engine"
    ]):
        return answer_displacement(data)

    if any(x in q for x in [
        "transmission",
        "gearbox",
        "gear box",
        "cvt",
        "e cvt",
        "automatic",
        "manual"
    ]):
        return answer_transmission(data)

    if any(x in q for x in [
        "price",
        "cost",
        "how much",
        "starting price"
    ]):
        return answer_price(data)

    if any(x in q for x in [
        "fuel type",
        "fuel",
        "petrol",
        "diesel",
        "hybrid",
        "electric",
        "ev",
        "bev"
    ]):
        return answer_fuel(data)

    return answer_general(model, data)


if __name__ == "__main__":

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("Customer Question: ").strip()

    print()
    print("Customer :", question)
    print("AI       :", answer_question(question))
    print()
