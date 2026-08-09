"""Backfill past opencode sessions from ~/.local/share/opencode/opencode.db
into PROMPT.md as external_chat records.

Usage:
    python3 backfill_opencode.py
"""
import json
import os
import sqlite3
import sys

import import_chat
import prompt_log

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")


def extract_parts(parts):
    out = []
    for part in parts:
        data = json.loads(part[0])
        ptype = data.get("type")
        if ptype == "text":
            text = (data.get("text") or "").strip()
            if text and not data.get("synthetic"):
                out.append(text)
        elif ptype == "tool":
            state = data.get("state") or {}
            out.append(f"[tool: {data.get('tool')} {state.get('status')}]".strip())
    return "\n".join(out).strip()


def main():
    if not os.path.exists(DB_PATH):
        print(f"[backfill] opencode db not found at {DB_PATH}")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    sessions = cur.execute(
        "SELECT id, title, time_created FROM session ORDER BY time_created"
    ).fetchall()

    total = 0
    for sid, title, tcreated in sessions:
        message_rows = cur.execute(
            "SELECT id, data FROM message WHERE session_id=? "
            "ORDER BY time_created, id",
            (sid,),
        ).fetchall()
        messages = []
        for mid, mdata in message_rows:
            info = json.loads(mdata)
            part_rows = cur.execute(
                "SELECT data FROM part WHERE message_id=? ORDER BY time_created, id",
                (mid,),
            ).fetchall()
            content = extract_parts(part_rows)
            if not content:
                continue
            role = "user" if info.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": content})
        if not messages:
            continue
        record, is_new = import_chat.import_messages(
            "opencode", title, messages, session_id=sid
        )
        if is_new:
            total += 1
            print(f"[backfill] imported '{title}' ({len(messages)} messages)")
        else:
            print(f"[backfill] skipped existing '{title}'")

    conn.close()
    print(f"[backfill] {total} new record(s) written")


if __name__ == "__main__":
    main()
