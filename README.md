# ABTalks AI Interview Agent

An AI agent that conducts a realistic, adaptive, multi-turn technical
interview for candidates of a 31-day AI Cohort. It assesses each
candidate's understanding of the curriculum concepts they completed,
asks intelligent follow-ups that react to their actual answers, keeps
full conversation context, and produces structured, actionable feedback.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
```

Open http://127.0.0.1:8000

## Two interview environments

- **Chatbot (text)** — http://127.0.0.1:8000 — the classic chat UI. Shay greets
  the candidate with a short intro, then runs the interview as chat bubbles.
- **Voice (face-to-face)** — http://127.0.0.1:8000/voice.html — Shay walks in,
  sits across from the candidate in an office scene, and conducts a hands-free
  spoken interview. She reads questions aloud (human-paced, with sighs),
  listens to answers via the Web Speech API, and shows a score ring on
  completion. Requires Chrome or Edge.

A "Voice interview" button in the chatbot's corner links to the voice room.

## How the agent works

1. **Planner** — builds an ordered interview plan from the candidate's
   completed missions, prioritizing weak areas (high attempts or failed
   missions) while ensuring coverage of at least 4 distinct curriculum
   days and 8 questions.
2. **Adaptive questioning** — every turn alternates between an opening
   question (scenario-based, calibrated to the candidate's difficulty
   level) and a follow-up that reacts to the candidate's previous answer
   (probes tools they mentioned, failure modes, tradeoffs, scale,
   evaluation).
3. **Context** — full conversation is maintained server-side per session
   (SQLite) and echoed by the client, so the agent stays coherent across
   the entire interview.
4. **Feedback** — on completion, produces an overall score (0–100),
   strengths, actionable improvements, a summary, and per-day topic
   scores.

### Optional LLM integration

The agent runs out-of-the-box with a built-in heuristic engine. To
upgrade question generation and feedback to a real LLM, configure one of:

| Provider | Env vars |
| --- | --- |
| OpenAI | `LLM_PROVIDER=openai`, `OPENAI_API_KEY` |
| Groq | `LLM_PROVIDER=groq`, `GROQ_API_KEY` |
| Ollama (local) | `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL` (default `http://localhost:11434`) |

Optional: `LLM_MODEL` overrides the default model.
If the LLM is unavailable or misbehaves, the agent falls back to the
heuristic engine automatically.

## API contract

### `POST /api/interview`

Conducts one turn of the interview. Pass the full conversation so far.

Request:

```json
{
  "candidate_id": "CAND-003",
  "session_id": "optional; omit to start a new interview",
  "conversation": [
    { "role": "assistant", "content": "First question..." },
    { "role": "user", "content": "The candidate's answer..." }
  ]
}
```

Responses:

In progress:

```json
{
  "status": "IN_PROGRESS",
  "session_id": "uuid",
  "question_number": 3,
  "question": "The next interview question...",
  "mode": "followup",
  "day_title": "Prompt Engineering Fundamentals",
  "covered_days": [7, 8],
  "remaining_questions": 5
}
```

Waiting for answer (when the last message is from the assistant):

```json
{ "status": "WAITING_FOR_ANSWER", "session_id": "uuid" }
```

Completed (after ≥ 8 questions across ≥ 4 days):

```json
{
  "status": "COMPLETED",
  "session_id": "uuid",
  "feedback": {
    "candidate": "Emily Chen",
    "overall_score": 84,
    "strengths": ["..."],
    "improvements": ["..."],
    "summary": "...",
    "topics": { "day_7": { "title": "Prompt Engineering Fundamentals", "score": 88 } }
  }
}
```

### `GET /api/candidates`

Returns candidate profiles for the interview UI.

### `GET /api/health`

Health check.

## AI Usage Log

Every prompt and output is recorded to `PROMPT.md` (JSON lines) and is
accessible through the app — satisfying the "AI Usage Log must be
included and accessible" requirement.

**View it live:**
- `http://127.0.0.1:8000/log.html` — human-readable log page (filter by
  interviews, LLM calls, or imported chats) with a download button.
- `GET /api/log` — full log as JSON.
- `GET /api/log/download` — downloads the raw log as `AI_Usage_Log.txt`.
- `PROMPT.md` — the underlying JSON-lines file.

**Compliance file (`ai_usage_log.json`):**
- Every single LLM call is automatically appended to `ai_usage_log.json`
  (JSON lines) in the project root with a timestamp, model name, provider,
  the full prompt (`messages`), the raw model response, and an `ok` /
  `error` status — including failed calls.
- `GET /api/usage-log` — the compliance log as JSON (counts + models used).
- `GET /api/usage-log/download` — downloads `ai_usage_log.json`.
- Model names also appear on each `llm_call` record in `PROMPT.md` and on
  the log page.

**What gets logged automatically:**
- `session_start` / `turn` (question) / `answer` / `session_end` — every
  interview, including past sessions backfilled from `sessions.db`.
- `llm_call` — full prompt messages + raw response (with model name) for
  LLM-powered question generation and feedback.
- `session_complete` — final feedback (score, strengths, improvements).

**Importing chats from other AIs (e.g. Microsoft Copilot):**
- CLI: `python3 -m import_chat <file.json|transcript.txt> --title "..."`
- Web: open `/log.html` → **+ Import chat** and paste the conversation.
- Both accept JSON (`[{role, content}, ...]` or an object with a
  `messages` key) or plain-text transcripts (`You:` / `Copilot:`
  markers). Duplicate chats are skipped.
- Re-sync missing start/end markers anytime: `python3 -m prompt_log`.

**Automatically capturing opencode chats:**
- A plugin (`.opencode/plugin/opencode-chatlog.ts`) records every opencode
  session to `PROMPT.md` as an `external_chat` record (one record per
  session, kept up to date). Restart opencode after any change to the
  plugin.
- Past opencode sessions can be backfilled from the local database:
  `python3 backfill_opencode.py`.

## Minimum requirements coverage

- Conversational technical interview — adaptive question engine
- ≥ 8 questions covering ≥ 4 curriculum days — enforced by planner
- Follow-ups based on previous responses — answer-aware probing
- Conversation context maintained — per-session state + history
- Structured feedback at the end — score, strengths, improvements
- Required HTTP endpoint — `POST /api/interview`
