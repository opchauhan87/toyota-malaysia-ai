from flask import Flask, render_template, jsonify, send_file, abort, request
from pathlib import Path
from datetime import datetime
import json
import wave
import io
import time
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

BASE_DIR = Path("/opt/toyota-malaysia-ai")
REPORT_DIR = BASE_DIR / "reports" / "calls"
RECORDING_DIR = BASE_DIR / "recordings"
ACTIVE_FILE = Path("/run/toyota-ai/active-calls.json")

app = Flask(__name__)


def safe_recording_path(filename):
    requested = (RECORDING_DIR / filename).resolve()
    try:
        requested.relative_to(RECORDING_DIR.resolve())
    except ValueError:
        abort(403)
    if not requested.is_file():
        abort(404)
    return requested


def get_recording_duration(recording_path):
    if not recording_path:
        return None
    try:
        path = Path(recording_path).resolve()
        path.relative_to(RECORDING_DIR.resolve())
        if not path.is_file():
            return None
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return round(frames / rate, 2) if rate > 0 else None
    except Exception:
        return None


def load_json_report(path):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        data["_report_file"] = path.name
        data["recording_duration_seconds"] = get_recording_duration(data.get("recording"))
        return data
    except Exception:
        return None


def load_reports():
    reports = []
    if not REPORT_DIR.exists():
        return reports

    for path in REPORT_DIR.glob("*.json"):
        data = load_json_report(path)
        if data:
            reports.append(data)

    grouped = {}
    for report in reports:
        call_id = str(report.get("call_id") or report.get("_report_file"))
        existing = grouped.get(call_id)
        if existing is None:
            grouped[call_id] = report
            continue

        existing_finished = bool(existing.get("end_time"))
        current_finished = bool(report.get("end_time"))
        if current_finished and not existing_finished:
            grouped[call_id] = report
        elif current_finished == existing_finished:
            existing_time = existing.get("end_time") or existing.get("start_time") or ""
            current_time = current_time = report.get("end_time") or report.get("start_time") or ""
            if current_time >= existing_time:
                grouped[call_id] = report

    reports = list(grouped.values())
    reports.sort(key=lambda x: x.get("start_time") or "", reverse=True)
    return reports


def calculate_stats(reports):
    total = len(reports)

    phone_leads = sum(
        1 for r in reports
        if r.get("disposition") in ("Interested – Agent Call", "Interested – Specific Model")
    )
    whatsapp_leads = sum(
        1 for r in reports
        if r.get("disposition") == "Interested – WhatsApp"
    )
    interested = sum(1 for r in reports if r.get("intent") == "Interested")
    not_interested = sum(1 for r in reports if r.get("disposition") == "Not Interested")
    callback = sum(1 for r in reports if r.get("disposition") == "Call Back Later")
    wrong_number = sum(1 for r in reports if r.get("disposition") == "Wrong Number")
    dnc = sum(1 for r in reports if r.get("disposition") == "Do Not Contact")

    hangup = sum(
        1 for r in reports
        if "customer hang up" in str(r.get("conversation_status") or r.get("status") or "").lower()
        or "customer hang up" in str(r.get("disposition") or "").lower()
    )

    total_duration = sum(float(r.get("duration_seconds") or 0) for r in reports)
    total_recording_duration = sum(float(r.get("recording_duration_seconds") or 0) for r in reports)
    recording_count = sum(1 for r in reports if r.get("recording_duration_seconds") is not None)

    return {
        "total": total,
        "phone_leads": phone_leads,
        "whatsapp_leads": whatsapp_leads,
        "interested": interested,
        "not_interested": not_interested,
        "callback": callback,
        "wrong_number": wrong_number,
        "dnc": dnc,
        "hangup": hangup,
        "total_duration": round(total_duration, 2),
        "total_recording_duration": round(total_recording_duration, 2),
        "recording_count": recording_count,
    }


def get_live_calls():
    if not ACTIVE_FILE.exists():
        return []
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return []
        live = []
        for call_id, call in data.items():
            if not isinstance(call, dict):
                continue
            if str(call.get("stage", "")).lower() == "completed":
                continue
            item = dict(call)
            item.setdefault("call_id", call_id)
            live.append(item)
        return live
    except Exception:
        return []



EXCEL_HEADERS = [
    "Call_ID",
    "Call_Date",
    "Call_Start_Time",
    "Call_End_Time",
    "Call_Duration_Sec",
    "Lead_ID",
    "Phone_Number",
    "Customer_Name",
    "Conversation_Status",
    "Disposition",
    "Customer_Captured_Model",
    "Car_Type",
    "Purchase_Type",
    "Current_Car",
    "Interested_Model",
    "Budget",
    "Monthly_Payment",
    "Purchase_Timeline",
    "Callback_Time",
    "Contact_Preference",
    "Customer_Language",
    "Customer_Transcript",
    "AI_Response",
    "KB_Question",
    "KB_Answer",
    "KB_Model",
    "KB_Variant",
    "KB_Source",
    "KB_Source_Date",
    "KB_Market",
    "KB_Price_Type",
    "Agent_Callback_Required",
    "WhatsApp_Required",
    "Recording_File",
    "Conversation_Notes",
    "Created_At",
]


def _conversation_parts(report):
    conversation = report.get("conversation") or []

    customer = []
    ai = []
    languages = []

    for item in conversation:
        if not isinstance(item, dict):
            continue

        speaker = str(item.get("speaker") or "").lower()

        value = (
            item.get("english_text")
            or item.get("original_text")
            or item.get("text")
            or ""
        ).strip()

        if speaker == "customer":
            if value:
                customer.append(value)

            if item.get("language"):
                languages.append(str(item["language"]))

        elif speaker == "ai":
            if value:
                ai.append(value)

    kb_questions = []
    kb_answers = []
    kb_models = []
    kb_variants = []

    for item in report.get("kb_history") or []:
        if not isinstance(item, dict):
            continue

        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()

        if question:
            kb_questions.append(question)

        if answer:
            kb_answers.append(answer)

        if item.get("model"):
            kb_models.append(str(item["model"]))

        if item.get("variant"):
            kb_variants.append(str(item["variant"]))

    return (
        "\n".join(customer),
        "\n".join(ai),
        ", ".join(dict.fromkeys(languages)),
        "\n".join(kb_questions),
        "\n".join(kb_answers),
        ", ".join(dict.fromkeys(kb_models)),
        ", ".join(dict.fromkeys(kb_variants)),
    )


def _excel_safe(value):
    """Remove characters that Excel/openpyxl cannot store in worksheet cells."""
    if value is None:
        return None

    if isinstance(value, str):
        return "".join(
            ch for ch in value
            if ch in "\\t\\n\\r"
            or 0x20 <= ord(ch) <= 0xD7FF
            or 0xE000 <= ord(ch) <= 0xFFFD
            or 0x10000 <= ord(ch) <= 0x10FFFF
        )

    if isinstance(value, (list, tuple)):
        return ", ".join(str(_excel_safe(v)) for v in value)

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    return value


def _report_excel_row(report):
    start = report.get("start_time") or ""
    end = report.get("end_time") or ""

    call_date = (
        start[:10]
        if start
        else (end[:10] if end else "")
    )

    disposition = report.get("disposition") or ""

    status = (
        report.get("conversation_status")
        or report.get("status")
        or (
            "Customer Hang Up"
            if disposition.lower() == "customer hang up"
            else ("Completed" if end else "")
        )
    )

    (
        customer_text,
        ai_text,
        language,
        kb_question,
        kb_answer,
        kb_model,
        kb_variant,
    ) = _conversation_parts(report)

    return [
        report.get("call_id"),
        call_date,
        start,
        end,
        report.get("duration_seconds"),
        report.get("lead_id"),
        report.get("phone_number"),
        report.get("first_name"),
        status,
        disposition,

        # Customer captured information
        report.get("preferred_model"),
        report.get("car_type"),
        report.get("purchase_type"),
        report.get("current_car"),
        report.get("interested_model")
        or report.get("preferred_model"),
        report.get("budget"),
        report.get("monthly_payment"),
        report.get("purchase_timeline"),
        report.get("callback_time"),
        report.get("contact_preference"),

        language,
        customer_text,
        ai_text,

        # Verified KB information
        kb_question,
        kb_answer,
        kb_model,
        kb_variant,
        "Toyota Malaysia official website" if kb_question else "",
        call_date if kb_question else "",
        "Malaysia" if kb_question else "",
        (
            "Price"
            if kb_question
            and "price" in kb_question.lower()
            else ""
        ),

        "Yes"
        if disposition in (
            "Interested – Agent Call",
            "Interested – Specific Model",
            "Call Back Later",
        )
        else "No",

        "Yes"
        if disposition == "Interested – WhatsApp"
        else "No",

        report.get("recording"),

        report.get("ai_comments")
        or report.get("conversation_notes")
        or "",

        report.get("created_at")
        or end
        or start,
    ]


@app.route("/api/export/excel")
def api_export_excel():
    reports = load_reports()

    date_from = request.args.get(
        "date_from",
        ""
    ).strip()

    date_to = request.args.get(
        "date_to",
        ""
    ).strip()

    phone = request.args.get(
        "phone",
        ""
    ).strip()

    df = (
        datetime.fromisoformat(date_from).date()
        if date_from
        else None
    )

    dt = (
        datetime.fromisoformat(date_to).date()
        if date_to
        else None
    )

    filtered = [
        r for r in reports
        if report_matches_filters(
            r,
            df,
            dt,
            phone,
        )
    ]

    wb = Workbook()

    ws = wb.active
    ws.title = "Call_Report"

    ws.append(EXCEL_HEADERS)

    for report in filtered:
        ws.append(
            [_excel_safe(v) for v in _report_excel_row(report)]
        )

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    widths = [
        38, 12, 24, 24, 16, 12, 18, 20,
        20, 28, 24, 16, 18, 20, 24, 16,
        20, 20, 20, 22, 16, 50, 50, 45,
        60, 22, 22, 38, 16, 14, 16, 20,
        18, 40, 60, 24,
    ]

    # ---------------------------------------------------------
    # Call Summary sheet
    # ---------------------------------------------------------
    summary = wb.create_sheet("Call_Summary")

    summary.append(["Toyota Malaysia AI - Call Summary"])
    summary.append([])
    summary.append(["Metric", "Value"])

    total_calls = len(filtered)

    phone_leads = sum(
        1 for r in filtered
        if r.get("disposition") in (
            "Interested – Agent Call",
            "Interested – Specific Model",
        )
    )

    whatsapp_leads = sum(
        1 for r in filtered
        if r.get("disposition") == "Interested – WhatsApp"
    )

    interested = sum(
        1 for r in filtered
        if str(r.get("disposition") or "").startswith("Interested")
    )

    not_interested = sum(
        1 for r in filtered
        if r.get("disposition") == "Not Interested"
    )

    callback_later = sum(
        1 for r in filtered
        if r.get("disposition") == "Call Back Later"
    )

    wrong_number = sum(
        1 for r in filtered
        if r.get("disposition") == "Wrong Number"
    )

    do_not_contact = sum(
        1 for r in filtered
        if r.get("disposition") == "Do Not Contact"
    )

    customer_hangup = sum(
        1 for r in filtered
        if r.get("disposition") == "Customer Hang Up"
    )

    durations = []

    for r in filtered:
        try:
            value = float(r.get("duration_seconds") or 0)
            if value > 0:
                durations.append(value)
        except (TypeError, ValueError):
            pass

    average_duration = (
        round(sum(durations) / len(durations), 2)
        if durations else 0
    )

    summary_rows = [
        ["Total Calls", total_calls],
        ["Phone Leads", phone_leads],
        ["WhatsApp Leads", whatsapp_leads],
        ["Interested", interested],
        ["Not Interested", not_interested],
        ["Call Back Later", callback_later],
        ["Wrong Number", wrong_number],
        ["Do Not Contact", do_not_contact],
        ["Customer Hang Up", customer_hangup],
        ["Average Duration (Sec)", average_duration],
    ]

    for row in summary_rows:
        summary.append(row)

    summary.append([])
    summary.append(["Applied Filters", ""])
    summary.append(["Date From", date_from or "All"])
    summary.append(["Date To", date_to or "All"])
    summary.append(["Phone", phone or "All"])

    summary.freeze_panes = "A4"
    summary.column_dimensions["A"].width = 30
    summary.column_dimensions["B"].width = 24

    for cell in summary[1]:
        cell.font = cell.font.copy(bold=True, size=14)

    for cell in summary[3]:
        cell.font = cell.font.copy(bold=True)

    for index, width in enumerate(
        widths,
        start=1,
    ):
        ws.column_dimensions[
            get_column_letter(index)
        ].width = width

    for cell in ws[1]:
        cell.font = cell.font.copy(
            bold=True
        )

    output = io.BytesIO()

    wb.save(output)

    output.seek(0)

    return send_file(
        output,
        mimetype=(
            "application/"
            "vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        as_attachment=True,
        download_name="toyota_call_report.xlsx",
    )


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def report_matches_filters(report, date_from=None, date_to=None, phone=None):
    dt = parse_date(report.get("start_time") or report.get("end_time"))
    if date_from and (not dt or dt.date() < date_from):
        return False
    if date_to and (not dt or dt.date() > date_to):
        return False
    if phone:
        haystack = str(report.get("phone_number") or "").lower()
        if phone.lower() not in haystack:
            return False
    return True


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/reports")
def api_reports():
    reports = load_reports()

    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    phone = request.args.get("phone", "").strip()

    df = datetime.fromisoformat(date_from).date() if date_from else None
    dt = datetime.fromisoformat(date_to).date() if date_to else None

    filtered = [r for r in reports if report_matches_filters(r, df, dt, phone)]

    return jsonify({
        "stats": calculate_stats(filtered),
        "reports": filtered,
        "total_available": len(reports),
        "server_time": datetime.now().astimezone().isoformat(),
    })


@app.route("/api/live-calls")
def api_live_calls():
    live_calls = get_live_calls()
    result = []

    for r in live_calls:
        item = dict(r)
        start_time = r.get("start_time")
        elapsed = r.get("duration_seconds") or 0

        if start_time:
            try:
                started = datetime.fromisoformat(start_time)
                elapsed = max(0, (datetime.now(started.tzinfo) - started).total_seconds())
            except Exception:
                pass

        item["live_duration_seconds"] = round(float(elapsed), 1)

        conversation = r.get("conversation") or []
        if conversation:
            last = conversation[-1]
            item["last_speaker"] = last.get("speaker")
            item["last_message"] = last.get("english_text") or last.get("original_text") or ""
        else:
            item["last_speaker"] = None
            item["last_message"] = ""

        result.append(item)

    return jsonify({
        "count": len(result),
        "calls": result,
        "server_time": datetime.now().astimezone().isoformat(),
    })


@app.route("/recordings/<path:filename>")
def recording(filename):
    requested = safe_recording_path(filename)
    return send_file(requested, mimetype="audio/wav", conditional=True)


@app.route("/recordings/channel/<channel>/<path:filename>")
def recording_channel(channel, filename):
    if channel not in ("customer", "ai", "both"):
        abort(400)

    requested = safe_recording_path(filename)

    try:
        with wave.open(str(requested), "rb") as src:
            channels = src.getnchannels()
            sample_width = src.getsampwidth()
            frame_rate = src.getframerate()
            frames = src.readframes(src.getnframes())

        if channels == 1:
            output = io.BytesIO()
            with wave.open(output, "wb") as dst:
                dst.setnchannels(1)
                dst.setsampwidth(sample_width)
                dst.setframerate(frame_rate)
                dst.writeframes(frames)
            output.seek(0)
            return send_file(output, mimetype="audio/wav",
                             download_name=f"{requested.stem}-{channel}.wav")

        if channels != 2:
            abort(415)

        bytes_per_sample = sample_width
        frame_size = channels * bytes_per_sample
        total_frames = len(frames) // frame_size
        customer = bytearray()
        ai = bytearray()

        for i in range(total_frames):
            offset = i * frame_size
            customer.extend(frames[offset:offset + bytes_per_sample])
            ai.extend(frames[offset + bytes_per_sample:offset + frame_size])

        selected = frames if channel == "both" else (bytes(customer) if channel == "customer" else bytes(ai))

        output = io.BytesIO()
        with wave.open(output, "wb") as dst:
            dst.setnchannels(2 if channel == "both" else 1)
            dst.setsampwidth(sample_width)
            dst.setframerate(frame_rate)
            dst.writeframes(selected)
        output.seek(0)

        return send_file(output, mimetype="audio/wav",
                         download_name=f"{requested.stem}-{channel}.wav")
    except Exception:
        abort(500)


@app.route("/health")
def health():
    reports = load_reports()
    live = get_live_calls()
    return jsonify({
        "status": "ok",
        "reports": len(reports),
        "active_calls": len(live),
        "time": datetime.now().astimezone().isoformat()
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=9080, debug=False)

