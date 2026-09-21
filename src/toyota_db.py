#!/usr/bin/env python3

import json
import os
from datetime import datetime

import pymysql
from pymysql.cursors import DictCursor


def get_connection():
    return pymysql.connect(
        host=os.environ.get("TOYOTA_DB_HOST", "127.0.0.1"),
        user=os.environ.get("TOYOTA_DB_USER", "toyota_ai"),
        password=os.environ["TOYOTA_DB_PASS"],
        database=os.environ.get("TOYOTA_DB_NAME", "toyota_ai"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
        autocommit=False,
    )


def _parse_datetime(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value)
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def save_call_to_db(report):
    """
    Save one completed Toyota AI call atomically.

    Main call data -> calls
    Conversation -> call_conversation

    Existing call_id is updated safely.
    Conversation rows are replaced for that call.
    """

    call_id = report.get("call_id")

    if not call_id:
        raise ValueError("Missing call_id")

    conn = get_connection()

    try:
        with conn.cursor() as cur:

            vicidial_update = report.get("vicidial_update")

            if vicidial_update is not None:
                vicidial_update = json.dumps(
                    vicidial_update,
                    ensure_ascii=False,
                )

            sql = """
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
                ON DUPLICATE KEY UPDATE
                    lead_id = VALUES(lead_id),
                    phone_number = VALUES(phone_number),
                    first_name = VALUES(first_name),
                    start_time = VALUES(start_time),
                    end_time = VALUES(end_time),
                    duration_seconds = VALUES(duration_seconds),
                    conversation_status = VALUES(conversation_status),
                    intent = VALUES(intent),
                    disposition = VALUES(disposition),
                    customer_captured_model =
                        VALUES(customer_captured_model),
                    car_type = VALUES(car_type),
                    purchase_type = VALUES(purchase_type),
                    current_car = VALUES(current_car),
                    interested_model = VALUES(interested_model),
                    budget = VALUES(budget),
                    monthly_payment = VALUES(monthly_payment),
                    purchase_timeline = VALUES(purchase_timeline),
                    callback_time = VALUES(callback_time),
                    contact_preference = VALUES(contact_preference),
                    customer_language = VALUES(customer_language),
                    recording = VALUES(recording),
                    vicidial_status = VALUES(vicidial_status),
                    vicidial_update = VALUES(vicidial_update),
                    ai_comments = VALUES(ai_comments)
            """

            cur.execute(
                sql,
                (
                    call_id,
                    report.get("lead_id"),
                    report.get("phone_number"),
                    report.get("first_name"),
                    _parse_datetime(report.get("start_time")),
                    _parse_datetime(report.get("end_time")),
                    report.get("duration_seconds"),
                    report.get("conversation_status"),
                    report.get("intent"),
                    report.get("disposition"),
                    report.get("customer_captured_model"),
                    report.get("car_type"),
                    report.get("purchase_type"),
                    report.get("current_car"),
                    report.get("interested_model"),
                    report.get("budget"),
                    report.get("monthly_payment"),
                    report.get("purchase_timeline"),
                    report.get("callback_time"),
                    report.get("contact_preference"),
                    report.get("customer_language"),
                    report.get("recording"),
                    report.get("vicidial_status"),
                    vicidial_update,
                    report.get("ai_comments"),
                ),
            )

            # Rebuild conversation for this call.
            # This makes retries/idempotent saves safe.
            cur.execute(
                """
                DELETE FROM call_conversation
                WHERE call_id = %s
                """,
                (call_id,),
            )

            conversation_count = 0

            for item in report.get("conversation") or []:

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
                        _parse_datetime(
                            item.get("timestamp")
                        ),
                    ),
                )

                conversation_count += 1

        conn.commit()

        print(
            "TOYOTA DB SAVE SUCCESS:",
            call_id,
            "conversation=",
            conversation_count,
        )

        return {
            "success": True,
            "call_id": call_id,
            "conversation_count": conversation_count,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
