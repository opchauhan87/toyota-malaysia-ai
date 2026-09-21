#!/usr/bin/env python3

import json
import os
import glob
import sys
from datetime import datetime

import pymysql


BASE_DIR = "/opt/toyota-malaysia-ai"
JSON_DIR = os.path.join(BASE_DIR, "reports", "calls")


def get_db_connection():
    host = os.environ.get("TOYOTA_DB_HOST", "127.0.0.1")
    user = os.environ.get("TOYOTA_DB_USER", "toyota_ai")
    password = os.environ.get("TOYOTA_DB_PASS")
    database = os.environ.get("TOYOTA_DB_NAME", "toyota_ai")

    if not password:
        print("ERROR: TOYOTA_DB_PASS is not set.")
        print("Set it first:")
        print("export TOYOTA_DB_PASS='YOUR_DB_PASSWORD'")
        sys.exit(1)

    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def parse_datetime(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value)

        # MariaDB DATETIME does not store timezone information.
        # Keep the local wall-clock time from the JSON.
        return dt.replace(tzinfo=None)

    except Exception:
        return None


def migrate_file(conn, filepath):
    filename = os.path.basename(filepath)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return {
            "status": "error",
            "file": filename,
            "message": f"Invalid JSON: {exc}",
            "conversation": 0,
        }

    call_id = data.get("call_id")

    if not call_id:
        return {
            "status": "error",
            "file": filename,
            "message": "Missing call_id",
            "conversation": 0,
        }

    conversation = data.get("conversation") or []

    with conn.cursor() as cur:

        # Check whether this call already exists.
        cur.execute(
            "SELECT id FROM calls WHERE call_id = %s",
            (call_id,),
        )

        existing = cur.fetchone()

        if existing:
            return {
                "status": "duplicate",
                "file": filename,
                "call_id": call_id,
                "conversation": 0,
            }

        vicidial_update = data.get("vicidial_update")

        if vicidial_update is not None:
            vicidial_update = json.dumps(
                vicidial_update,
                ensure_ascii=False,
            )

        insert_call = """
            INSERT INTO calls (
                call_id,
                lead_id,
                phone_number,
                first_name,
                start_time,
                end_time,
                duration_seconds,
                conversation_status,
                intent,
                disposition,
                customer_captured_model,
                car_type,
                purchase_type,
                current_car,
                interested_model,
                budget,
                monthly_payment,
                purchase_timeline,
                callback_time,
                contact_preference,
                customer_language,
                recording,
                vicidial_status,
                vicidial_update,
                ai_comments
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
        """

        cur.execute(
            insert_call,
            (
                call_id,
                data.get("lead_id"),
                data.get("phone_number"),
                data.get("first_name"),
                parse_datetime(data.get("start_time")),
                parse_datetime(data.get("end_time")),
                data.get("duration_seconds"),
                data.get("conversation_status"),
                data.get("intent"),
                data.get("disposition"),
                data.get("customer_captured_model"),
                data.get("car_type"),
                data.get("purchase_type"),
                data.get("current_car"),
                data.get("interested_model"),
                data.get("budget"),
                data.get("monthly_payment"),
                data.get("purchase_timeline"),
                data.get("callback_time"),
                data.get("contact_preference"),
                data.get("customer_language"),
                data.get("recording"),
                data.get("vicidial_status"),
                vicidial_update,
                data.get("ai_comments"),
            ),
        )

        # Insert conversation rows.
        conversation_count = 0

        for item in conversation:
            if not isinstance(item, dict):
                continue

            speaker = item.get("speaker")

            if speaker not in ("customer", "ai"):
                continue

            cur.execute(
                """
                INSERT INTO call_conversation (
                    call_id,
                    speaker,
                    original_text,
                    english_text,
                    conversation_time
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    call_id,
                    speaker,
                    item.get("original_text"),
                    item.get("english_text"),
                    parse_datetime(item.get("timestamp")),
                ),
            )

            conversation_count += 1

    return {
        "status": "imported",
        "file": filename,
        "call_id": call_id,
        "conversation": conversation_count,
    }


def main():
    json_files = sorted(
        glob.glob(
            os.path.join(JSON_DIR, "toyota-*.json")
        )
    )

    print()
    print("Toyota Malaysia JSON → MySQL Migration")
    print("=" * 50)
    print(f"JSON directory : {JSON_DIR}")
    print(f"JSON files     : {len(json_files)}")
    print()

    if not json_files:
        print("No JSON reports found.")
        return

    conn = get_db_connection()

    imported = 0
    duplicates = 0
    errors = 0
    conversation_rows = 0

    try:
        for filepath in json_files:
            result = migrate_file(conn, filepath)

            status = result["status"]

            if status == "imported":
                imported += 1
                conversation_rows += result["conversation"]

                print(
                    f"[IMPORTED]  {result['file']} "
                    f"conversation={result['conversation']}"
                )

            elif status == "duplicate":
                duplicates += 1

                print(
                    f"[SKIPPED]   {result['file']} "
                    f"(already exists)"
                )

            else:
                errors += 1

                print(
                    f"[ERROR]     {result['file']} "
                    f"{result['message']}"
                )

        conn.commit()

    except Exception as exc:
        conn.rollback()
        print()
        print("MIGRATION FAILED")
        print(repr(exc))
        sys.exit(1)

    finally:
        conn.close()

    print()
    print("=" * 50)
    print("Migration Summary")
    print("=" * 50)
    print(f"JSON files          : {len(json_files)}")
    print(f"Imported calls      : {imported}")
    print(f"Duplicate calls     : {duplicates}")
    print(f"Conversation rows    : {conversation_rows}")
    print(f"Errors              : {errors}")
    print()

    if errors:
        print("Migration completed with errors.")
        sys.exit(2)

    print("Migration completed successfully.")


if __name__ == "__main__":
    main()
