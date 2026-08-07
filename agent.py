import json
import random

import llm

MIN_QUESTIONS = 8
MIN_CURRICULUM_DAYS = 4
MAX_QUESTIONS = 12

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
                      level, question_number):
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
    if not data or not data.get("question"):
        return None

    question = str(data["question"]).strip().strip('"')
    return question or None


# ------------------------------------------------------------------
# Interview orchestration
# ------------------------------------------------------------------

def next_turn(candidate, conversation, topics):
    answers = [m.content for m in conversation if m.role == "user"]

    for index, topic in enumerate(topics):
        topic["answer"] = answers[index] if index < len(answers) else None

    asked_count = len(topics)
    covered_days = sorted({t["day"] for t in topics})

    if (asked_count >= MIN_QUESTIONS and
            len(set(covered_days)) >= MIN_CURRICULUM_DAYS):
        feedback = generate_feedback(candidate, topics, covered_days)
        return (
            {"status": "COMPLETED", "feedback": feedback},
            topics
        )

    if topics and topics[-1]["answer"] is None:
        return ({"status": "WAITING_FOR_ANSWER"}, topics)

    plan = build_plan(candidate)
    if not plan:
        raise ValueError("Candidate has no completed missions to assess")

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
            candidate, conversation, day_info, mode, level, question_number
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
    "actionable feedback.\n"
    'Return ONLY JSON: {"overall_score": <int 0-100>, "strengths": '
    '["...", ...up to 4], "improvements": ["...", ...up to 5], '
    '"summary": "1-2 sentences", "topics": {"day_7": <int>, ...}}\n'
    "Base the score on technical depth, breadth across curriculum days, "
    "clarity of explanation, and engineering judgment (tradeoffs, "
    "evaluation, failure modes). Improvements must be specific and "
    "actionable — reference concrete skills or habits to change. Do not "
    "invent topics that were not covered."
)

DEPTH_MARKERS = [
    "tradeoff", "latency", "failure", "because", "would", "scale",
    "measure", "evaluate", "monitor", "alternative", "however",
    "for example", "first", "then", "if",
]


def score_topic(topic):
    answer = (topic.get("answer") or "").lower()
    words = answer.split()

    score = 0
    if len(words) >= 15:
        score += 25
    if len(words) >= 40:
        score += 25

    depth = sum(1 for marker in DEPTH_MARKERS if marker in answer)
    score += min(depth * 7, 30)

    tools = day_map[topic["day"]].get("tools", [])
    mentioned = sum(1 for tool in tools if tool.lower() in answer)
    score += min(mentioned * 5, 15)

    return min(score, 100)


def generate_feedback(candidate, topics, covered_days):
    if llm.available():
        feedback = llm_feedback(candidate, topics)
        if feedback:
            return feedback
    return heuristic_feedback(candidate, topics, covered_days)


def llm_feedback(candidate, topics):
    lines = []
    for topic in topics:
        lines.append(
            f"Interviewer (Day {topic['day']}, {topic['mode']}): "
            f"{topic['question']}"
        )
        if topic.get("answer"):
            lines.append(f"Candidate: {topic['answer']}")
    transcript = "\n".join(lines)

    member = candidate["member"]
    messages = [
        {"role": "system", "content": SYSTEM_FEEDBACK},
        {"role": "user",
         "content":
             f"CANDIDATE: {member['name']}, {member['jobRole']} "
             f"({member['yearsExperience']} yrs)\n\nTRANSCRIPT:\n{transcript}"}
    ]

    data = llm.chat_json(messages, temperature=0.3, max_tokens=800)
    if not data:
        return None

    try:
        score = max(0, min(100, int(data.get("overall_score", 50))))
    except (TypeError, ValueError):
        score = 50

    strengths = [str(s) for s in (data.get("strengths") or [])][:4]
    improvements = [str(i) for i in (data.get("improvements") or [])][:5]
    summary = str(data.get("summary") or "")
    topics_out = data.get("topics") or {}

    return {
        "candidate": member["name"],
        "overall_score": score,
        "strengths": strengths,
        "improvements": improvements,
        "summary": summary,
        "topics": topics_out,
    }


def heuristic_feedback(candidate, topics, covered_days):
    member = candidate["member"]
    answered = [t for t in topics if t.get("answer")]

    day_scores = {}
    for topic in answered:
        day_scores.setdefault(topic["day"], []).append(score_topic(topic))

    day_scores = {
        day: int(sum(values) / len(values))
        for day, values in day_scores.items()
    }

    all_scores = [score_topic(t) for t in answered]

    average = (
        int(sum(all_scores) / len(all_scores))
        if all_scores else 50
    )

    breadth = len(covered_days)
    if breadth >= MIN_CURRICULUM_DAYS:
        average = min(
            average + min(breadth - MIN_CURRICULUM_DAYS, 2) * 2, 100
        )

    if len(all_scores) >= 2:
        spread = max(all_scores) - min(all_scores)
        if spread >= 50:
            average = max(average - 5, 0)

    strengths, improvements = [], []

    strong = sorted(day_scores.items(), key=lambda kv: -kv[1])[:2]
    for day, score in strong:
        if score >= 68:
            strengths.append(
                f"Strong grasp of {day_map[day]['title']} (score {score}) — "
                "answered with concrete implementation detail"
            )

    if not strengths and average >= 55:
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

    answer_text = " ".join(t["answer"] for t in answered).lower()

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
    if average < 55:
        improvements.append(
            "Structure answers as: approach → implementation → tradeoffs → "
            "evaluation. This scaffolding improves clarity and depth"
        )

    if average >= 75:
        verdict = "strong"
    elif average >= 55:
        verdict = "developing"
    else:
        verdict = "needs reinforcement"

    summary = (
        f"Interview covered {len(topics)} questions across "
        f"{len(covered_days)} curriculum days "
        f"(days {sorted(covered_days)}). "
        f"Overall understanding is {verdict}: "
        + ("solid grasp of core concepts demonstrated"
           if average >= 75
           else "core ideas are present but depth is inconsistent"
           if average >= 55
           else "fundamental concepts require review")
        + "."
    )

    return {
        "candidate": member["name"],
        "overall_score": average,
        "strengths": strengths[:3],
        "improvements": improvements[:4],
        "summary": summary,
        "topics": {
            f"day_{day}": score
            for day, score in sorted(day_scores.items())
        },
    }
