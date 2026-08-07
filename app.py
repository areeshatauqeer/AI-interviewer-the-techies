import json
import sqlite3
import threading
import uuid

import agent
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

    result, topics = agent.next_turn(candidate, req.conversation, topics)

    if result["status"] != "COMPLETED":
        save_topics(session_id, req.candidate_id, topics)

    return {**result, "session_id": session_id}


app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="frontend"
)
