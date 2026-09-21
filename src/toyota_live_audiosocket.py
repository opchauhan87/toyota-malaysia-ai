from datetime import datetime
from pathlib import Path
#!/usr/bin/env python3

import os
import json
import re
import socket
import struct
import subprocess
import tempfile
import time
import uuid
import wave

from faster_whisper import WhisperModel

HOST = "127.0.0.1"
PORT = 9020

WHISPER_MODEL = "small"
KB_QUERY = "/opt/toyota-malaysia-ai/src/toyota_customer_query.py"

# Telephone audio
SAMPLE_RATE = 8000
BYTES_PER_SAMPLE = 2

# 320-byte AudioSocket frames = 20 ms at 8 kHz / 16-bit mono
FRAME_BYTES = 320

# End a caller speech turn after this much silence.
SILENCE_SECONDS = 0.8

# Ignore very short fragments.
MIN_SPEECH_SECONDS = 0.35

# Basic RMS threshold for telephone PCM.
RMS_THRESHOLD = 450

def get_time_based_greeting():
    hour = time.localtime().tm_hour

    if 5 <= hour < 12:
        period = "morning"
    elif 12 <= hour < 17:
        period = "afternoon"
    else:
        period = "evening"

    return (
        f"Hi, good {period}. I'm calling on behalf of Toyota regarding "
        "our latest car promotion. May I take a few seconds to share "
        "the promotion with you?"
    )



def rms(pcm):
    if not pcm:
        return 0

    count = len(pcm) // 2
    if count == 0:
        return 0

    values = struct.unpack("<%dh" % count, pcm)
    total = sum(x * x for x in values)
    return (total / count) ** 0.5


def recv_exact(conn, size):
    data = b""

    while len(data) < size:
        chunk = conn.recv(size - len(data))

        if not chunk:
            return None

        data += chunk

    return data


def drain_incoming_audio(conn, recording_buffer=None):
    """
    Drain incoming AudioSocket packets while AI is speaking.

    Audio is NOT sent to Whisper, so AI echo cannot become the next
    customer speech turn.

    If recording_buffer is provided, incoming AUDIO payloads are also
    preserved for the complete call recording.
    """

    import select

    try:
        conn.setblocking(False)

        while True:
            ready, _, _ = select.select([conn], [], [], 0)

            if not ready:
                break

            try:
                data = conn.recv(65536)

                if not data:
                    break

                # AudioSocket may return one or more complete packets.
                # Preserve only audio payloads for recording.
                offset = 0

                while offset + 3 <= len(data):
                    packet_type = data[offset]
                    length = struct.unpack(
                        "!H",
                        data[offset + 1:offset + 3]
                    )[0]

                    packet_end = offset + 3 + length

                    if packet_end > len(data):
                        break

                    if packet_type == 0x10 and recording_buffer is not None:
                        recording_buffer.extend(
                            data[offset + 3:packet_end]
                        )

                    offset = packet_end

            except BlockingIOError:
                break

    finally:
        conn.setblocking(True)


def socket_is_alive(conn):
    """
    Check whether the AudioSocket TCP connection is still alive
    without consuming incoming AudioSocket data.

    MSG_PEEK is used so the main AudioSocket packet parser remains
    the only consumer of the socket.
    """
    import select

    try:
        ready, _, _ = select.select([conn], [], [], 0)

        if not ready:
            return True

        data = conn.recv(1, socket.MSG_PEEK)

        if not data:
            print("CUSTOMER HANGUP DETECTED DURING AI PROCESSING")
            return False

        return True

    except BlockingIOError:
        return True

    except (ConnectionResetError, BrokenPipeError, OSError) as exc:
        print(
            "CUSTOMER HANGUP / SOCKET ERROR:",
            repr(exc)
        )
        return False


def send_audio(conn, pcm, recording_buffer=None):
    """
    Send TTS to the caller in real time.

    IMPORTANT:
    Before every audio chunk, verify that the customer is still
    connected. If the customer hangs up, stop immediately.
    """

    offset = 0

    while offset < len(pcm):

        # Customer may have hung up while AI was generating or speaking.
        if not socket_is_alive(conn):
            print("TTS STOPPED: CUSTOMER HUNG UP")
            return False

        # Drain caller audio while AI is speaking.
        drain_incoming_audio(
            conn,
            recording_buffer
        )

        # Check again after draining.
        if not socket_is_alive(conn):
            print("TTS STOPPED AFTER DRAIN: CUSTOMER HUNG UP")
            return False

        chunk = pcm[
            offset:offset + FRAME_BYTES
        ]

        packet = (
            bytes([0x10])
            + struct.pack("!H", len(chunk))
            + chunk
        )

        try:
            conn.sendall(packet)

        except (
            ConnectionResetError,
            BrokenPipeError,
            OSError
        ) as exc:
            print(
                "TTS SEND FAILED - CUSTOMER HUNG UP:",
                repr(exc)
            )
            return False

        offset += len(chunk)

        # 20 ms telephone-audio pacing.
        time.sleep(
            len(chunk) /
            (SAMPLE_RATE * BYTES_PER_SAMPLE)
        )

    # Final connection check.
    if not socket_is_alive(conn):
        print("CUSTOMER HUNG UP AFTER TTS")
        return False

    drain_incoming_audio(
        conn,
        recording_buffer
    )

    return True



def piper_speak(text):
    """
    Uses the first configured PIPER_MODEL.
    Produces 8-kHz mono signed PCM using SoX.
    """

    model = os.environ.get(
        "PIPER_MODEL",
        "/opt/voice-ai/models/piper/en_US-hfc_female-medium.onnx"
    )

    if not model:
        raise RuntimeError(
            "PIPER_MODEL environment variable is not configured"
        )

    if not os.path.exists(model):
        raise RuntimeError(
            "Piper model not found: " + model
        )

    with tempfile.TemporaryDirectory(prefix="toyota-ai-") as td:

        raw_wav = os.path.join(td, "piper.wav")
        telephony_wav = os.path.join(td, "telephone.wav")

        cmd = [
            "/usr/local/bin/piper",
            "--model", model,
            "--output_file", raw_wav,
            "--length_scale", "1.08",
        ]

        subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        subprocess.run(
            [
                "/usr/bin/sox",
                raw_wav,
                "-r", str(SAMPLE_RATE),
                "-c", "1",
                "-b", "16",
                telephony_wav,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        with wave.open(telephony_wav, "rb") as wf:
            return wf.readframes(wf.getnframes())


def ask_toyota_kb(text):
    """
    Temporary live mode:
    Query Toyota Malaysia official website directly.
    Local KB is bypassed for now.
    """

    result = subprocess.run(
        [
            "python3",
            "/opt/toyota-malaysia-ai/src/toyota_online_query.py",
            text,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
    )

    answer = result.stdout.strip()

    if not answer:
        answer = (
            "I'm sorry, but I could not retrieve the "
            "verified information from the Toyota Malaysia website."
        )

    return answer

def transcribe(pcm):
    with tempfile.NamedTemporaryFile(
        prefix="toyota-stt-",
        suffix=".wav",
        delete=False
    ) as f:

        path = f.name

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm)

    try:
        segments, info = WHISPER.transcribe(
            path,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )

        text = " ".join(
            s.text.strip()
            for s in segments
            if s.text.strip()
        ).strip()

        return text

    finally:
        try:
            os.unlink(path)
        except OSError:
            pass




def interpret_customer_language(text, state=None):
    """
    Interpret Hindi / Hinglish / English customer speech.

    Whisper remains the primary STT engine.
    Ollama is used only when the existing fast English/Hinglish
    rules cannot confidently determine the customer's meaning.

    Returns:
        {
            "language": "hi|en|mixed|unknown",
            "english": "...",
            "intent": "positive|negative|callback|whatsapp|agent_call|model|budget|car_type|other"
        }

    Never use this function to generate Toyota facts.
    """

    original = (text or "").strip()

    if not original:
        return {
            "language": "unknown",
            "english": "",
            "intent": "other",
        }

    # ---------------------------------------------------------
    # Fast Hindi / Hinglish rules
    # ---------------------------------------------------------
    t = original.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()

    # DNC
    if any(x in t for x in [
        "phone mat karna",
        "call mat karna",
        "dobara phone mat",
        "dobara call mat",
        "contact mat karna",
        "number hata do",
        "mera number hata do",
        "mujhe call mat",
    ]):
        return {
            "language": "hi",
            "english": "Please do not call or contact me.",
            "intent": "negative",
        }

    # Wrong number
    if any(x in t for x in [
        "galat number",
        "wrong number hai",
        "galat aadmi",
        "galat person",
        "yeh mera number nahi",
        "ye mera number nahi",
    ]):
        return {
            "language": "hi",
            "english": "You have the wrong number.",
            "intent": "negative",
        }

    # Callback
    if any(x in t for x in [
        "abhi busy hoon",
        "abhi busy hu",
        "busy hoon",
        "busy hu",
        "kal phone karna",
        "kal call karna",
        "kal call kar lena",
        "kal phone kar lena",
        "baad mein phone karna",
        "baad mein call karna",
        "baad mein call kar lena",
        "baad me phone karna",
        "baad me call karna",
        "abhi nahi",
        "abhi nahin",
    ]):
        return {
            "language": "hi",
            "english": "I am busy right now. Please call me later.",
            "intent": "callback",
        }

    # WhatsApp
    if any(x in t for x in [
        "whatsapp pe",
        "whatsapp par",
        "whatsapp me",
        "whatsapp kar do",
        "whatsapp bhej do",
        "whatsapp pe bhejo",
        "whatsapp par bhejo",
        "whatsapp pe details",
        "whatsapp par details",
    ]):
        return {
            "language": "mixed",
            "english": "Please send the details to me on WhatsApp.",
            "intent": "whatsapp",
        }

    # Agent call
    if any(x in t for x in [
        "agent se baat",
        "agent se baat karni",
        "agent ka phone",
        "agent ka call",
        "agent call kare",
        "kisi agent ka call",
        "mujhe call karwa do",
        "mujhe phone karwa do",
    ]):
        return {
            "language": "hi",
            "english": "Please have an agent call me.",
            "intent": "agent_call",
        }

    # Negative
    if any(x in t for x in [
        "interest nahi hai",
        "interested nahi hoon",
        "interested nahi hu",
        "mujhe interest nahi",
        "mujhe nahi chahiye",
        "mujhe car nahi chahiye",
        "car nahi chahiye",
        "toyota nahi chahiye",
        "nahi lena",
        "nahi leni",
        "nahi lena hai",
        "mujhe nahi lena",
        "abhi nahi lena",
        "koi interest nahi",
        "interest nahin hai",
        "nahi bhai",
        "nahi ji",
    ]):
        return {
            "language": "hi",
            "english": "I am not interested.",
            "intent": "negative",
        }

    # Positive
    if any(x in t for x in [
        "haan",
        "haan ji",
        "ji haan",
        "bilkul",
        "theek hai",
        "thik hai",
        "bataiye",
        "batao",
        "zaroor",
        "ji zaroor",
        "haan bataiye",
        "haan batao",
        "aur bataiye",
        "details bataiye",
        "details batao",
    ]):
        return {
            "language": "hi",
            "english": "Yes, please tell me more.",
            "intent": "positive",
        }

    # ---------------------------------------------------------
    # Existing English should not be sent to Ollama unnecessarily.
    # ---------------------------------------------------------
    english_words = re.findall(r"[a-z]+", t)
    hindi_markers = [
        "haan", "hai", "hoon", "hu", "mujhe", "aap", "aapka",
        "bataiye", "batao", "chahiye", "nahi", "nahin", "karna",
        "kar do", "bhej", "pe", "par", "abhi", "kal", "baad",
        "kitna", "kitne", "kya", "ka", "ki", "ke"
    ]

    has_hindi_marker = any(x in t for x in hindi_markers)

    # If there are no Hindi markers and the text looks like normal
    # English, leave it untouched.
    if english_words and not has_hindi_marker:
        return {
            "language": "en",
            "english": original,
            "intent": "other",
        }

    # ---------------------------------------------------------
    # Ambiguous Hindi/Hinglish -> local Ollama
    # ---------------------------------------------------------
    prompt = f"""Return ONLY valid JSON. No markdown. No explanation.

Understand the customer's speech exactly. Preserve who must perform
an action. Never change "call me" into "I will call".

Allowed language values:
hi, en, mixed, unknown

Allowed intent values:
positive, negative, callback, whatsapp, agent_call, model, budget, car_type, other

JSON format:
{{"language":"...","english":"...","intent":"..."}}

Customer speech:
{original}
"""

    try:
        result = subprocess.run(
            [
                "/usr/local/bin/ollama",
                "run",
                "llama3.2:3b",
                prompt,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.5,
        )

        raw = (result.stdout or "").strip()

        # Extract the JSON object even if the model accidentally
        # adds a small amount of surrounding text.
        match = re.search(r"\{.*\}", raw, re.DOTALL)

        if not match:
            raise ValueError("Ollama did not return JSON")

        import json

        data = json.loads(match.group(0))

        language = str(data.get("language") or "unknown").strip().lower()
        english = str(data.get("english") or "").strip()
        intent = str(data.get("intent") or "other").strip().lower()

        if language not in {"hi", "en", "mixed", "unknown"}:
            language = "unknown"

        if intent not in {
            "positive",
            "negative",
            "callback",
            "whatsapp",
            "agent_call",
            "model",
            "budget",
            "car_type",
            "other",
        }:
            intent = "other"

        if not english:
            english = original

        return {
            "language": language,
            "english": english,
            "intent": intent,
        }

    except Exception as exc:
        print("LANGUAGE INTERPRETER FALLBACK:", repr(exc))

        # Never invent a translation when the local interpreter
        # fails. Preserve the original STT text.
        return {
            "language": "unknown",
            "english": original,
            "intent": "other",
        }


def is_yes(text):
    # Normalize punctuation so Whisper output such as
    # "Yes.", "Yes!", "Yeah.", etc. is handled correctly.
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9\\s']", " ", t)
    t = re.sub(r"\\s+", " ", t).strip()

    yes_words = [
        "yes",
        "yeah",
        "yep",
        "sure",
        "okay",
        "ok",
        "go ahead",
        "please",
        "of course",
        "that's fine",
        "thats fine",
    ]

    return any(
        t == x or t.startswith(x + " ")
        for x in yes_words
    )


def get_followup_answer(text):
    """
    Detect customer's preferred contact method.

    Whisper can transcribe WhatsApp in many different ways.
    This function is used only for contact-method detection.
    """

    t = (text or "").lower().strip()

    # Normalize punctuation/apostrophes.
    t = re.sub(r"[^a-z0-9\\s]", " ", t)
    t = re.sub(r"\\s+", " ", t).strip()

    # WhatsApp / common Whisper variations.
    whatsapp_patterns = [
        "whatsapp",
        "whats app",
        "what app",
        "what s app",
        "whats up",
        "what s up",
        "what sup",
        "what sap",
        "wats app",
        "wat app",
        "wat sap",
        "wassup",
        "was sup",
        "was sap",

        # Common Whisper misrecognitions observed in live calls.
        "what s that",
        "whats that",
        "what that",
        "wats that",
        "wat that",
    ]

    if any(pattern in t for pattern in whatsapp_patterns):
        return "WhatsApp"

    # Phone / call variations.
    call_patterns = [
        "call",
        "phone",
        "telephone",
        "agent",
        "phone call",
        "call me",
    ]

    if any(pattern in t for pattern in call_patterns):
        return "Call"

    return None





def normalize_toyota_question(text):
    """
    Normalize common Whisper/STT mis-transcriptions before
    sending the question to the Toyota KB.

    Only converts high-confidence automotive phrases.
    It does not invent an answer.
    """

    t = (text or "").strip()

    replacements = {
        # Horsepower / engine power
        "fast forward": "horsepower",
        "fast forwards": "horsepower",
        "fast forward does": "horsepower does",
        "how much fast forward": "how much horsepower",
        "how many fast forward": "how much horsepower",
        "horse power": "horsepower",
        "horse powers": "horsepower",

        # Torque
        "talk": "torque",
        "tork": "torque",
        "torgue": "torque",

        # Common engine terms
        "engine cc": "engine displacement",
        "engine size": "engine displacement",

        # WhatsApp should never become a car-question keyword.
        "what s app": "whatsapp",
    }

    normalized = t.lower()

    for old, new in replacements.items():
        normalized = normalized.replace(old, new)

    return normalized


def is_toyota_car_question(text):
    """
    Detect whether the customer is asking a Toyota/car-related question.

    This is intentionally broad because customers may ask about:
    price, power, torque, engine, fuel, hybrid, features, safety,
    warranty, dimensions, variants, availability, etc.
    """

    t = (text or "").lower().strip()

    if not t:
        return False

    # Toyota model names.
    model_terms = [
        "vios",
        "yaris",
        "yaris cross",
        "corolla",
        "corolla cross",
        "camry",
        "veloz",
        "innova",
        "innova zenix",
        "fortuner",
        "harrier",
        "hilux",
        "hiace",
        "vellfire",
        "alphard",
        "bz4x",
        "b z 4 x",
        "gr yaris",
        "gr corolla",
        "gr86",
        "urban cruiser",
    ]

    # Common automotive question terms.
    question_terms = [
        "price",
        "how much",
        "cost",
        "power",
        "horsepower",
        "hp",
        "ps",
        "torque",
        "engine",
        "engine size",
        "cc",
        "displacement",
        "fuel",
        "fuel consumption",
        "mileage",
        "hybrid",
        "electric",
        "battery",
        "motor",
        "transmission",
        "automatic",
        "manual",
        "cvt",
        "e cvt",
        "variant",
        "variants",
        "spec",
        "specification",
        "specifications",
        "feature",
        "features",
        "safety",
        "airbag",
        "warranty",
        "dimension",
        "dimensions",
        "length",
        "width",
        "height",
        "wheelbase",
        "boot",
        "seats",
        "seat",
        "available",
        "availability",
        "colour",
        "color",
        "booking",
        "down payment",
        "monthly payment",
        "financing",
        "loan",
        "interest rate",
    ]

    has_model = any(term in t for term in model_terms)
    has_question = (
        "?" in (text or "")
        or any(term in t for term in question_terms)
    )

    # A named Toyota model + normal question wording.
    if has_model and has_question:
        return True

    # Generic car question.
    generic_car_terms = [
        "toyota car",
        "toyota cars",
        "toyota vehicle",
        "toyota vehicles",
        "your car",
        "your cars",
        "which car",
        "which model",
        "what model",
        "car price",
        "car cost",
        "car engine",
        "car warranty",
        "car features",
        "car safety",
        "car specification",
        "car specifications",
    ]

    if any(term in t for term in generic_car_terms):
        return True

    return False


def detect_disposition_signal(state, text):
    """
    Central customer-intent router.

    Priority:
      1. Do Not Contact
      2. Wrong Number
      3. Not Interested
      4. Call Back Later
      5. Positive interest / contact preference
      6. Specific Toyota model

    This runs on every customer speech turn.
    """

    t = (text or "").lower().strip()

    if not t:
        return None

    # Normalize punctuation.
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    # =========================================================
    # DO NOT CONTACT
    # =========================================================
    dnc_phrases = [
        "do not call",
        "dont call",
        "don't call",
        "do not contact",
        "dont contact",
        "don't contact",
        "stop calling",
        "stop call",
        "please stop",
        "please stop calling",
        "please dont call",
        "please don't call",
        "no more calls",
        "no more call",
        "remove my number",
        "remove me",
        "take me off your list",
        "take my number off",
        "do not call this number",
        "dont call this number",
        "don't call this number",
        "never call me",
        "never contact me",
    ]

    if any(x in t for x in dnc_phrases):
        state["do_not_contact"] = True
        state["intent"] = "Not Interested"
        state["disposition"] = "Do Not Contact"
        return "Do Not Contact"

    # =========================================================
    # WRONG NUMBER
    # =========================================================
    wrong_number_phrases = [
        "wrong number",
        "wrong person",
        "you have the wrong number",
        "you called the wrong number",
        "you called the wrong person",
        "not the right person",
        "not the person",
        "not who you are looking for",
        "not who you're looking for",
        "not who you are looking",
        "this is not my number",
        "this isnt my number",
        "this isn't my number",
        "this is the wrong number",
        "you got the wrong person",
        "nobody here is looking for a car",
    ]

    if any(x in t for x in wrong_number_phrases):
        state["wrong_number"] = True
        state["intent"] = "Not Interested"
        state["disposition"] = "Wrong Number"
        return "Wrong Number"

    # =========================================================
    # CLEAR NEGATIVE ANSWER
    # =========================================================
    # A standalone "no" is a clear rejection in this lead flow.
    # More specific phrases such as "no, call me later" are handled
    # by the higher-priority rules above.
    if t in (
        "no",
        "nope",
        "nah",
        "no thanks",
        "no thank you",
    ):
        state["intent"] = "Not Interested"
        state["disposition"] = "Not Interested"
        return "Not Interested"

    # =========================================================
    # NOT INTERESTED
    # =========================================================
    not_interested_phrases = [
        "not interested",
        "no thanks",
        "no thank you",
        "no thank",
        "not interest",
        "no interest",
        "not for me",
        "not for us",
        "i dont want",
        "i don't want",
        "i do not want",
        "do not want",
        "dont want",
        "don't want",
        "i dont need",
        "i don't need",
        "i do not need",
        "dont need",
        "don't need",
        "no car",
        "no vehicle",
        "dont want a car",
        "don't want a car",
        "do not want a car",
        "i dont want a car",
        "i don't want a car",
        "i do not want a car",
        "i dont want car",
        "i don't want car",
        "i do not want car",
        "dont need a car",
        "don't need a car",
        "i dont need a car",
        "i don't need a car",
        "i do not need a car",
        "not looking for a car",
        "not looking for car",
        "not looking to buy",
        "not buying a car",
        "not buying any car",
        "i am not buying a car",
        "im not buying a car",
        "not planning to buy",
        "not planning on buying",
        "not interested in toyota",
        "dont want toyota",
        "don't want toyota",
        "do not want toyota",
        "toyota is not for me",
        "happy with my current car",
        "happy with my car",
        "i already have a car",
        "i already have a vehicle",
        "i am not interested",
        "im not interested",
    ]

    if any(x in t for x in not_interested_phrases):
        state["intent"] = "Not Interested"
        state["disposition"] = "Not Interested"
        return "Not Interested"

    # =========================================================
    # CALL BACK LATER
    # =========================================================
    callback_phrases = [
        "call me later",
        "call back later",
        "call later",
        "contact me later",
        "call me tomorrow",
        "call tomorrow",
        "call back tomorrow",
        "contact me tomorrow",
        "call me next week",
        "call back next week",
        "call me another time",
        "call back another time",
        "contact me another time",
        "not now",
        "not right now",
        "busy right now",
        "i am busy",
        "im busy",
        "i'm busy",
        "busy at the moment",
        "not a good time",
        "this is not a good time",
        "this isnt a good time",
        "this isn't a good time",
        "can you call later",
        "can you call me later",
        "can you call tomorrow",
        "can you call me tomorrow",
        "can you contact me later",
        "call me after work",
        "call after work",
        "call me this evening",
        "call this evening",
        "call me in the evening",
        "call me this afternoon",
        "call this afternoon",
        "call me tonight",
        "call tonight",
        "i am driving",
        "im driving",
        "i'm driving",
        "i am at work",
        "im at work",
        "i'm at work",
    ]

    if any(x in t for x in callback_phrases):
        state["callback_later"] = True
        state["intent"] = "Interested"
        state["disposition"] = "Call Back Later"
        return "Call Back Later"

    # =========================================================
    # WHATSAPP
    # =========================================================
    whatsapp_phrases = [
        "whatsapp",
        "whats app",
        "what app",
        "what s app",
        "whats up",
        "what s up",
        "what sup",
        "what sap",
        "what s that",
        "whats that",
        "what that",
        "wats app",
        "wat app",
        "wat sap",
        "wat s app",
        "wassup",
        "was sup",
        "was sap",
        "send whatsapp",
        "send me whatsapp",
        "send it on whatsapp",
        "send details on whatsapp",
        "message me on whatsapp",
        "whatsapp me",
        "contact me on whatsapp",
    ]

    if any(x in t for x in whatsapp_phrases):
        state["intent"] = "Interested"
        state["contact_preference"] = "WhatsApp"
        return "Interested – WhatsApp"

    # =========================================================
    # AGENT CALL
    # =========================================================
    call_phrases = [
        "call me",
        "give me a call",
        "please call me",
        "phone me",
        "phone call",
        "telephone",
        "agent call",
        "have an agent call",
        "let an agent call",
        "agent contact me",
        "i want a call",
        "i would like a call",
        "id like a call",
        "i'd like a call",
        "speak to an agent",
        "talk to an agent",
        "speak with an agent",
        "talk with an agent",
        "i want to talk agent",
        "i want to talk to agent",
        "i want to talk to an agent",
        "i want to speak agent",
        "i want to speak to agent",
        "i want to speak to an agent",
        "let me talk to agent",
        "let me talk to an agent",
        "let me speak to agent",
        "let me speak to an agent",
        "connect me to agent",
        "connect me to an agent",
        "connect me with an agent",
    ]

    # =========================================================
    # AGENT CALL - STT / FUZZY VARIATIONS
    # =========================================================
    # Whisper may drop or misrecognize words such as "to", "an",
    # or "agent". Handle strong transfer-intent combinations.
    transfer_verbs = (
        "talk",
        "speak",
        "connect",
    )

    transfer_targets = (
        "agent",
        "human",
        "representative",
        "person",
    )

    has_transfer_verb = any(x in t for x in transfer_verbs)
    has_transfer_target = any(x in t for x in transfer_targets)

    if has_transfer_verb and has_transfer_target:
        state["intent"] = "Interested"
        state["contact_preference"] = "Call"
        state["transfer_requested"] = True
        state["transfer_status"] = "requested"
        state["disposition"] = "TTA"
        print("AGENT TRANSFER REQUESTED (FUZZY)")
        return "TTA"

    # Common Whisper transcription variations where "agent"
    # may be incorrectly transcribed as "isn't" / "is not".
    stt_transfer_variations = [
        "i want to talk isnt",
        "i want to talk is not",
        "i want to speak isnt",
        "i want to speak is not",
    ]

    if any(x in t for x in stt_transfer_variations):
        state["intent"] = "Interested"
        state["contact_preference"] = "Call"
        state["transfer_requested"] = True
        state["transfer_status"] = "requested"
        state["disposition"] = "TTA"
        print("AGENT TRANSFER REQUESTED (STT VARIATION)")
        return "TTA"

    if any(x in t for x in call_phrases):
        state["intent"] = "Interested"
        state["contact_preference"] = "Call"
        state["transfer_requested"] = True
        state["transfer_status"] = "requested"
        state["disposition"] = "TTA"
        print("AGENT TRANSFER REQUESTED")
        return "TTA"

    # =========================================================
    # POSITIVE INTEREST
    # =========================================================
    positive_phrases = [
        "interested",
        "i am interested",
        "im interested",
        "i'm interested",
        "yes",
        "yes please",
        "sure",
        "okay",
        "ok",
        "sounds good",
        "tell me more",
        "more information",
        "more details",
        "i want to know more",
        "i would like to know more",
        "id like to know more",
        "i'd like to know more",
        "i want more information",
        "send me the details",
        "i want the details",
        "please explain",
    ]

    if any(x == t or t.startswith(x + " ") for x in positive_phrases):
        state["intent"] = "Interested"

    # =========================================================
    # SPECIFIC TOYOTA MODEL
    # =========================================================
    model_aliases = {
        "vios": "Vios",
        "yaris": "Yaris",
        "yaris cross": "Yaris Cross",
        "corolla": "Corolla",
        "corolla cross": "Corolla Cross",
        "corolla gr": "Corolla GR Sport",
        "camry": "Camry",
        "veloz": "Veloz",
        "innova": "Innova Zenix",
        "innova zenix": "Innova Zenix",
        "fortuner": "Fortuner",
        "harrier": "Harrier",
        "hilux": "Hilux",
        "hiace": "Hiace",
        "vellfire": "Vellfire",
        "alphard": "Alphard",
        "bz4x": "bZ4X",
        "gr yaris": "GR Yaris",
        "gr corolla": "GR Corolla",
        "gr86": "GR86",
        "urban cruiser": "Urban Cruiser",
    }

    for alias, model_name in sorted(
        model_aliases.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if alias in t:
            state["intent"] = "Interested"
            state["preferred_model"] = model_name

            # Do not override an already explicit WhatsApp/Call choice.
            if state.get("contact_preference") == "WhatsApp":
                return "Interested – WhatsApp"

            if state.get("contact_preference") == "Call":
                return "TTA"

            state["disposition"] = "Interested – Specific Model"
            return "Interested – Specific Model"

    return None



def classify_disposition(state):
    """
    Determine final CRM disposition from the completed conversation.
    """

    # CUSTOMER HANGUP ALWAYS WINS.
    # Even if an Interested disposition was detected earlier,
    # a customer hangup means the conversation was not completed.
    if state.get("_customer_hung_up"):
        return "Customer Hang Up"

    # Explicit disposition always wins.
    if state.get("do_not_contact"):
        return "Do Not Contact"

    if state.get("wrong_number"):
        return "Wrong Number"

    if state.get("callback_later"):
        return "Call Back Later"

    if state.get("disposition") in (
        "Not Interested",
        "Wrong Number",
        "Do Not Contact",
        "Call Back Later",
    ):
        return state["disposition"]

    # ---------------------------------------------------------
    # CUSTOMER EXPLICITLY SAID NO
    # ---------------------------------------------------------
    # Check the actual customer speech. A clear negative answer
    # must never fall through to the default Interested status.
    negative_words = {
        "no",
        "nope",
        "nah",
        "not interested",
        "no thanks",
        "no thank you",
        "not now",
        "don't want",
        "do not want",
        "dont want",
    }

    conversation = state.get("conversation") or []

    for entry in reversed(conversation):
        if entry.get("speaker") != "customer":
            continue

        text = (
            entry.get("english_text")
            or entry.get("original_text")
            or ""
        ).strip().lower()

        # Exact negative responses.
        if text in negative_words:
            return "Not Interested"

        # Whisper may add surrounding words/punctuation.
        # Examples:
        #   "here? No."
        #   "No, thank you."
        #   "no thanks"
        # Treat a clear standalone "no" as Not Interested.
        import re

        if re.search(r"\bno\b", text):
            return "Not Interested"

        break

    contact = (
        state.get("final_contact")
        or state.get("contact_preference")
        or ""
    ).lower()

    model = (state.get("preferred_model") or "").strip()

    # WhatsApp preference has priority over model.
    if "whatsapp" in contact:
        return "Interested – WhatsApp"

    # Agent/phone preference.
    if "call" in contact or "phone" in contact:
        return "TTA"

    # Specific model without an explicit contact preference.
    if model:
        return "Interested – Specific Model"

    return "TTA"



def save_call_report(state, call_id, recording_file=None):
    """
    Save completed Toyota AI call report and synchronize
    the final AI disposition with VICIdial.
    """

    import json
    from pathlib import Path

    report_dir = Path("/opt/toyota-malaysia-ai/reports/calls")
    report_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # FINAL AI DISPOSITION
    # ---------------------------------------------------------
    disposition = classify_disposition(state)

    state["disposition"] = disposition

    # Intent must agree with the final disposition.
    if disposition in (
        "Not Interested",
        "Wrong Number",
        "Do Not Contact",
        "Call Back Later",
        "Customer Hang Up",
    ):
        state["intent"] = disposition
    else:
        state["intent"] = "Interested"

    # ---------------------------------------------------------
    # REPORT
    # ---------------------------------------------------------
    from datetime import datetime

    end_time = datetime.now().astimezone()
    state["end_time"] = end_time.isoformat()

    start_time = state.get("start_time")

    duration = None
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time)
            duration = round((end_time - start_dt).total_seconds(), 2)
        except Exception:
            duration = None

    contact_preference = (
        state.get("final_contact")
        or state.get("contact_preference")
    )

    # Customer requirement data only.
    # These values come from what the customer said during the call.
    # Toyota KB answers are intentionally NOT stored here.
    report = {
        "call_id": call_id,
        "lead_id": state.get("lead_id"),
        "phone_number": state.get("phone_number"),
        "first_name": state.get("first_name"),
        "start_time": start_time,
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,

        "conversation_status": state.get(
            "conversation_status",
            "Customer Hang Up"
            if state.get("_customer_hung_up")
            else "Completed"
            if state.get("stage") == "completed"
            else "Conversation Not Done"
        ),

        "intent": state.get("intent"),
        "disposition": disposition,

        "customer_captured_model": state.get(
            "customer_captured_model"
        ),
        "car_type": state.get("car_type"),
        "purchase_type": state.get("purchase_type"),
        "current_car": state.get("current_car"),
        "interested_model": (
            state.get("interested_model")
            or state.get("preferred_model")
        ),
        "budget": state.get("budget"),
        "monthly_payment": state.get("monthly_payment"),
        "purchase_timeline": state.get("purchase_timeline"),
        "callback_time": state.get("callback_time"),
        "contact_preference": contact_preference,
        "customer_language": state.get("customer_language"),

        # Full conversation timeline is retained in the JSON report
        # for the Call Details modal. It is NOT exported to Excel.
        "conversation": state.get("conversation") or [],

        # Internal call data retained in JSON only.
        "recording": recording_file,
        "vicidial_status": state.get("vicidial_status"),
        "vicidial_update": state.get("vicidial_update"),
    }

    # ---------------------------------------------------------
    # BUILD CUSTOMER REQUIREMENT COMMENT FOR VICIDIAL
    # ---------------------------------------------------------
    comment_parts = [
        f"AI: {disposition}"
    ]

    if state.get("customer_captured_model"):
        comment_parts.append(
            f"Customer Model: {state['customer_captured_model']}"
        )

    if state.get("interested_model"):
        comment_parts.append(
            f"Interested Model: {state['interested_model']}"
        )

    if state.get("car_type"):
        comment_parts.append(
            f"Car Type: {state['car_type']}"
        )

    if state.get("purchase_type"):
        comment_parts.append(
            f"Purchase Type: {state['purchase_type']}"
        )

    if state.get("current_car"):
        comment_parts.append(
            f"Current Car: {state['current_car']}"
        )

    if state.get("budget"):
        comment_parts.append(
            f"Budget: {state['budget']}"
        )

    if state.get("monthly_payment"):
        comment_parts.append(
            f"Monthly Payment: {state['monthly_payment']}"
        )

    if state.get("purchase_timeline"):
        comment_parts.append(
            f"Purchase Timeline: {state['purchase_timeline']}"
        )

    if state.get("callback_time"):
        comment_parts.append(
            f"Callback: {state['callback_time']}"
        )

    contact = (
        state.get("final_contact")
        or state.get("contact_preference")
    )

    if contact:
        comment_parts.append(
            f"Contact: {contact}"
        )

    ai_comments = " | ".join(comment_parts)

    report["ai_comments"] = ai_comments

    print("AI COMMENTS:", ai_comments)

    # ---------------------------------------------------------
    # VICIDIAL SYNCHRONIZATION
    # ---------------------------------------------------------
    try:
        from toyota_vicidial import update_lead_status

        lead_id = state.get("lead_id")

        if lead_id:
            vicidial_result = update_lead_status(
                lead_id,
                disposition,
                ai_comments,
            )

            report["vicidial_status"] = vicidial_result.get(
                "vicidial_status"
            )
            report["vicidial_update"] = vicidial_result

            print(
                "VICIDIAL UPDATE:",
                vicidial_result
            )

        else:
            report["vicidial_update"] = {
                "success": False,
                "reason": "missing_lead_id",
            }

            print(
                "VICIDIAL UPDATE: SKIPPED - missing lead_id"
            )

    except Exception as exc:
        report["vicidial_update"] = {
            "success": False,
            "reason": "exception",
            "error": repr(exc),
        }

        print(
            "VICIDIAL UPDATE ERROR:",
            repr(exc)
        )

    # ---------------------------------------------------------
    # SAVE REPORT
    # ---------------------------------------------------------
    filename = report_dir / f"toyota-{call_id}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # ---------------------------------------------------------
    # TOYOTA MYSQL DATABASE
    #
    # JSON remains the local backup/audit copy.
    # MySQL is now the primary structured call store.
    #
    # DB failure must NOT delete or invalidate the JSON report.
    # ---------------------------------------------------------
    try:
        from toyota_db import save_call_to_db

        db_result = save_call_to_db(report)

        report["database_update"] = db_result

        print(
            "TOYOTA DB:",
            db_result
        )

    except Exception as exc:
        report["database_update"] = {
            "success": False,
            "error": repr(exc),
        }

        print(
            "TOYOTA DB SAVE ERROR:",
            repr(exc)
        )

    print("CALL REPORT:", filename)
    print("LEAD ID:", report["lead_id"])
    print("PHONE:", report["phone_number"])
    print("INTENT:", report["intent"])
    print("DISPOSITION:", report["disposition"])
    print("VICIDIAL STATUS:", report["vicidial_status"])

    return str(filename)


def conversation_answer(state, text):
    """
    Deterministic customer requirement capture.

    Customer-facing language remains English.
    Customer requirements are captured from what the customer says.
    Toyota KB is NOT used to populate customer requirement fields.
    """

    t = text.strip()
    lower = t.lower()
    stage = state.get("stage", "permission")

    # --------------------------------------------------------
    # CUSTOMER RESPONDS TO INITIAL GREETING
    # --------------------------------------------------------
    if stage == "permission":

        if is_yes(t):
            return (
                "Great. Would you prefer our agent to call you back, "
                "or would you like us to contact you through WhatsApp?",
                "contact_preference",
            )

        if t:
            state["intent"] = "Interested"

            return (
                "Great. Would you prefer our agent to call you back, "
                "or would you like us to contact you through WhatsApp?",
                "contact_preference",
            )

        return (
            "Sorry, I didn't quite catch that. Would you like me "
            "to share the promotion?",
            "permission",
        )

    # --------------------------------------------------------
    # INITIAL CONTACT PREFERENCE
    # --------------------------------------------------------
    if stage == "contact_preference":

        preference = get_followup_answer(t)

        if preference:
            state["contact_preference"] = preference
            return (
                "Sure. Which Toyota model are you interested in?",
                "model",
            )

        return (
            "Would you prefer a phone call or WhatsApp?",
            "contact_preference",
        )

    # --------------------------------------------------------
    # TOYOTA MODEL
    # --------------------------------------------------------
    if stage == "model":

        state["customer_captured_model"] = t
        state["preferred_model"] = t
        state["interested_model"] = t

        return (
            "What type of car are you looking for, such as a sedan, "
            "SUV or MPV?",
            "car_type",
        )

    # --------------------------------------------------------
    # CAR TYPE
    # --------------------------------------------------------
    if stage == "car_type":

        car_type = None

        car_types = [
            ("suv", "SUV"),
            ("sedan", "Sedan"),
            ("mpv", "MPV"),
            ("hatchback", "Hatchback"),
            ("pickup", "Pickup"),
            ("pick-up", "Pickup"),
            ("4x4", "4x4"),
            ("van", "Van"),
            ("commercial", "Commercial"),
        ]

        for keyword, value in car_types:
            if keyword in lower:
                car_type = value
                break

        if car_type:
            state["car_type"] = car_type
        else:
            # Capture exactly what customer said rather than guessing.
            state["car_type"] = t

        return (
            "Are you looking for a new car, or are you replacing "
            "your current car?",
            "purchase_type",
        )

    # --------------------------------------------------------
    # NEW / REPLACEMENT
    # --------------------------------------------------------
    if stage == "purchase_type":

        if any(x in lower for x in [
            "replace",
            "replacement",
            "old car",
            "current car",
            "existing car",
            "upgrade",
            "upgrading",
            "trade in",
            "trade-in",
        ]):
            state["purchase_type"] = "Replacement"

            return (
                "What car are you currently driving?",
                "current_car",
            )

        if any(x in lower for x in [
            "new",
            "first car",
            "new vehicle",
            "first vehicle",
        ]):
            state["purchase_type"] = "New"

            return (
                "What is your preferred budget?",
                "budget",
            )

        state["purchase_type"] = t

        return (
            "What car are you currently driving?",
            "current_car",
        )

    # --------------------------------------------------------
    # CURRENT CAR
    # --------------------------------------------------------
    if stage == "current_car":

        state["current_car"] = t

        return (
            "What is your preferred budget?",
            "budget",
        )

    # --------------------------------------------------------
    # BUDGET
    # --------------------------------------------------------
    if stage == "budget":

        state["budget"] = t

        return (
            "Do you have a preferred monthly payment?",
            "monthly_payment",
        )

    # --------------------------------------------------------
    # MONTHLY PAYMENT
    # --------------------------------------------------------
    if stage == "monthly_payment":

        state["monthly_payment"] = t

        return (
            "When are you planning to purchase the car?",
            "purchase_timeline",
        )

    # --------------------------------------------------------
    # PURCHASE TIMELINE
    # --------------------------------------------------------
    if stage == "purchase_timeline":

        state["purchase_timeline"] = t

        return (
            "What time would be convenient for our agent to call you?",
            "callback_time",
        )

    # --------------------------------------------------------
    # CALLBACK TIME
    # --------------------------------------------------------
    if stage == "callback_time":

        state["callback_time"] = t

        return (
            "And would you prefer a phone call or WhatsApp?",
            "final_contact",
        )

    # --------------------------------------------------------
    # FINAL CONTACT METHOD
    # --------------------------------------------------------
    if stage == "final_contact":

        preference = get_followup_answer(t)

        if preference:
            state["final_contact"] = preference
            state["contact_preference"] = preference
        else:
            state["final_contact"] = t
            state["contact_preference"] = t

        state["intent"] = "Interested"
        state["conversation_status"] = "Completed"

        return (
            "Thank you. With your permission, our Toyota agent will "
            "contact you to explain the promotion, financing options "
            "and required documentation.",
            "completed",
        )

    # --------------------------------------------------------
    # COMPLETED
    # --------------------------------------------------------
    if stage == "completed":

        return (
            "Thank you for your time. Have a great day.",
            "completed",
        )

    return (
        "Could you please tell me a little more about what you are "
        "looking for?",
        stage,
    )



def update_realtime_call_report(
    state,
    call_id,
    customer_text=None,
    english_text=None,
):
    """
    Add the customer's latest speech to the in-memory conversation
    timeline and refresh the realtime active-call record.

    This is realtime call state only. The completed JSON report is
    written later by save_call_report().
    """
    try:
        conversation = state.setdefault("conversation", [])

        if customer_text:
            conversation.append({
                "speaker": "customer",
                "original_text": customer_text,
                "english_text": english_text or customer_text,
                "timestamp": datetime.now().astimezone().isoformat(),
            })

        # Keep the realtime dashboard synchronized with the latest
        # customer information and conversation state.
        write_active_call(call_id, state)

    except Exception as exc:
        # Reporting must never break the live voice conversation.
        print(
            "REALTIME CUSTOMER REPORT ERROR:",
            repr(exc)
        )


def append_ai_response_to_report(
    state,
    call_id,
    answer,
):
    """
    Add the AI response to the same conversation timeline and
    refresh the realtime active-call record.

    This does not create the final JSON report.
    """
    try:
        conversation = state.setdefault("conversation", [])

        if answer:
            conversation.append({
                "speaker": "ai",
                "original_text": answer,
                "english_text": answer,
                "timestamp": datetime.now().astimezone().isoformat(),
            })

        # Keep the realtime dashboard synchronized after AI response.
        write_active_call(call_id, state)

    except Exception as exc:
        # Reporting must never break the live voice conversation.
        print(
            "REALTIME AI REPORT ERROR:",
            repr(exc)
        )


def process_turn(conn, pcm, state, call_id, customer_recording=None):
    duration = len(pcm) / (SAMPLE_RATE * BYTES_PER_SAMPLE)

    if duration < MIN_SPEECH_SECONDS:
        return False

    print()
    print("-" * 70)
    print(f"Speech turn: {duration:.2f}s")

    try:
        text = transcribe(pcm)

        print("STT:", text)

        if text:
            # Realtime customer transcript.
            # For English speech, the transcript itself is the
            # verified English representation.
            update_realtime_call_report(
                state,
                call_id,
                customer_text=text,
                english_text=text,
            )

        if not text:
            print("No usable speech detected.")
            return False

        # ---------------------------------------------------------
        # Automatic CRM disposition detection
        # ---------------------------------------------------------
        detected_disposition = detect_disposition_signal(state, text)

        if detected_disposition in (
            "Not Interested",
            "Wrong Number",
            "Do Not Contact",
            "Call Back Later",
        ):
            answer = (
                "No problem. Thank you for your time. "
                "Have a great day."
            )

            state["stage"] = "completed"

            print("AUTO INTENT:", state.get("intent"))
            print("AUTO DISPOSITION:", state.get("disposition"))
            print("Answer:", answer)

            ai_pcm = piper_speak(answer)

            if ai_pcm:
                state.setdefault("_ai_recording", bytearray())
                state["_ai_recording"].extend(ai_pcm)
                send_audio(conn, ai_pcm, customer_recording)

            return True

        # ---------------------------------------------------------
        # HUMAN AGENT TRANSFER
        # ---------------------------------------------------------
        if detected_disposition == "TTA":
            state["transfer_requested"] = True
            state["transfer_status"] = "requested"
            state["disposition"] = "TTA"
            state["intent"] = "Interested"

            answer = (
                "Sure, I'll connect you with a Toyota agent now. "
                "Please hold for a moment."
            )

            print("AGENT TRANSFER: REQUESTED")
            print("Answer:", answer)

            append_ai_response_to_report(
                state,
                call_id,
                answer
            )

            audio = piper_speak(answer)

            state.setdefault("_ai_recording", bytearray())
            state["_ai_recording"].extend(audio)

            audio_sent = send_audio(
                conn,
                audio,
                customer_recording
            )

            if not audio_sent:
                state["transfer_status"] = "customer_hung_up"
                state["_customer_hung_up"] = True
                return True

            # Let the final transfer message finish playing.
            time.sleep(0.30)

            # The connection handler will create the transfer signal
            # after this turn returns.
            return True

        # ---------------------------------------------------------
        # Toyota car-question interrupt.
        #
        # Customer can ask a Toyota question at ANY lead stage.
        # Answer from the verified Toyota KB, then return to the
        # exact same lead stage.
        # ---------------------------------------------------------
        if (
            state.get("stage") != "kb"
            and is_toyota_car_question(text)
        ):
            previous_stage = state.get("stage", "permission")

            kb_question = normalize_toyota_question(text)

            print("CAR QUESTION: Yes")
            print("KB QUERY:", kb_question)

            answer = ask_toyota_kb(kb_question)
            print("KB STAGE PRESERVED:", previous_stage)
            print("Answer:", answer)

            # Keep the lead stage unchanged.
            state["stage"] = previous_stage

        # ---------------------------------------------------------
        # Fellow-style lead conversation takes priority.
        # Once the lead conversation is completed, normal Toyota
        # Knowledge Base questions continue to use the KB.
        # ---------------------------------------------------------
        elif state.get("stage") != "kb":

            flow_answer, new_stage = conversation_answer(state, text)

            if flow_answer:
                answer = flow_answer
                state["stage"] = new_stage

                print("FLOW STAGE:", new_stage)
                print("Answer:", answer)

                if state.get("stage") == "completed":
                    print("LEAD DATA:", state)

            else:
                # Conversation flow completed/unknown; move to KB.
                state["stage"] = "kb"
                answer = ask_toyota_kb(text)
                print("Answer:", answer)

        else:
            answer = ask_toyota_kb(text)
            print("Answer:", answer)

        # Save AI response into the same conversation timeline.
        append_ai_response_to_report(
            state,
            call_id,
            answer
        )

        audio = piper_speak(answer)

        print(f"TTS audio: {len(audio)} bytes")

        # Record AI TTS audio for the final two-channel call recording.
        state.setdefault("_ai_recording", bytearray())
        state["_ai_recording"].extend(audio)

        audio_sent = send_audio(
            conn,
            audio,
            customer_recording
        )

        if not audio_sent:
            print("PROCESS TURN STOPPED: CUSTOMER HUNG UP")
            state["_customer_hung_up"] = True
            return True

        # Give the telephone/audio path a short settling period after
        # TTS, then discard residual echo before listening again.
        time.sleep(0.15)
        drain_incoming_audio(conn, customer_recording)

        print("Answer sent to caller.")

        # Tell the connection handler that the conversation is complete.
        if state.get("stage") == "completed":
            return True

        return False

    except (BrokenPipeError, ConnectionResetError) as exc:
        # Customer/Asterisk already disconnected.
        # Never attempt fallback TTS on a dead AudioSocket.
        print(
            "CUSTOMER HANGUP DURING TURN:",
            repr(exc)
        )

        state["_customer_hung_up"] = True
        return True

    except OSError as exc:
        # Errno 104 = Connection reset by peer.
        if getattr(exc, "errno", None) in (32, 104):
            print(
                "CUSTOMER HANGUP DURING TURN:",
                repr(exc)
            )

            state["_customer_hung_up"] = True
            return True

        print("TURN ERROR:", repr(exc))

        try:
            fallback = (
                "I'm sorry, I could not process that question. "
                "Please ask me again."
            )

            send_audio(
                conn,
                piper_speak(fallback),
                customer_recording
            )

        except Exception as tts_exc:
            print(
                "Fallback TTS ERROR:",
                repr(tts_exc)
            )

    except Exception as exc:
        print("TURN ERROR:", repr(exc))

        try:
            fallback = (
                "I'm sorry, I could not process that question. "
                "Please ask me again."
            )

            send_audio(
                conn,
                piper_speak(fallback),
                customer_recording
            )

        except Exception as tts_exc:
            print(
                "Fallback TTS ERROR:",
                repr(tts_exc)
            )



def terminate_audiosocket(conn):
    """
    Tell Asterisk AudioSocket to terminate the session.
    Protocol termination packet = 0x00 0x00 0x00
    """
    try:
        print("Sending AudioSocket termination packet...")
        conn.sendall(b"\x00\x00\x00")
        time.sleep(0.25)
        print("AudioSocket termination packet sent.")
    except Exception as exc:
        print("AudioSocket termination error:", repr(exc))


def save_call_recording(call_id, customer_pcm, ai_pcm):
    """
    Save a two-channel WAV:
      Left  = customer
      Right = AI

    8 kHz / 16-bit PCM.
    """

    import wave
    from pathlib import Path

    out_dir = Path("/opt/toyota-malaysia-ai/recordings")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Always work with immutable bytes.
    customer_pcm = bytes(customer_pcm or b"")
    ai_pcm = bytes(ai_pcm or b"")

    # PCM samples are 2 bytes each.
    # Keep both streams sample-aligned.
    customer_pcm = customer_pcm[:len(customer_pcm) - (len(customer_pcm) % 2)]
    ai_pcm = ai_pcm[:len(ai_pcm) - (len(ai_pcm) % 2)]

    size = max(len(customer_pcm), len(ai_pcm))

    if len(customer_pcm) < size:
        customer_pcm += b"\\x00" * (size - len(customer_pcm))

    if len(ai_pcm) < size:
        ai_pcm += b"\\x00" * (size - len(ai_pcm))

    stereo = bytearray()

    for i in range(0, size, 2):
        stereo += customer_pcm[i:i+2]
        stereo += ai_pcm[i:i+2]

    filename = out_dir / f"toyota-{call_id}.wav"

    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(bytes(stereo))

    print("CALL RECORDING:", filename)

    return str(filename)



def normalize_audiosocket_uuid(payload):
    """
    Convert AudioSocket UUID payload to the canonical UUID string
    used by the Asterisk /run/hnc-ai/<UUID>.lead file.
    """

    import uuid
    import re

    try:
        # AudioSocket UUID is normally 16 raw UUID bytes.
        if len(payload) == 16:
            return str(uuid.UUID(bytes=payload))

        # Support ASCII UUID as well.
        text = payload.decode("ascii", errors="ignore").strip()

        if re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{12}",
            text,
        ):
            return text.lower()

        if re.fullmatch(r"[0-9a-fA-F]{32}", text):
            return str(uuid.UUID(hex=text))

    except Exception as exc:
        print("UUID normalization error:", repr(exc))

    return payload.hex()


def load_vicidial_lead(audiosocket_uuid):
    """
    Load VICIdial lead metadata written by the Asterisk dialplan.

    File format:
      line 1 = lead_id
      line 2 = phone_number
      line 3 = first_name
      line 4 = address1
      line 5 = address2
    """

    from pathlib import Path

    if not audiosocket_uuid:
        return {}

    lead_file = Path(
        f"/run/hnc-ai/{audiosocket_uuid}.lead"
    )

    print(
        "VICIDIAL LEAD LOOKUP:",
        audiosocket_uuid
    )
    print(
        "VICIDIAL LEAD FILE:",
        lead_file
    )

    if not lead_file.exists():
        print(
            "VICIDIAL LEAD FILE NOT FOUND:",
            lead_file
        )

        # Show currently available lead files for debugging.
        try:
            available = sorted(
                str(x)
                for x in Path("/run/hnc-ai").glob("*.lead")
            )
            print(
                "AVAILABLE LEAD FILES:",
                available
            )
        except Exception as exc:
            print(
                "LEAD DIRECTORY DEBUG ERROR:",
                repr(exc)
            )

        return {}

    try:
        lines = lead_file.read_text(
            encoding="utf-8",
            errors="replace"
        ).splitlines()

        values = lines + [""] * (5 - len(lines))

        lead_id = values[0].strip()
        phone_number = values[1].strip()
        first_name = values[2].strip()
        address1 = values[3].strip()
        address2 = values[4].strip()

        data = {
            "audiosocket_uuid": audiosocket_uuid,
            "lead_id": int(lead_id) if lead_id.isdigit() else None,
            "phone_number": phone_number or None,
            "first_name": first_name or None,
            "address1": address1 or None,
            "address2": address2 or None,
        }

        print("VICIDIAL LEAD:", data)

        return data

    except Exception as exc:
        print(
            "VICIDIAL LEAD LOAD ERROR:",
            repr(exc)
        )
        return {}


ACTIVE_CALLS_FILE = Path("/run/toyota-ai/active-calls.json")


def write_active_call(call_id, state):
    """
    Publish the actual AudioSocket-connected call to the reporting UI.
    Only small JSON-safe fields are exposed.
    """
    try:
        ACTIVE_CALLS_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        active = {}

        if ACTIVE_CALLS_FILE.exists():
            try:
                active = json.loads(
                    ACTIVE_CALLS_FILE.read_text(
                        encoding="utf-8"
                    )
                )
            except Exception:
                active = {}

        active[call_id] = {
            "call_id": call_id,
            "audiosocket_uuid": state.get("audiosocket_uuid"),
            "lead_id": state.get("lead_id"),
            "phone_number": state.get("phone_number"),
            "first_name": state.get("first_name"),
            "stage": state.get("stage"),
            "intent": state.get("intent"),
            "disposition": state.get("disposition"),
            "preferred_model": state.get("preferred_model"),
            "car_type": state.get("car_type"),
            "budget": state.get("budget"),
            "callback_time": state.get("callback_time"),
            "contact_preference": state.get("contact_preference"),
            "start_time": state.get("start_time"),
            "last_update": datetime.now().astimezone().isoformat(),
        }

        tmp = ACTIVE_CALLS_FILE.with_suffix(".tmp")

        tmp.write_text(
            json.dumps(
                active,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        tmp.replace(ACTIVE_CALLS_FILE)

    except Exception as exc:
        print(
            "ACTIVE CALL STATE WRITE ERROR:",
            repr(exc)
        )


def remove_active_call(call_id):
    """
    Remove the call immediately when AudioSocket disconnects.
    """
    try:
        active = {}

        if ACTIVE_CALLS_FILE.exists():
            try:
                active = json.loads(
                    ACTIVE_CALLS_FILE.read_text(
                        encoding="utf-8"
                    )
                )
            except Exception:
                active = {}

        active.pop(call_id, None)

        if active:
            tmp = ACTIVE_CALLS_FILE.with_suffix(".tmp")

            tmp.write_text(
                json.dumps(
                    active,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            tmp.replace(ACTIVE_CALLS_FILE)

        else:
            try:
                ACTIVE_CALLS_FILE.unlink()
            except FileNotFoundError:
                pass

    except Exception as exc:
        print(
            "ACTIVE CALL STATE REMOVE ERROR:",
            repr(exc)
        )


def handle_connection(conn, addr):
    print()
    print("=" * 70)
    print("TOYOTA CALL CONNECTED:", addr)
    print("=" * 70)

    # --------------------------------------------------------------
    # POC: LOAD LATEST VICIDIAL LEAD FILE
    #
    # Asterisk creates /run/hnc-ai/<AI_UUID>.lead immediately before
    # AudioSocket() is started. For the POC we use the newest .lead
    # file instead of depending on the AudioSocket UUID packet.
    # --------------------------------------------------------------

    poc_lead_data = {}
    poc_lead_file = None

    try:
        lead_files = sorted(
            Path("/run/hnc-ai").glob("*.lead"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        if lead_files:
            poc_lead_file = lead_files[0]

            print(
                "POC LATEST VICIDIAL LEAD FILE:",
                poc_lead_file
            )

            poc_uuid = poc_lead_file.stem

            poc_lead_data = load_vicidial_lead(
                poc_uuid
            )

            if poc_lead_data:
                print(
                    "POC VICIDIAL LEAD LOADED:",
                    poc_lead_data
                )
            else:
                print(
                    "POC VICIDIAL LEAD LOAD FAILED"
                )
        else:
            print(
                "POC: NO VICIDIAL .lead FILE FOUND"
            )

    except Exception as exc:
        print(
            "POC VICIDIAL LEAD SCAN ERROR:",
            repr(exc)
        )

    # --------------------------------------------------------------
    # CALL CONNECT GREETING
    # Uses the actual Malaysia server time.
    # Caller audio during the greeting is ignored/drained.
    # --------------------------------------------------------------
    # Full-call customer recording buffer.
    # Created before greeting so ALL incoming AudioSocket audio
    # can be preserved, including audio arriving during TTS.
    customer_recording = bytearray()

    try:
        greeting = get_time_based_greeting()
        print("GREETING:", greeting)

        send_audio(conn, piper_speak(greeting), customer_recording)

        # Clear any audio that arrived while AI was speaking.
        time.sleep(0.15)
        drain_incoming_audio(conn, customer_recording)

        print("Greeting sent.")

    except Exception as exc:
        print("GREETING ERROR:", repr(exc))

    # --------------------------------------------------------------
    # CALL RECORDING
    # --------------------------------------------------------------
    call_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]

    ai_recording = bytearray()

    print("CALL RECORDING ID:", call_id)

    # --------------------------------------------------------------
    # CALL CONVERSATION STATE
    # --------------------------------------------------------------
    state = {
        "stage": "permission",

        # Call timing
        "start_time": datetime.now().astimezone().isoformat(),
        "end_time": None,

        # VICIdial lead identity
        "audiosocket_uuid": None,
        "lead_id": None,
        "phone_number": None,
        "first_name": None,
        "address1": None,
        "address2": None,

        "intent": None,
        "disposition": None,
        "wrong_number": False,
        "do_not_contact": False,
        "callback_later": False,
        "contact_preference": None,

        # Human-agent transfer
        "transfer_requested": False,
        "transfer_status": None,

        # Customer requirement capture
        "customer_captured_model": None,
        "preferred_model": None,
        "interested_model": None,
        "car_type": None,
        "purchase_type": None,
        "current_car": None,
        "budget": None,
        "monthly_payment": None,
        "purchase_timeline": None,
        "callback_time": None,
        "final_contact": None,
        "customer_language": None,
        "conversation_status": None,
        "conversation": [],
    }

    # --------------------------------------------------------------
    # POC: APPLY VICIDIAL LEAD TO CALL STATE
    # --------------------------------------------------------------
    if poc_lead_data:
        state["audiosocket_uuid"] = poc_lead_data.get("audiosocket_uuid")
        state["lead_id"] = poc_lead_data.get("lead_id")
        state["phone_number"] = poc_lead_data.get("phone_number")
        state["first_name"] = poc_lead_data.get("first_name")
        state["address1"] = poc_lead_data.get("address1")
        state["address2"] = poc_lead_data.get("address2")

        print("POC STATE LEAD ID:", state["lead_id"])
        print("POC STATE PHONE:", state["phone_number"])
        print("POC STATE FIRST NAME:", state["first_name"])

    print("CALL FLOW: permission")

    # Publish this ACTUAL AudioSocket connection to the
    # realtime dashboard. This is not based on old reports.
    write_active_call(call_id, state)

    speech = bytearray()
    silence_frames = 0
    speaking = False

    # While AI TTS is playing, incoming audio must NEVER be
    # considered caller speech.
    ai_speaking = False

    try:
        while True:

            header = recv_exact(conn, 3)

            if header is None:
                print("CUSTOMER HANGUP / AUDIO SOCKET CLOSED")

                # -----------------------------------------------------
                # CUSTOMER HANGUP BEFORE NORMAL CALL COMPLETION
                #
                # A caller may disconnect before process_turn()
                # reaches call_completed=True. The call must still be
                # persisted to JSON + MySQL.
                # -----------------------------------------------------
                state["_customer_hung_up"] = True

                try:
                    if not state.get("_final_report_saved"):
                        state["_final_report_saved"] = True

                        recording_file = save_call_recording(
                            call_id,
                            bytes(customer_recording),
                            bytes(state.get("_ai_recording", b""))
                        )

                        save_call_report(
                            state,
                            call_id,
                            recording_file
                        )

                        print(
                            "CUSTOMER HANGUP REPORT SAVED:",
                            call_id
                        )

                except Exception as exc:
                    print(
                        "CUSTOMER HANGUP REPORT SAVE ERROR:",
                        repr(exc)
                    )

                break

            packet_type = header[0]
            length = struct.unpack("!H", header[1:3])[0]

            payload = recv_exact(conn, length)

            if payload is None:
                break

            # ---------------------------------------------------------
            # AUDIO
            # ---------------------------------------------------------
            if packet_type == 0x10:

                # Always record incoming AudioSocket audio.
                # This keeps the complete customer-side call timeline.
                customer_recording.extend(payload)

                # While AI is speaking, do NOT send incoming audio
                # into the Whisper speech buffer. This prevents AI
                # playback / acoustic echo from being transcribed.
                if ai_speaking:
                    continue

                level = rms(payload)

                if level >= RMS_THRESHOLD:

                    speech.extend(payload)
                    speaking = True
                    silence_frames = 0

                elif speaking:

                    speech.extend(payload)
                    silence_frames += 1

                    silent_seconds = silence_frames * 0.020

                    if silent_seconds >= SILENCE_SECONDS:

                        turn = bytes(speech)

                        speech.clear()
                        silence_frames = 0
                        speaking = False

                        # -------------------------------------------------
                        # AI processing
                        # -------------------------------------------------
                        ai_speaking = True

                        try:
                            call_completed = process_turn(
                                conn,
                                turn,
                                state,
                                call_id,
                                customer_recording
                            )

                            # A completed conversation must immediately
                            # disappear from the realtime monitor.
                            if call_completed:
                                remove_active_call(call_id)

                                if state.get("_customer_hung_up"):
                                    print(
                                        "CUSTOMER HUNG UP - "
                                        "STOPPING AI CALL"
                                    )
                                else:
                                    print("CALL FLOW COMPLETE")

                            else:
                                # Keep the actual running call synchronized
                                # with the realtime dashboard.
                                write_active_call(call_id, state)

                            if call_completed:
                                print("FINAL LEAD DATA:", state)

                                print("FINAL LEAD DATA:", state)

                                # Save complete two-sided call recording.
                                recording_file = save_call_recording(
                                    call_id,
                                    bytes(customer_recording),
                                    bytes(state.get("_ai_recording", b""))
                                )

                                if not state.get("_final_report_saved"):
                                    state["_final_report_saved"] = True

                                    save_call_report(
                                        state,
                                        call_id,
                                        recording_file
                                    )

                                # Allow final TTS to finish completely.
                                time.sleep(0.30)

                                # -------------------------------------------------
                                # HUMAN AGENT TRANSFER SIGNAL
                                #
                                # Asterisk checks this file immediately after
                                # AudioSocket() returns. Do NOT remove this file
                                # here; Asterisk will remove it after reading it.
                                # -------------------------------------------------
                                if state.get("transfer_requested"):
                                    audiosocket_uuid = state.get("audiosocket_uuid")

                                    if audiosocket_uuid:
                                        transfer_file = Path(
                                            f"/run/hnc-ai/{audiosocket_uuid}.transfer"
                                        )

                                        try:
                                            transfer_file.write_text(
                                                "requested\\n",
                                                encoding="utf-8"
                                            )

                                            state["transfer_status"] = "signaled"

                                            print(
                                                "AGENT TRANSFER SIGNAL CREATED:",
                                                transfer_file
                                            )

                                        except Exception as exc:
                                            state["transfer_status"] = "signal_error"

                                            print(
                                                "AGENT TRANSFER SIGNAL ERROR:",
                                                repr(exc)
                                            )
                                    else:
                                        state["transfer_status"] = "missing_uuid"

                                        print(
                                            "AGENT TRANSFER ERROR: "
                                            "AudioSocket UUID missing"
                                        )

                                # Tell Asterisk AudioSocket to terminate.
                                terminate_audiosocket(conn)

                                print("Hanging up Toyota AI call.")
                                return True

                        finally:
                            ai_speaking = False

                            # Throw away any audio accumulated during
                            # Whisper/KB/TTS processing and immediately
                            # following playback.
                            drain_incoming_audio(conn, customer_recording)

            # ---------------------------------------------------------
            # DTMF
            # ---------------------------------------------------------
            elif packet_type == 0x01:
                print("DTMF:", payload.hex())

            # ---------------------------------------------------------
            # UUID
            # ---------------------------------------------------------
            elif packet_type == 0x00:
                # -----------------------------------------------------
                # AUDIOSOCKET UUID / VICIDIAL LEAD
                # -----------------------------------------------------

                audiosocket_uuid = normalize_audiosocket_uuid(payload)

                print(
                    "AudioSocket UUID:",
                    audiosocket_uuid
                )

                state["audiosocket_uuid"] = audiosocket_uuid

                # Load lead metadata written by Asterisk.
                lead_data = load_vicidial_lead(
                    audiosocket_uuid
                )

                if lead_data:

                    state.update(lead_data)

                    print(
                        "VICIDIAL LEAD ID:",
                        state.get("lead_id")
                    )

                    print(
                        "VICIDIAL PHONE:",
                        state.get("phone_number")
                    )

                    # -------------------------------------------------
                    # RESOLVE EXISTING LEAD OR CREATE NEW LEAD
                    # -------------------------------------------------

                    try:
                        from toyota_vicidial import (
                            resolve_or_create_lead
                        )

                        resolved = resolve_or_create_lead(
                            lead_id=state.get("lead_id"),
                            phone_number=state.get("phone_number"),
                            first_name=state.get("first_name"),
                            address1=state.get("address1"),
                            address2=state.get("address2"),
                        )

                        print(
                            "VICIDIAL RESOLUTION:",
                            resolved
                        )

                        if resolved.get("success"):

                            state["lead_id"] = resolved.get(
                                "lead_id"
                            )

                            state["phone_number"] = (
                                resolved.get("phone_number")
                                or state.get("phone_number")
                            )

                            state["first_name"] = (
                                resolved.get("first_name")
                                or state.get("first_name")
                            )

                            state["address1"] = (
                                resolved.get("address1")
                                or state.get("address1")
                            )

                            state["address2"] = (
                                resolved.get("address2")
                                or state.get("address2")
                            )

                            state["lead_source"] = (
                                "new"
                                if resolved.get("created")
                                else "existing"
                            )

                            print(
                                "TOYOTA VICIDIAL LEAD READY:",
                                state.get("lead_id"),
                                state.get("phone_number"),
                                state.get("lead_source")
                            )

                            # Refresh realtime dashboard with resolved
                            # VICIdial customer information.
                            write_active_call(call_id, state)

                        else:
                            print(
                                "VICIDIAL LEAD RESOLUTION FAILED:",
                                resolved
                            )

                    except Exception as exc:
                        print(
                            "VICIDIAL RESOLUTION ERROR:",
                            repr(exc)
                        )

                else:
                    print(
                        "VICIDIAL LEAD DATA EMPTY FOR UUID:",
                        audiosocket_uuid
                    )

            else:
                print(
                    f"AudioSocket packet "
                    f"type=0x{packet_type:02x} length={length}"
                )

    except ConnectionResetError:
        print("AudioSocket connection closed by Asterisk.")

    except BrokenPipeError:
        print("AudioSocket connection closed by Asterisk.")

    except OSError as exc:
        if getattr(exc, "errno", None) == 104:
            print("AudioSocket connection closed by Asterisk.")
        else:
            print("CONNECTION ERROR:", repr(exc))

    except Exception as exc:
        print("CONNECTION ERROR:", repr(exc))

    finally:
        conn.close()
        print("TOYOTA CALL DISCONNECTED")


print("=" * 70)
print("Toyota Malaysia Live Voice AI")
print("=" * 70)
print("Loading Whisper:", WHISPER_MODEL)

WHISPER = WhisperModel(
    WHISPER_MODEL,
    device="cpu",
    compute_type="int8",
)

print("Whisper loaded.")
print(f"Listening on {HOST}:{PORT}")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(10)

while True:
    conn, addr = server.accept()

    try:
        handle_connection(conn, addr)
    except Exception as exc:
        print("FATAL CONNECTION ERROR:", repr(exc))
