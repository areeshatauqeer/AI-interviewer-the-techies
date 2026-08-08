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

## Minimum requirements coverage

- Conversational technical interview — adaptive question engine
- ≥ 8 questions covering ≥ 4 curriculum days — enforced by planner
- Follow-ups based on previous responses — answer-aware probing
- Conversation context maintained — per-session state + history
- Structured feedback at the end — score, strengths, improvements
- Required HTTP endpoint — `POST /api/interview`
