from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
import json
import random

app = FastAPI(title="ABTalks AI Interview Agent")

# ------------------------------------
# Load Curriculum + Candidates
# ------------------------------------

with open("curriculum.json", "r", encoding="utf-8") as f:
    curriculum = json.load(f)

with open("candidates.json", "r", encoding="utf-8") as f:
    candidates_data = json.load(f)

candidate_map = {
    c["member"]["id"]: c
    for c in candidates_data["candidates"]
}

day_map = {
    d["day"]: d
    for d in curriculum["days"]
}

MIN_QUESTIONS = 8
MIN_CURRICULUM_DAYS = 4

# ------------------------------------
# Models
# ------------------------------------

class Message(BaseModel):
    role: str
    content: str


class InterviewRequest(BaseModel):
    candidate_id: str
    conversation: List[Message] = []


# ------------------------------------
# Candidate Logic
# ------------------------------------

def get_candidate(candidate_id):
    candidate = candidate_map.get(candidate_id)

    if not candidate:
        raise HTTPException(
            status_code=404,
            detail="Candidate not found"
        )

    return candidate


def completed_days(candidate):
    days = []

    for mission in candidate["missions"]:
        if mission.get("passed"):
            days.append({
                "day": mission["day"],
                "attempts": mission.get("attempts", 1)
            })

    return days


def weak_areas(candidate):

    weak = []

    for mission in candidate["missions"]:

        attempts = mission.get("attempts", 0)

        if attempts >= 3:
            weak.append(mission["day"])

        if mission.get("passed") is False:
            weak.append(mission["day"])

    return list(set(weak))


# ------------------------------------
# Interview Planning
# ------------------------------------

def build_plan(candidate):

    completed = completed_days(candidate)

    weak = weak_areas(candidate)

    completed.sort(
        key=lambda x: (
            x["day"] not in weak,
            x["attempts"]
        )
    )

    chosen = []

    for mission in completed:

        if mission["day"] in day_map:
            chosen.append(mission["day"])

    chosen = list(dict.fromkeys(chosen))

    return chosen


# ------------------------------------
# AI Interview Questions
# ------------------------------------

def create_question(day_info, candidate):

    objective = random.choice(
        day_info["objectives"]
    )

    role = candidate["member"]["jobRole"]

    return (
        f"Let's explore a real-world engineering scenario.\n\n"
        f"Based on your background as a {role}, "
        f"walk me through how you would design, implement, "
        f"or justify the following objective in production.\n\n"
        f"{objective}"
    )


def create_followup(previous_question, answer):

    answer = answer.lower()

    if len(answer.split()) < 15:

        return (
            "I'd like to understand your thinking in more depth.\n\n"
            "Can you discuss the implementation approach, "
            "tradeoffs, and technical challenges involved?"
        )

    keywords = [
        "rag",
        "embedding",
        "vector",
        "agent",
        "prompt",
        "deployment",
        "security"
    ]

    for keyword in keywords:

        if keyword in answer:

            return (
                f"Interesting. You mentioned {keyword}.\n\n"
                f"Imagine this system is already running in production.\n\n"
                f"What failure modes would you expect, "
                f"and how would you mitigate them?"
            )

    return (
        "That's a reasonable approach.\n\n"
        "Can you propose an alternative architecture or design "
        "and explain why you might choose it?"
    )


# ------------------------------------
# Conversation Helpers
# ------------------------------------

def assistant_questions(conversation):

    return [
        m.content
        for m in conversation
        if m.role == "assistant"
    ]


def user_answers(conversation):

    return [
        m.content
        for m in conversation
        if m.role == "user"
    ]


# ------------------------------------
# Feedback Engine
# ------------------------------------

def score_answer(answer):

    score = 0

    words = len(answer.split())

    if words > 20:
        score += 30

    if words > 50:
        score += 20

    keywords = [
        "architecture",
        "tradeoff",
        "latency",
        "embedding",
        "retrieval",
        "agent",
        "context",
        "evaluation",
        "deployment",
        "security"
    ]

    matches = sum(
        1
        for k in keywords
        if k in answer.lower()
    )

    score += min(matches * 5, 50)

    return min(score, 100)


def generate_feedback(candidate, answers):

    scores = [
        score_answer(a)
        for a in answers
    ]

    avg = int(
        sum(scores) / max(len(scores), 1)
    )

    strengths = []
    improvements = []

    if avg >= 80:
        strengths.append(
            "Strong technical depth"
        )

    if avg >= 70:
        strengths.append(
            "Good engineering communication"
        )

    if avg < 70:
        improvements.append(
            "Provide deeper technical reasoning"
        )

    if avg < 80:
        improvements.append(
            "Discuss architecture choices and tradeoffs more explicitly"
        )

    return {
        "candidate": candidate["member"]["name"],
        "overall_score": avg,
        "strengths": strengths,
        "improvements": improvements,
        "summary":
        "Interview completed successfully."
    }


# ------------------------------------
# API Endpoint
# ------------------------------------

@app.post("/api/interview")
def interview(req: InterviewRequest):

    candidate = get_candidate(
        req.candidate_id
    )

    plan = build_plan(candidate)

    questions = assistant_questions(
        req.conversation
    )

    answers = user_answers(
        req.conversation
    )

    asked_count = len(questions)

    covered_days = []

    for idx in range(
        min(
            len(plan),
            asked_count
        )
    ):
        covered_days.append(
            plan[idx]
        )

    if (
        asked_count >= MIN_QUESTIONS and
        len(set(covered_days))
        >= MIN_CURRICULUM_DAYS
    ):
        return {
            "status": "COMPLETED",
            "feedback":
                generate_feedback(
                    candidate,
                    answers
                )
        }

    if len(answers) < len(questions):
        return {
            "status": "WAITING_FOR_ANSWER"
        }

    if asked_count > 0:

        last_question = questions[-1]
        last_answer = answers[-1]

        if asked_count % 2 == 1:

            followup = create_followup(
                last_question,
                last_answer
            )

            return {
                "status": "IN_PROGRESS",
                "question_number":
                asked_count + 1,
                "question": followup,
                "covered_days":
                covered_days,
                "remaining_questions":
                MIN_QUESTIONS -
                asked_count
            }

    day_index = min(
        asked_count // 2,
        len(plan) - 1
    )

    selected_day = plan[day_index]

    question = create_question(
        day_map[selected_day],
        candidate
    )

    return {
        "status": "IN_PROGRESS",
        "question_number":
        asked_count + 1,
        "question": question,
        "covered_days":
        covered_days + [selected_day],
        "remaining_questions":
        MIN_QUESTIONS -
        asked_count - 1
    }


# ------------------------------------
# Serve Frontend
# ------------------------------------

app.mount(
    "/",
    StaticFiles(
        directory="frontend",
        html=True
    ),
    name="frontend"
)