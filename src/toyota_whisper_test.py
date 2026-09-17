#!/usr/bin/env python3

import os
import sys
import subprocess
import tempfile

from faster_whisper import WhisperModel


if len(sys.argv) != 2:
    print("Usage: python3 src/toyota_whisper_test.py /path/to/file.wav")
    sys.exit(1)

input_wav = sys.argv[1]

if not os.path.isfile(input_wav):
    print("ERROR: File not found:", input_wav)
    sys.exit(1)

with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    output_wav = f.name

try:
    print("Converting audio to 16 kHz mono...")

    subprocess.run([
        "sox",
        input_wav,
        "-c", "1",
        "-r", "16000",
        output_wav
    ], check=True)

    print("Loading Whisper base.en...")

    model = WhisperModel(
        "base.en",
        device="cpu",
        compute_type="int8"
    )

    print("Transcribing...")
    print()

    segments, info = model.transcribe(
        output_wav,
        language="en",
        beam_size=5,
        vad_filter=True
    )

    print("Detected language:", info.language)
    print("Language probability:", round(info.language_probability, 3))
    print()
    print("=" * 80)
    print("TRANSCRIPT")
    print("=" * 80)

    text_parts = []

    for segment in segments:
        text = segment.text.strip()

        if text:
            print(
                f"[{segment.start:7.2f} - {segment.end:7.2f}] {text}"
            )
            text_parts.append(text)

    print("=" * 80)
    print("FULL TEXT:")
    print(" ".join(text_parts))
    print("=" * 80)

finally:
    if os.path.exists(output_wav):
        os.remove(output_wav)
