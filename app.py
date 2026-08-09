import json
import os
import sqlite3
import threading
import uuid

import agent
import import_chat
import prompt_log
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="ABTalks AI Interview Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "sessions.db"
_db_lock = threading.Lock()


def init_db():
    with _db_lock, sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                topics       TEXT NOT NULL,
                updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


init_db()


def load_topics(session_id):
    with _db_lock, sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT topics FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def save_topics(session_id, candidate_id, topics):
    with _db_lock, sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            INSERT INTO sessions (session_id, candidate_id, topics)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                topics = excluded.topics,
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, candidate_id, json.dumps(topics))
        )


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class Message(BaseModel):
    role: str
    content: str


class InterviewRequest(BaseModel):
    candidate_id: str
    session_id: Optional[str] = None
    conversation: List[Message] = []


class ImportChatRequest(BaseModel):
    title: Optional[str] = ""
    source: Optional[str] = "microsoft_copilot"
    messages: Optional[List[Message]] = None
    text: Optional[str] = None


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/candidates")
def list_candidates():
    output = []
    for candidate_id, candidate in agent.candidate_map.items():
        member = candidate["member"]
        completed = len(agent.completed_missions(candidate))
        output.append({
            "id": candidate_id,
            "name": member["name"],
            "role": member["jobRole"],
            "yearsExperience": member["yearsExperience"],
            "education": member["education"],
            "completed": completed,
            "weak": agent.weak_days(candidate),
        })
    return {"candidates": output}


@app.post("/api/interview")
def interview(req: InterviewRequest):
    try:
        candidate = agent.get_candidate(req.candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    session_id = req.session_id
    topics = load_topics(session_id) if session_id else None

    if topics is None:
        session_id = str(uuid.uuid4())
        topics = agent.reconstruct_topics(candidate, req.conversation)

    result, topics = agent.next_turn(
        candidate, req.conversation, topics, session_id=session_id
    )

    if result["status"] != "COMPLETED":
        save_topics(session_id, req.candidate_id, topics)

    return {**result, "session_id": session_id}


@app.get("/api/log")
def ai_usage_log():
    records = []
    for line in open(prompt_log.LOG_PATH, "r", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue

    return {
        "records": records,
        "count": len(records),
        "sessions": sum(1 for r in records if r.get("type") == "session_start"),
        "turns": sum(1 for r in records if r.get("type") == "turn"),
        "answers": sum(1 for r in records if r.get("type") == "answer"),
        "llm_calls": sum(1 for r in records if r.get("type") == "llm_call"),
        "external_chats": sum(
            1 for r in records if r.get("type") == "external_chat"
        ),
        "attachments": sum(
            1 for r in records if r.get("type") == "attachment"
        ),
        "completed": sum(
            1 for r in records if r.get("type") == "session_complete"
        ),
        "updated_at": (
            os.path.getmtime(prompt_log.LOG_PATH)
            if os.path.exists(prompt_log.LOG_PATH) else 0
        ),
    }


@app.get("/api/log/download")
def ai_usage_log_download():
    if not os.path.exists(prompt_log.LOG_PATH):
        raise HTTPException(status_code=404, detail="Log not found")
    return FileResponse(
        prompt_log.LOG_PATH,
        media_type="text/plain",
        filename="AI_Usage_Log.txt",
    )


@app.get("/api/usage-log")
def usage_log():
    records = []
    if not os.path.exists(prompt_log.USAGE_LOG_PATH):
        return {"records": [], "count": 0, "models": []}
    for line in open(prompt_log.USAGE_LOG_PATH, "r", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return {
        "records": records,
        "count": len(records),
        "llm_calls": sum(1 for r in records if r.get("type") == "llm_call"),
        "ok": sum(1 for r in records if r.get("ok")),
        "failed": sum(1 for r in records if not r.get("ok")),
        "models": sorted({
            r.get("model") for r in records if r.get("model")
        }),
        "updated_at": (
            os.path.getmtime(prompt_log.USAGE_LOG_PATH)
            if os.path.exists(prompt_log.USAGE_LOG_PATH) else 0
        ),
    }


@app.get("/api/usage-log/download")
def usage_log_download():
    if not os.path.exists(prompt_log.USAGE_LOG_PATH):
        raise HTTPException(status_code=404, detail="Usage log not found")
    return FileResponse(
        prompt_log.USAGE_LOG_PATH,
        media_type="application/json",
        filename="ai_usage_log.json",
    )


@app.post("/api/import-chat")
def import_external_chat(req: ImportChatRequest):
    if req.messages:
        messages = [
            {
                "role": ("user" if m.role == "user" else "assistant"),
                "content": m.content,
            }
            for m in req.messages
            if m.content.strip()
        ]
    elif req.text:
        messages = import_chat.parse_transcript(req.text)
    else:
        raise HTTPException(status_code=422, detail="Provide 'messages' or "
                                                   "'text'")

    record, is_new = import_chat.import_messages(
        req.source or "microsoft_copilot", req.title, messages
    )
    if record is None:
        raise HTTPException(status_code=422, detail="No messages to import")

    return {
        "imported": is_new,
        "num_messages": record["num_messages"],
        "record": record,
    }


app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="frontend"
)
