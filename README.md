# ABTalks AI Interview Agent

An adaptive, multi-turn AI technical interview agent built for candidates of a 31-day AI Cohort. The system evaluates candidate responses to curriculum concepts, asks dynamic follow-up questions, preserves conversation context, and delivers structured, actionable evaluations.

🔗 **Live Demo:** [https://abtalks-ai-interview-agent-8w7b.onrender.com](https://abtalks-ai-interview-agent-8w7b.onrender.com)

---

## Key Features

- **Adaptive Question Planner:** Generates an 8+ question interview covering at least 4 curriculum days, prioritizing candidate weak areas (failed missions or high attempt counts).
- **Context-Aware Follow-ups:** Alternates between scenario-based opening questions and intelligent follow-ups probing candidate choices, tradeoffs, and failure modes.
- **Two Interview Modes:**
  - **Chat UI (`/`):** Classic turn-based text interface.
  - **Voice UI (`/voice.html`):** Hands-free, spoken interview with speech synthesis and the Web Speech API (Chrome/Edge).
- **Structured Feedback:** Delivers an overall score (0–100), key strengths, areas for improvement, and per-topic breakdowns.
- **Built-in Compliance & AI Logging:** Automatically logs all prompts, LLM generations, and sessions to `PROMPT.md` and `ai_usage_log.json` with a live visualizer at `/log.html`.
- **Hybrid Engine:** Runs out-of-the-box using a heuristic engine, with seamless fallback support for real LLMs (OpenAI, Groq, Ollama).

---

## Quick Start

### Prerequisites
- Python 3.10+ (Python 3.13 recommended)

### Local Setup

1. **Clone the repository and set up a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
