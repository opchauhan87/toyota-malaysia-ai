#!/usr/bin/env python3

import json
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toyota-malaysia-ai")
PDF_DIR = BASE / "data/brochures"
OUT_DIR = BASE / "data/brochure_ocr"
REPORT = BASE / "reports/toyota_brochure_ocr_report.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

MIN_TEXT_CHARS = 1000

def clean_text(text):
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def pdf_text(pdf):
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        timeout=180
    )

    if result.returncode != 0:
        return ""

    return clean_text(result.stdout)

def render_page(pdf, page_no, output_prefix):
    subprocess.run(
        [
            "pdftoppm",
            "-f", str(page_no),
            "-singlefile",
            "-jpeg",
            "-r", "200",
            str(pdf),
            str(output_prefix)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
        check=True
    )

def ocr_image(image):
    result = subprocess.run(
        [
            "tesseract",
            str(image),
            "stdout",
            "-l", "eng",
            "--psm", "6"
        ],
        capture_output=True,
        text=True,
        timeout=180
    )

    if result.returncode != 0:
        return ""

    return clean_text(result.stdout)

print("TOYOTA MALAYSIA BULK BROCHURE OCR ENGINE")
print("=" * 65)

pdfs = sorted(PDF_DIR.glob("*.pdf"))

print("PDF files :", len(pdfs))
print()

records = []

normal_text = 0
ocr_used = 0
failed = 0

for index, pdf in enumerate(pdfs, 1):

    print(f"[{index:02d}/{len(pdfs)}] {pdf.name}")

    result = {
        "source_file": pdf.name,
        "source_path": str(pdf),
        "processed_at": datetime.now().isoformat(),
        "method": None,
        "pages": 0,
        "text_chars": 0,
        "status": "FAILED",
        "output_text": None
    }

    try:
        text = pdf_text(pdf)

        # Determine PDF page count
        info = subprocess.run(
            ["pdfinfo", str(pdf)],
            capture_output=True,
            text=True,
            timeout=60
        )

        pages_match = re.search(r"Pages:\s+(\d+)", info.stdout)
        pages = int(pages_match.group(1)) if pages_match else 0
        result["pages"] = pages

        # Normal PDF text is sufficient
        if len(text) >= MIN_TEXT_CHARS:
            output = OUT_DIR / (pdf.stem + ".txt")
            output.write_text(text, encoding="utf-8")

            result["method"] = "pdftotext"
            result["text_chars"] = len(text)
            result["status"] = "OK"
            result["output_text"] = str(output)

            normal_text += 1

            print(
                f"        TEXT OK | pages={pages} | chars={len(text):,}"
            )

        else:
            print(
                f"        TEXT LOW ({len(text)} chars) -> OCR {pages} pages"
            )

            all_pages = []

            work_dir = OUT_DIR / "_work"
            work_dir.mkdir(parents=True, exist_ok=True)

            for page in range(1, pages + 1):

                image = work_dir / f"{pdf.stem}_page_{page}"

                try:
                    render_page(pdf, page, image)

                    jpg = Path(str(image) + ".jpg")

                    if jpg.exists():
                        page_text = ocr_image(jpg)

                        if page_text:
                            all_pages.append(
                                f"\n===== PAGE {page} =====\n\n{page_text}"
                            )

                        jpg.unlink(missing_ok=True)

                except Exception as page_error:
                    print(
                        f"        Page {page} OCR warning: {page_error}"
                    )

            text = clean_text("\n".join(all_pages))

            output = OUT_DIR / (pdf.stem + ".txt")
            output.write_text(text, encoding="utf-8")

            result["method"] = "tesseract_ocr"
            result["text_chars"] = len(text)
            result["status"] = "OK" if len(text) > 100 else "LOW_TEXT"
            result["output_text"] = str(output)

            ocr_used += 1

            print(
                f"        OCR DONE | pages={pages} | chars={len(text):,}"
            )

    except Exception as e:
        result["error"] = str(e)
        failed += 1
        print("        FAILED:", e)

    records.append(result)

# Remove work directory if empty
work_dir = OUT_DIR / "_work"
if work_dir.exists():
    try:
        if not any(work_dir.iterdir()):
            work_dir.rmdir()
    except Exception:
        pass

output_data = {
    "country": "Malaysia",
    "source": "Toyota Malaysia Official Brochures",
    "generated_at": datetime.now().isoformat(),
    "total_pdfs": len(pdfs),
    "normal_text_extraction": normal_text,
    "ocr_processed": ocr_used,
    "failed": failed,
    "records": records
}

with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print()
print("=" * 65)
print("OCR SUMMARY")
print("PDFs                    :", len(pdfs))
print("Normal text extraction  :", normal_text)
print("OCR processed           :", ocr_used)
print("Failed                  :", failed)
print("Text directory          :", OUT_DIR)
print("Report                  :", REPORT)
print()
print("JSON VALID")
