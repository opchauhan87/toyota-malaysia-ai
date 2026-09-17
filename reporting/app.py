from flask import Flask, render_template, jsonify, send_file, abort, request
from pathlib import Path
from datetime import datetime
import json
import wave
import io
import time

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

