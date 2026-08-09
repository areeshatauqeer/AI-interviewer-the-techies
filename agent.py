import json
import random

import llm
import prompt_log

MIN_QUESTIONS = 8
MIN_CURRICULUM_DAYS = 4
MAX_QUESTIONS = 12

# On-the-fly performance analysis. Every answer is scored against the
# rubric as the interview runs. A candidate whose running average stays
# below the weak threshold after EARLY_EXIT_MIN_ANSWERS answers is ended
# early with a warm closing message (fewer questions); candidates above
# the bar run the full interview. Matches the feedback engine's
# "needs reinforcement" bar (< 55).
WEAK_SCORE_THRESHOLD = 55
EARLY_EXIT_MIN_ANSWERS = 4

EARLY_EXIT_MESSAGE = (
    "Thanks so much for coming in today — it was great to have you here. "
    "We really appreciate the time you spent with us."
)

with open("curriculum.json", "r", encoding="utf-8") as f:
    curriculum = json.load(f)

with open("candidates.json", "r", encoding="utf-8") as f:
    candidates_data = json.load(f)

day_map = {d["day"]: d for d in curriculum["days"]}
candidate_map = {c["member"]["id"]: c for c in candidates_data["candidates"]}


def get_candidate(candidate_id):
    candidate = candidate_map.get(candidate_id)
    if not candidate:
        raise ValueError(f"Candidate not found: {candidate_id}")
    return candidate


# ------------------------------------------------------------------
# Candidate analysis
# ------------------------------------------------------------------

def completed_missions(candidate):
    return [m for m in candidate["missions"] if m.get("passed")]


def weak_days(candidate):
    weak = []
    for mission in candidate["missions"]:
        if (not mission.get("passed") or
                mission.get("attempts", 0) >= 3):
            weak.append(mission["day"])
    return list(dict.fromkeys(weak))


def build_plan(candidate):
    completed = completed_missions(candidate)
    weak = set(weak_days(candidate))

    completed.sort(
        key=lambda m: (
            m["day"] not in weak,
            -m.get("attempts", 0)
        )
    )

    days = []
    for mission in completed:
        day = mission["day"]
        if day in day_map and day not in days:
            days.append(day)
    return days


def difficulty_level(candidate):
    signals = candidate.get("signals", {})
    first_try = signals.get("missionsFirstTry", 0)
    experience = candidate["member"].get("yearsExperience", 0)

    if first_try >= 26 and experience >= 4:
        return "senior"
    if first_try <= 10 or experience <= 2:
        return "foundational"
    return "standard"


def build_profile_blurb(candidate):
    member = candidate["member"]
    signals = candidate.get("signals", {})
    completed = completed_missions(candidate)
    weak = weak_days(candidate)

    lines = [
        f"Name: {member['name']}",
        f"Role: {member['jobRole']} ({member['yearsExperience']} yrs experience)",
        f"Education: {member['education']}",
        f"Completed missions: {len(completed)}/{len(candidate['missions'])} "
        f"listed; first-try rate: {signals.get('missionsFirstTry', 0)}",
    ]
    if weak:
        lines.append("Weak areas (high attempts or failed): " +
                     ", ".join(f"Day {d}" for d in sorted(weak)))

    return "\n".join(lines)


def first_name(candidate):
    return candidate["member"]["name"].split()[0]


# ------------------------------------------------------------------
# Question generation
# ------------------------------------------------------------------

def is_conceptual(objective):
    low = objective.lower().lstrip()
    return low.startswith((
        "understand", "learn", "know", "the role", "what is",
        "explain", "why", "when"
    ))


FRAMES = {
    "A1": (
        "Let's talk about {title}.\n\n"
        "{objective}\n\n"
        "Walk me through how you'd actually do this in production — "
        "the concrete steps, the tools you'd reach for, and any "
        "decisions you'd have to defend to a senior engineer."
    ),
    "A2": (
        "Next up: {title}.\n\n"
        "{objective}\n\n"
        "Where would this break under real-world conditions, and how "
        "would you design around those failure modes from the start?"
    ),
    "A3": (
        "You've been through {title} in the cohort.\n\n"
        "{objective}\n\n"
        "What design choices are you weighing here, and what tradeoffs "
        "would you accept? Why this path over the alternatives?"
    ),
    "A4": (
        "Let's take {title} and imagine it's heading to production "
        "at real scale.\n\n"
        "{objective}\n\n"
        "What changes about how you'd implement it compared to the "
        "cohort project? What would you measure, and what would you "
        "optimize first?"
    ),
    "A5": (
        "Let's explore {title}.\n\n"
        "{objective}\n\n"
        "Start from the high-level idea and work down to the "
        "implementation details. I want to hear how you reason about "
        "it — no need for a perfect answer."
    ),
    "A6": (
        "Given your background as a {role}, this should be familiar "
        "territory: {title}.\n\n"
        "{objective}\n\n"
        "Walk me through how you'd approach this end-to-end, and "
        "where you'd expect to spend most of your effort."
    ),
    "C1": (
        "Let's talk about {title}.\n\n"
        "{objective}\n\n"
        "Explain this to me as if I'm a new teammate who needs to "
        "build on your work. What are the core ideas, and what's the "
        "most common mistake someone makes here?"
    ),
    "C2": (
        "On {title}, the goal was: {objective}\n\n"
        "Walk me through your mental model here — why does this "
        "matter in a real system, and how does it connect to the "
        "rest of the pipeline we've been discussing?"
    ),
}

FRAME_WEIGHTS = {
    "senior": [("A2", 2), ("A3", 2), ("A4", 2), ("A1", 1), ("A6", 1)],
    "standard": [("A1", 2), ("A2", 1), ("A3", 1), ("A6", 1), ("A5", 1)],
    "foundational": [("A5", 2), ("A1", 2), ("A2", 1)],
}

CONNECTIVES = [
    "Let's switch gears.",
    "Good — moving on.",
    "Let's shift to something different.",
]


def create_opening(day_info, candidate, level, question_number):
    seed = hash((day_info["day"], question_number, candidate["member"]["id"]))
    rng = random.Random(seed & 0xffffffff)

    objectives = day_info["objectives"]
    conceptual = [o for o in objectives if is_conceptual(o)]
    pool = conceptual if conceptual else objectives
    objective = rng.choice(pool)

    if is_conceptual(objective):
        frame = rng.choice(["C1", "C2"])
    else:
        keys = [k for k, _ in FRAME_WEIGHTS[level]]
        weights = [w for _, w in FRAME_WEIGHTS[level]]
        frame = rng.choices(keys, weights=weights)[0]

    body = FRAMES[frame].format(
        title=day_info["title"],
        objective=objective,
        role=candidate["member"]["jobRole"]
    )

    if question_number == 1:
        return f"Alright {first_name(candidate)}, let's get started.\n\n{body}"

    return f"{rng.choice(CONNECTIVES)}\n\n{body}"


CONCEPT_PROBES = [
    (("fine-tun", "qlora", "lora"),
     "You mentioned fine-tuning. When would you reach for fine-tuning "
     "instead of RAG or better prompting — and how would you measure, "
     "concretely, that it was worth the cost and effort?"),
    (("embedding", "sentence-transformers", "sentence transformer"),
     "You mentioned embeddings. If related documents were no longer "
     "clustering together in {day}, how would you diagnose whether the "
     "problem is the embedding model, your chunking, or your similarity "
     "threshold?"),
    (("chromadb", "chroma", "pinecone", "vector db", "vector database", "index"),
     "You mentioned {kw}. In a live system, how do you keep that index "
     "in sync as new data arrives, and how do you balance recall against "
     "latency as it grows?"),
    (("query rout", "hybrid", "retriev", "dedup"),
     "You mentioned {kw}. How would you evaluate the quality of what "
     "gets retrieved, and what do you do in the edge cases where the "
     "wrong context keeps coming back?"),
    (("rag", "ground", "context"),
     "You mentioned {kw}. How do you keep the model grounded so it "
     "doesn't drift outside the retrieved context, and how would you "
     "audit that in production?"),
    (("few-shot", "chain-of-thought", "chain of thought", "prompt"),
     "You mentioned prompting. Walk me through how you'd structure that "
     "prompt to keep answers grounded and consistent — and how would you "
     "react if a user tried to override your instructions?"),
    (("function call", "tool call", "structured output", "pydantic", "schema"),
     "You mentioned {kw}. What happens when the model returns output "
     "that doesn't fit your schema? How would you validate, retry, and "
     "log those failures in production?"),
    (("mcp", "langchain", "langgraph", "crewai", "agent"),
     "You mentioned agents. How do you make sure the agent picks the "
     "right tool at the right moment, and what's your recovery path "
     "when it picks wrong?"),
    (("docker", "kubernetes", "k8s", "container"),
     "You mentioned {kw}. Walk me through deploying this with health "
     "checks and zero-downtime updates — and what would you monitor "
     "first after it ships?"),
    (("evaluat", "benchmark", "regression"),
     "You mentioned {kw}. What specific metrics would you track to "
     "prove this works, and how would you establish a baseline before "
     "you change anything?"),
    (("secur", "injection", "pii", "auth", "guardrail"),
     "You mentioned {kw}. In a system handling sensitive data, what "
     "are the specific attacks you'd defend against — prompt injection, "
     "unauthorized access, data leakage — and what guardrails would you "
     "put in place?"),
    (("latency", "cost", "token", "cache", "performance"),
     "You mentioned {kw}. Where would you expect the biggest cost or "
     "latency hotspot to be, and how would you go about measuring and "
     "then fixing it?"),
    (("stream", "sse", "server-sent"),
     "You mentioned streaming. How do you handle a client that "
     "disconnects mid-response, or a backend that times out? What does "
     "the graceful failure path look like?"),
]

GENERIC_PROBES = [
    "Let's push on that a bit. What are the main tradeoffs in the "
    "approach you just described, and how would you decide between "
    "the alternatives?",
    "Now imagine this needs to handle 10x the load. What breaks first, "
    "and how would you fix it?",
    "If a teammate came to you with an implementation that mostly works "
    "but fails in edge cases, what would you tell them to check first?",
    "How would you prove this actually works? What would you measure "
    "or test before you'd call it production-ready?",
    "Is there an alternative architecture you considered? What made "
    "you settle on this one?",
]

COMMON_TOOLS = {
    "python", "json", "sql", "api", "llm", "llms", "react", "docker",
    "kubernetes", "markdown", "requests", "uuid", "chat", "vector"
}


def create_followup(day_info, last_answer, level, topics_len):
    answer = (last_answer or "").lower()
    words = answer.split()
    seed = hash((day_info["day"], topics_len))
    rng = random.Random(seed & 0xffffffff)
    title = day_info["title"]

    if any(p in answer for p in (
        "i don't know", "i dont know", "not sure", "no idea",
        "i'm not sure", "i have no clue"
    )):
        objective = rng.choice(day_info["objectives"])
        return (
            "That's fine — let's approach it from a different angle.\n\n"
            f"For {title}, one of the core goals was: {objective}\n\n"
            "Given that, how would you begin tackling it? Even a rough "
            "outline helps me see where to guide you."
        )

    if len(words) < 15:
        return (
            "I'd like to see the shape of your approach.\n\n"
            "Could you walk me through it step by step — what would you "
            "do first, and what comes after that? It's okay to be rough; "
            "I'm more interested in how you think."
        )

    for keywords, template in CONCEPT_PROBES:
        for keyword in keywords:
            if keyword in answer:
                return template.format(kw=keyword, day=title)

    tools = [
        t for t in day_info.get("tools", [])
        if t.lower() not in answer
        and len(t) > 3
        and t.lower() not in COMMON_TOOLS
    ]
    if tools:
        tool = rng.choice(tools)
        return (
            f"You didn't mention {tool} — where would it fit in the "
            f"approach you just described, and what would it actually "
            f"be responsible for in your design?"
        )

    return rng.choice(GENERIC_PROBES)


# ------------------------------------------------------------------
# Optional LLM-powered question generation
# ------------------------------------------------------------------

SYSTEM_INTERVIEWER = (
    "You are a senior technical interviewer conducting an adaptive "
    "technical interview for a candidate from the ABTalks AI Cohort "
    "(a 31-day applied AI program covering embeddings, vector search, "
    "RAG, prompting, function calling, agents, MCP, security and "
    "deployment). Sound like a real, sharp but fair human interviewer.\n\n"
    "Rules:\n"
    "1. Ask exactly ONE question per turn. Never list multiple questions.\n"
    "2. The context will tell you the current topic, tools, objectives, "
    "and whether to ask an OPENING or FOLLOW-UP question.\n"
    "3. OPENING: scenario-based; probe real understanding, not memorized "
    "facts. Be specific and applied.\n"
    "4. FOLLOW-UP: react specifically to the candidate's most recent "
    "answer — reference what they actually said (concepts, tools, claims) "
    "and probe deeper: tradeoffs, failure modes, scale, evaluation. Never "
    "ask a generic follow-up.\n"
    "5. Calibrate difficulty to the stated level. Don't be condescending.\n"
    "6. Respond ONLY with valid JSON: {\"question\": \"...\"}.\n"
    "7. Keep each question under ~70 words."
)


def llm_next_question(candidate, conversation, day_info, mode,
                      level, question_number, last_score=None):
    if not llm.available():
        return None

    context = (
        f"INTERVIEW QUESTION #{question_number}\n"
        f"Mode: {'OPENING' if mode == 'opening' else 'FOLLOW-UP'}\n\n"
        f"CANDIDATE PROFILE:\n{build_profile_blurb(candidate)}\n\n"
        f"DIFFICULTY: {level}\n\n"
        f"CURRENT TOPIC — Day {day_info['day']}: {day_info['title']}\n"
        f"Tools: {', '.join(day_info.get('tools', []))}\n"
        f"Objectives: {'; '.join(day_info['objectives'])}\n\n"
    )

    if (mode == "followup" and last_score is not None
            and last_score < WEAK_SCORE_THRESHOLD):
        context += (
            f"NOTE: The candidate's last answer scored {last_score}/100 — "
            "below the passing bar. Keep this follow-up grounded and "
            "concrete, lower the difficulty slightly, and probe the "
            "foundational understanding behind this day's concept.\n\n"
        )

    history = []
    for message in conversation[-8:]:
        role = "user" if message.role == "user" else "assistant"
        history.append({"role": role, "content": message.content})

    messages = [
        {"role": "system", "content": SYSTEM_INTERVIEWER},
        {"role": "user", "content": context},
        *history,
        {"role": "user",
         "content": 'Generate the next question as JSON: {"question": "..."}'}
    ]

    data = llm.chat_json(messages, temperature=0.8, max_tokens=300)
    prompt_log.log_record({
        "type": "llm_call",
        "kind": "question",
        "timestamp": prompt_log.now(),
        "candidate_id": candidate["member"]["id"],
        "mode": mode,
        "day": day_info["day"],
        "level": level,
        "question_number": question_number,
        "messages": messages,
        "raw_output": data,
    })
    if not data or not data.get("question"):
        return None

    question = str(data["question"]).strip().strip('"')
    return question or None


# ------------------------------------------------------------------
# Interview orchestration
# ------------------------------------------------------------------

def next_turn(candidate, conversation, topics, session_id=None):
    answers = [m.content for m in conversation if m.role == "user"]

    for index, topic in enumerate(topics):
        topic["answer"] = answers[index] if index < len(answers) else None

    for index, topic in enumerate(topics, 1):
        answer = topic.get("answer")
        if answer and not topic.get("logged_answer"):
            topic["logged_answer"] = True
            prompt_log.log_record({
                "type": "answer",
                "timestamp": prompt_log.now(),
                "session_id": session_id,
                "candidate_id": candidate["member"]["id"],
                "turn": index,
                "day": topic.get("day"),
                "mode": topic.get("mode"),
                "question": topic.get("question"),
                "answer": answer,
            })

    asked_count = len(topics)
    covered_days = sorted({t["day"] for t in topics})

    if (asked_count >= MIN_QUESTIONS and
            len(set(covered_days)) >= MIN_CURRICULUM_DAYS):
        feedback = generate_feedback(candidate, topics, covered_days)
        prompt_log.log_record({
            "type": "session_complete",
            "timestamp": prompt_log.now(),
            "session_id": session_id,
            "candidate_id": candidate["member"]["id"],
            "feedback": feedback,
        })
        return (
            {"status": "COMPLETED", "feedback": feedback},
            topics
        )

    if topics and topics[-1]["answer"] is None:
        return ({"status": "WAITING_FOR_ANSWER"}, topics)

    plan = build_plan(candidate)
    if not plan:
        raise ValueError("Candidate has no completed missions to assess")

    # Score every answer so far and track the running average. If the
    # candidate is consistently below the weak threshold, end the
    # interview early instead of running them through all 8 questions.
    scores = []
    last_score = None
    for topic in topics:
        if topic.get("answer"):
            topic["score"] = score_answer_rubric(topic)["score"]
            scores.append(topic["score"])
    avg_score = (sum(scores) / len(scores)) if scores else None
    if topics and topics[-1].get("score") is not None:
        last_score = topics[-1]["score"]

    if (avg_score is not None
            and len(scores) >= EARLY_EXIT_MIN_ANSWERS
            and avg_score < WEAK_SCORE_THRESHOLD):
        feedback = early_exit_feedback(candidate, topics, scores)
        prompt_log.log_record({
            "type": "session_complete",
            "timestamp": prompt_log.now(),
            "session_id": session_id,
            "candidate_id": candidate["member"]["id"],
            "early_exit": True,
            "avg_score": avg_score,
            "feedback": feedback,
        })
        return (
            {"status": "COMPLETED", "early_exit": True, "feedback": feedback},
            topics
        )

    if not topics:
        day, mode = plan[0], "opening"
    else:
        last = topics[-1]
        if last["mode"] == "opening":
            day, mode = last["day"], "followup"
        else:
            day = _next_plan_day(plan, covered_days, asked_count)
            mode = "opening"

    day_info = day_map[day]
    level = difficulty_level(candidate)
    question_number = asked_count + 1

    question = None
    if llm.available():
        question = llm_next_question(
            candidate, conversation, day_info, mode, level,
            question_number, last_score=last_score
        )

    if not question:
        if mode == "opening":
            question = create_opening(
                day_info, candidate, level, question_number
            )
        else:
            question = create_followup(
                day_info, topics[-1]["answer"] or "", level, asked_count
            )

    topics.append({
        "day": day,
        "mode": mode,
        "question": question,
        "answer": None
    })

    prompt_log.log_record({
        "type": "turn",
        "timestamp": prompt_log.now(),
        "session_id": session_id,
        "candidate_id": candidate["member"]["id"],
        "day": day,
        "mode": mode,
        "question": question,
    })

    return (
        {
            "status": "IN_PROGRESS",
            "question_number": question_number,
            "question": question,
            "mode": mode,
            "day_title": day_info["title"],
            "covered_days": sorted({t["day"] for t in topics}),
            "remaining_questions": max(
                MIN_QUESTIONS - question_number, 0
            ),
        },
        topics
    )


def _next_plan_day(plan, covered_days, asked_count):
    for day in plan:
        if day not in covered_days:
            return day
    return plan[asked_count % len(plan)]


def reconstruct_topics(candidate, conversation):
    """Rebuild a lightweight topic list when session state is lost."""
    plan = build_plan(candidate)
    questions = [m for m in conversation if m.role == "assistant"]

    topics = []
    for index, message in enumerate(questions):
        if index % 2 == 0:
            day = plan[min(index // 2, len(plan) - 1)]
            mode = "opening"
        else:
            day = topics[-1]["day"]
            mode = "followup"
        topics.append({
            "day": day,
            "mode": mode,
            "question": message.content,
            "answer": None
        })
    return topics


# ------------------------------------------------------------------
# Feedback engine
# ------------------------------------------------------------------

SYSTEM_FEEDBACK = (
    "You are an expert interviewer coach. Given a transcript of a "
    "technical interview for the ABTalks AI Cohort, produce structured, "
    "actionable feedback that a hiring manager can act on.\n\n"
    "Each candidate answer was already scored against a rubric, and the "
    "scorecard shows exactly how many points were awarded per dimension. "
    "Use those scores as ground truth — do not contradict them.\n"
    'Rubric dimensions: relevance (0-20), reasoning & tradeoffs (0-30), '
    'concrete depth (0-20), production awareness (0-15), evaluation & '
    'metrics (0-15).\n'
    'Return ONLY JSON: {"strengths": ["...", ...up to 4], "improvements": '
    '["...", ...up to 5], "summary": "1-2 sentences"}\n'
    "Base strengths and improvements on scorecard evidence — quote what "
    "the candidate actually said when useful. Improvements must be "
    "specific and actionable — reference concrete skills or habits to "
    "change. Do not invent topics that were not covered."
)

# Explainable rubric. Each dimension maps a candidate answer back to
# observable signals so a hiring manager can see exactly why points were
# awarded (or withheld) for a specific technical explanation.
RUBRIC = [
    {"key": "relevance", "label": "Relevance & coverage", "max": 20,
     "desc": "Addresses the question and covers the day's tools and objectives."},
    {"key": "reasoning", "label": "Reasoning & tradeoffs", "max": 30,
     "desc": "Explains why, weighs tradeoffs and alternatives, shows engineering judgment."},
    {"key": "depth", "label": "Concrete depth", "max": 20,
     "desc": "Provides specific steps, implementation detail, and structure."},
    {"key": "production", "label": "Production awareness", "max": 15,
     "desc": "Considers failure modes, scaling, deployment, monitoring, security."},
    {"key": "evaluation", "label": "Evaluation & metrics", "max": 15,
     "desc": "References how to measure, test, benchmark, or baseline the solution."},
]

RUBRIC_MAX = sum(d["max"] for d in RUBRIC)

REASONING_MARKERS = [
    "because", "tradeoff", "however", "alternative", "would", "if",
    "depends", "consider", "weigh", "versus", "instead", "but",
    "compare", "justify", "decide",
]

DEPTH_MARKERS = [
    "first", "then", "next", "finally", "step", "approach",
    "implement", "build", "design", "create", "configure",
]

PRODUCTION_MARKERS = [
    "docker", "kubernetes", "k8s", "container", "deploy", "monitor",
    "scale", "fail", "failure", "retry", "timeout", "time out",
    "disconnect", "latency", "cache", "health check", "load balanc",
    "secure", "security", "auth", "injection", "pii", "guardrail",
    "zero-downtime", "production",
]

EVALUATION_MARKERS = [
    "measure", "evaluate", "metric", "benchmark", "test", "baseline",
    "track", "quantify", "regression", "accuracy", "precision", "recall",
    "validat",
]

HESITATION_MARKERS = [
    "i don't know", "i dont know", "not sure", "no idea",
    "i'm not sure", "i have no clue",
]


def _hits(text, markers):
    return [m for m in markers if m in text]


def score_answer_rubric(topic):
    """Score one question/answer pair against the rubric, with an
    audit trail of exactly why each dimension's points were awarded."""
    day_info = day_map[topic["day"]]
    answer = topic.get("answer") or ""
    low = answer.lower()
    word_count = len(answer.split())

    if not answer.strip():
        return {
            "day": topic["day"],
            "title": day_info["title"],
            "mode": topic["mode"],
            "question": topic["question"],
            "answer": "",
            "score": 0,
            "dimensions": [
                {"key": d["key"], "label": d["label"], "score": 0,
                 "max": d["max"], "reason": "No answer provided."}
                for d in RUBRIC
            ],
            "comment": "No answer recorded for this question.",
        }

    # Relevance & coverage (0-20)
    tools = [
        t for t in day_info.get("tools", [])
        if t.lower() in low and t.lower() not in COMMON_TOOLS
    ]
    rel = 6 + (10 if word_count >= 8 else 4) + min(len(tools) * 3, 8)
    rel = min(rel, 20)
    if tools:
        rel_reason = (
            "Directly addressed the question and covered the day's core "
            f"tool(s): {', '.join(tools)}."
        )
    else:
        rel_reason = (
            "Addressed the question but referenced none of the day's "
            "core tools or objectives."
        )

    # Reasoning & tradeoffs (0-30)
    hesitating = any(m in low for m in HESITATION_MARKERS)
    reas = _hits(low, REASONING_MARKERS)
    if hesitating:
        reasoning = 0
        reas_reason = (
            "Answer defers (\"not sure / don't know\") — no reasoning or "
            "tradeoff discussion."
        )
    elif word_count < 15:
        reasoning = 4
        reas_reason = (
            f"Answer too brief ({word_count} words) to demonstrate "
            "reasoning or tradeoffs."
        )
    else:
        reasoning = min(10 + len(reas) * 4, 30)
        if reas:
            reas_reason = (
                "Showed reasoning/tradeoff thinking "
                f"({len(reas)} signals): {', '.join(reas[:4])}."
            )
        else:
            reas_reason = (
                "Answer is descriptive rather than argued — no tradeoffs, "
                "alternatives, or 'why' behind the choices."
            )

    # Concrete depth (0-20)
    seq = _hits(low, DEPTH_MARKERS)
    depth = 3
    if word_count >= 15:
        depth += 3
    if word_count >= 40:
        depth += 4
    depth += min(len(seq) * 3, 9)
    depth = min(depth, 20)
    if word_count >= 15 and seq:
        depth_reason = (
            f"Structured, detailed answer ({word_count} words) with "
            f"concrete steps ({', '.join(seq[:3])})."
        )
    elif word_count < 15:
        depth_reason = (
            f"Answer is brief ({word_count} words) — little "
            "implementation detail."
        )
    else:
        depth_reason = (
            f"Lengthy answer ({word_count} words) but lacks explicit "
            "steps or sequence."
        )

    # Production awareness (0-15)
    prod = _hits(low, PRODUCTION_MARKERS)
    production = min(len(prod) * 4, 15)
    if prod:
        prod_reason = (
            "Showcased production thinking "
            f"({len(prod)} signals): {', '.join(prod[:4])}."
        )
    else:
        prod_reason = (
            "No production or failure-mode considerations — deployment, "
            "scaling, monitoring, or security all absent."
        )

    # Evaluation & metrics (0-15)
    ev = _hits(low, EVALUATION_MARKERS)
    if ev:
        evaluation = min(4 + len(ev) * 4, 15)
        eval_reason = (
            "References concrete evaluation "
            f"({len(ev)} signals): {', '.join(ev[:4])}."
        )
    else:
        evaluation = 0
        eval_reason = (
            "No metrics or evaluation plan — the answer never states how "
            "the solution would be measured."
        )

    dims = [
        {"key": "relevance", "label": "Relevance & coverage",
         "score": rel, "max": 20, "reason": rel_reason},
        {"key": "reasoning", "label": "Reasoning & tradeoffs",
         "score": reasoning, "max": 30, "reason": reas_reason},
        {"key": "depth", "label": "Concrete depth",
         "score": depth, "max": 20, "reason": depth_reason},
        {"key": "production", "label": "Production awareness",
         "score": production, "max": 15, "reason": prod_reason},
        {"key": "evaluation", "label": "Evaluation & metrics",
         "score": evaluation, "max": 15, "reason": eval_reason},
    ]

    total = min(sum(d["score"] for d in dims), 100)

    ratios = sorted(dims, key=lambda d: d["score"] / d["max"], reverse=True)
    strong = ratios[0]
    weak = [d for d in ratios if d["score"] / d["max"] < 0.4]

    comment = (
        f"Awarded {total}/100 — strongest on "
        f"{strong['label'].lower()} ({strong['score']}/{strong['max']})."
    )
    if weak:
        weakest = weak[0]
        comment += (
            f" Lost the most points on {weakest['label'].lower()} "
            f"({weakest['score']}/{weakest['max']})."
        )
    comment += " " + ratios[-1]["reason"]

    return {
        "day": topic["day"],
        "title": day_info["title"],
        "mode": topic["mode"],
        "question": topic["question"],
        "answer": answer,
        "score": total,
        "dimensions": dims,
        "comment": comment,
    }


def build_transcript(topics):
    lines = []
    for index, topic in enumerate(topics, 1):
        lines.append(
            f"Q{index} ({topic['mode']} · Day {topic['day']}): "
            f"{topic['question']}"
        )
        if topic.get("answer"):
            lines.append(f"A{index}: {topic['answer']}")
    return "\n".join(lines)


def early_exit_feedback(candidate, topics, scores):
    """Warm, short feedback for a candidate who is ended early because
    their answers stayed below the weak threshold."""
    return {
        "candidate": candidate["member"]["name"],
        "overall_score": int(sum(scores) / len(scores)),
        "verdict": "needs reinforcement",
        "borderline": False,
        "early_exit": True,
        "summary": (
            f"{EARLY_EXIT_MESSAGE} We're wrapping up the session a bit "
            "early, but every conversation helps us improve the program."
        ),
        "strengths": [
            "Showed up and engaged with the interview questions"
        ],
        "improvements": [],
        "topics": {},
        "rubric": [],
        "scorecard": [],
        "transcript": "",
    }


def generate_feedback(candidate, topics, covered_days):
    answered = [t for t in topics if t.get("answer")]
    scorecards = [score_answer_rubric(t) for t in answered]

    day_scores = {}
    for topic, card in zip(answered, scorecards):
        day_scores.setdefault(topic["day"], []).append(card["score"])
    day_scores = {
        day: int(sum(values) / len(values))
        for day, values in day_scores.items()
    }

    all_scores = [card["score"] for card in scorecards]
    overall = int(sum(all_scores) / len(all_scores)) if all_scores else 50

    if len(covered_days) >= MIN_CURRICULUM_DAYS:
        overall = min(
            overall + min(len(covered_days) - MIN_CURRICULUM_DAYS, 2) * 2,
            100
        )
    if len(all_scores) >= 2 and max(all_scores) - min(all_scores) >= 50:
        overall = max(overall - 5, 0)

    if overall >= 75:
        verdict = "strong"
    elif overall >= 55:
        verdict = "developing"
    else:
        verdict = "needs reinforcement"

    narrative = None
    if llm.available():
        narrative = llm_feedback(candidate, topics, scorecards, overall)
    if not narrative:
        narrative = heuristic_feedback(candidate, topics, day_scores, overall)

    return {
        "candidate": candidate["member"]["name"],
        "overall_score": overall,
        "verdict": verdict,
        "borderline": 55 <= overall < 75,
        "strengths": narrative["strengths"],
        "improvements": narrative["improvements"],
        "summary": narrative["summary"],
        "topics": {
            f"day_{day}": {"title": day_map[day]["title"], "score": score}
            for day, score in sorted(day_scores.items())
        },
        "rubric": RUBRIC,
        "scorecard": scorecards,
        "transcript": build_transcript(topics),
    }


def llm_feedback(candidate, topics, scorecards, overall):
    lines = []
    for card in scorecards:
        lines.append(
            f"Interviewer (Day {card['day']}, {card['mode']}): "
            f"{card['question']}"
        )
        if card.get("answer"):
            lines.append(f"Candidate: {card['answer']}")
        dims = " | ".join(
            f"{d['label']} {d['score']}/{d['max']}"
            for d in card["dimensions"]
        )
        lines.append(f"Scorecard: {card['score']}/100 ({dims})")
    transcript = "\n".join(lines)

    member = candidate["member"]
    messages = [
        {"role": "system", "content": SYSTEM_FEEDBACK},
        {"role": "user",
         "content":
             f"CANDIDATE: {member['name']}, {member['jobRole']} "
             f"({member['yearsExperience']} yrs)\n"
             f"OVERALL SCORE: {overall}/100\n\n"
             f"TRANSCRIPT WITH SCORECARDS:\n{transcript}"}
    ]

    data = llm.chat_json(messages, temperature=0.3, max_tokens=800)
    prompt_log.log_record({
        "type": "llm_call",
        "kind": "feedback",
        "timestamp": prompt_log.now(),
        "candidate_id": candidate["member"]["id"],
        "messages": messages,
        "raw_output": data,
    })
    if not data:
        return None

    strengths = [str(s) for s in (data.get("strengths") or [])][:4]
    improvements = [str(i) for i in (data.get("improvements") or [])][:5]
    summary = str(data.get("summary") or "")

    if not strengths and not improvements and not summary:
        return None

    return {
        "strengths": strengths,
        "improvements": improvements,
        "summary": summary,
    }


def heuristic_feedback(candidate, topics, day_scores, overall):
    strengths, improvements = [], []

    strong = sorted(day_scores.items(), key=lambda kv: -kv[1])[:2]
    for day, score in strong:
        if score >= 68:
            strengths.append(
                f"Strong grasp of {day_map[day]['title']} (score {score}) — "
                "answered with concrete implementation detail"
            )

    if not strengths and overall >= 55:
        strengths.append(
            "Consistent, engaged responses throughout the interview"
        )
    if not strengths:
        strengths.append(
            "Showed persistence and willingness to engage with "
            "challenging topics"
        )

    weak = sorted(day_scores.items(), key=lambda kv: kv[1])[:2]
    for day, score in weak:
        if score < 60:
            improvements.append(
                f"Deepen your command of {day_map[day]['title']} "
                f"(score {score}): walk through concrete steps and weigh "
                "tradeoffs explicitly"
            )

    answer_text = " ".join(t["answer"] for t in topics).lower()

    if "tradeoff" not in answer_text:
        improvements.append(
            "Discuss tradeoffs and alternatives explicitly — interviewers "
            "look for judgment, not just correctness"
        )
    if not any(k in answer_text for k in
               ("metric", "evaluate", "measure", "latency", "monitor")):
        improvements.append(
            "Reference how you would measure or evaluate your solution — "
            "metrics show production thinking"
        )
    if overall < 55:
        improvements.append(
            "Structure answers as: approach → implementation → tradeoffs → "
            "evaluation. This scaffolding improves clarity and depth"
        )

    if overall >= 75:
        verdict = "strong"
    elif overall >= 55:
        verdict = "developing"
    else:
        verdict = "needs reinforcement"

    summary = (
        f"Interview covered {len(topics)} questions across "
        f"{len(day_scores)} curriculum days "
        f"(days {sorted(day_scores)}). "
        f"Overall understanding is {verdict}: "
        + ("solid grasp of core concepts demonstrated"
           if overall >= 75
           else "core ideas are present but depth is inconsistent"
           if overall >= 55
           else "fundamental concepts require review")
        + "."
    )

    return {
        "strengths": strengths[:3],
        "improvements": improvements[:4],
        "summary": summary,
    }
