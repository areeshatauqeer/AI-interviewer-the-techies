const API = "http://127.0.0.1:8000/api/interview";
const CANDIDATE_ID = "CAND-003";
const MIN_QUESTIONS = 8;

let conversation = [];
let totalQuestions = MIN_QUESTIONS;

function updateProgress(current) {
    const chip = document.getElementById("progress");
    if (chip) {
        chip.textContent = `Question ${Math.min(current, totalQuestions)} / ${totalQuestions}`;
    }
}

function addAI(text) {
    const chat = document.getElementById("chat");
    const row = document.createElement("div");
    row.className = "message-row ai";

    const avatar = document.createElement("div");
    avatar.className = "avatar avatar-ai";
    avatar.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M9.5 9.5l5 5M14.5 9.5l-5 5"/>
        </svg>`;

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML =
        `<div class="msg-author">Interview Agent</div>${escapeHtml(text)}`;

    row.appendChild(avatar);
    row.appendChild(bubble);
    chat.appendChild(row);
    scrollToBottom();
}

function addUser(text) {
    const chat = document.getElementById("chat");
    const row = document.createElement("div");
    row.className = "message-row user";

    const avatar = document.createElement("div");
    avatar.className = "avatar avatar-user";
    avatar.textContent = "Y";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML =
        `<div class="msg-author">You</div>${escapeHtml(text)}`;

    row.appendChild(avatar);
    row.appendChild(bubble);
    chat.appendChild(row);
    scrollToBottom();
}

function addTyping() {
    const chat = document.getElementById("chat");
    const row = document.createElement("div");
    row.className = "message-row ai";
    row.id = "typing-row";

    const avatar = document.createElement("div");
    avatar.className = "avatar avatar-ai";
    avatar.textContent = "AI";

    const bubble = document.createElement("div");
    bubble.className = "bubble typing";
    bubble.innerHTML = `<span></span><span></span><span></span>`;

    row.appendChild(avatar);
    row.appendChild(bubble);
    chat.appendChild(row);
    scrollToBottom();
}

function removeTyping() {
    const row = document.getElementById("typing-row");
    if (row) row.remove();
}

function scrollToBottom() {
    const wrap = document.querySelector(".conversation-wrap");
    if (wrap) wrap.scrollTop = wrap.scrollHeight;
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML.replace(/\n/g, "<br>");
}

function setBusy(busy) {
    const btn = document.getElementById("send-btn");
    const box = document.getElementById("answer");
    if (btn) btn.disabled = busy;
    if (box) box.disabled = busy;
}

async function ask(payload) {
    setBusy(true);
    addTyping();

    const response = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    removeTyping();
    setBusy(false);

    if (data.status === "COMPLETED") {
        const f = data.feedback;
        const lines = [
            "Interview Complete",
            "",
            `Overall Score: ${f.overall_score}/100`,
            "",
            "Strengths:",
            ...f.strengths.map((s) => `• ${s}`),
            "",
            "Improvements:",
            ...f.improvements.map((i) => `• ${i}`)
        ];
        addAI(lines.join("\n"));
        document.getElementById("progress").textContent = "Completed";
        return data;
    }

    if (data.question_number) {
        updateProgress(data.question_number);
    }

    addAI(data.question);

    conversation.push({
        role: "assistant",
        content: data.question
    });

    return data;
}

async function startInterview() {
    conversation = [];
    document.getElementById("chat").innerHTML = "";
    document.getElementById("answer").value = "";
    updateProgress(1);

    const data = await ask({
        candidate_id: CANDIDATE_ID,
        conversation: []
    });

    if (data.question) {
        conversation.push({
            role: "assistant",
            content: data.question
        });
    }
}

async function sendAnswer() {
    const answer = document.getElementById("answer").value.trim();

    if (!answer) return;

    addUser(answer);

    conversation.push({
        role: "user",
        content: answer
    });

    await ask({
        candidate_id: CANDIDATE_ID,
        conversation
    });

    document.getElementById("answer").value = "";
    document.getElementById("answer").focus();
}

const answerBox = document.getElementById("answer");
answerBox.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendAnswer();
    }
});

answerBox.addEventListener("input", () => {
    answerBox.style.height = "auto";
    answerBox.style.height = Math.min(answerBox.scrollHeight, 160) + "px";
});

startInterview();
