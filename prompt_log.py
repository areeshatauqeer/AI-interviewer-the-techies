import json
import os
import sqlite3
import threading
import datetime

LOG_PATH = "PROMPT.md"
DB_PATH = "sessions.db"
_lock = threading.Lock()


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_record(record):
    with _lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def log_records(records):
    with _lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            for record in records:
                f.write(
                    json.dumps(record, ensure_ascii=False, default=str) + "\n"
                )


def _existing_sessions():
    if not os.path.exists(LOG_PATH):
        return set()
    seen = set()
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") == "session_start":
                seen.add(record.get("session_id"))
    return seen


def backfill_from_db():
    if not os.path.exists(DB_PATH):
        print(f"[prompt_log] {DB_PATH} not found, nothing to backfill")
        return 0

    existing = _existing_sessions()

    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT session_id, candidate_id, topics, updated_at "
            "FROM sessions ORDER BY updated_at"
        ).fetchall()

    written = 0
    for session_id, candidate_id, topics_json, updated_at in rows:
        if session_id in existing:
            continue
        records = [{
            "type": "session_start",
            "session_id": session_id,
            "candidate_id": candidate_id,
            "timestamp": updated_at,
        }]
        try:
            topics = json.loads(topics_json)
        except (TypeError, ValueError):
            topics = []

        for index, topic in enumerate(topics, 1):
            record = {
                "type": "turn",
                "session_id": session_id,
                "candidate_id": candidate_id,
                "turn": index,
                "day": topic.get("day"),
                "mode": topic.get("mode"),
                "question": topic.get("question"),
            }
            if topic.get("answer"):
                record["answer"] = topic["answer"]
            records.append(record)

        records.append({
            "type": "session_end",
            "session_id": session_id,
            "candidate_id": candidate_id,
            "num_turns": len(topics),
        })

        log_records(records)
        written += len(records)

    return written


def validate_log():
    errors = 0
    total = 0
    if not os.path.exists(LOG_PATH):
        print(f"[prompt_log] {LOG_PATH} does not exist")
        return 0

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                json.loads(line)
            except ValueError:
                errors += 1
                print(f"[prompt_log] invalid JSONL line {total}: {line[:100]}")

    print(f"[prompt_log] {total} lines, {errors} errors")
    return errors


def main():
    print("[prompt_log] backfilling sessions.db into PROMPT.md")
    written = backfill_from_db()
    print(f"[prompt_log] wrote {written} records")
    errors = validate_log()
    if errors:
        raise SystemExit(f"[prompt_log] {errors} invalid lines found")


if __name__ == "__main__":
    main()
