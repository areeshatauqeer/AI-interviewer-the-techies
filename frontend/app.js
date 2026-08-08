const API = "/api/interview";
const MIN_QUESTIONS = 8;

const INTRO_TEXT = "Hi, I'm Shay. I will be interviewing you today!";

let conversation = [];
let sessionId = null;
let currentCandidate = "CAND-003";

function updateProgress(current) {
    const chip = document.getElementById("progress");
    if (chip) {
        chip.textContent = `Question ${Math.min(current, MIN_QUESTIONS)} / ${MIN_QUESTIONS}`;
    }
}

function addAI(text, dayTitle) {
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
    const label = dayTitle ? `Interview Agent · ${dayTitle}` : "Interview Agent";
    bubble.innerHTML =
        `<div class="msg-author">${escapeHtml(label)}</div>${escapeHtml(text)}`;

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

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function typeText(el, text, msPerChar) {
    for (let i = 0; i < text.length; i++) {
        el.textContent = text.slice(0, i + 1);
        await wait(msPerChar);
    }
}

async function playIntro() {
    const overlay = document.getElementById("intro");
    const textEl = document.getElementById("intro-text");

    textEl.textContent = "";
    overlay.classList.remove("exiting");
    overlay.hidden = false;

    requestAnimationFrame(() => {
        overlay.classList.add("active");
    });

    await wait(700);

    await typeText(textEl, INTRO_TEXT, 38);
    await wait(1000);

    overlay.classList.remove("active");
    overlay.classList.add("exiting");

    await wait(550);

    overlay.classList.remove("exiting");
    overlay.hidden = true;
}

function renderFeedback(feedback) {
    const lines = [
        "Interview Complete",
        "",
        `Overall Score: ${feedback.overall_score}/100`,
        "",
        "Summary:",
        feedback.summary,
        "",
        "Strengths:",
        ...feedback.strengths.map((s) => `• ${s}`),
        "",
        "Improvements:",
        ...feedback.improvements.map((i) => `• ${i}`)
    ];
    addAI(lines.join("\n"));
    document.getElementById("progress").textContent = "Completed";
}

async function ask(payload) {
    setBusy(true);
    addTyping();

    let data;
    try {
        const response = await fetch(API, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        data = await response.json();
    } catch (err) {
        removeTyping();
        setBusy(false);
        alert("Connection error: " + err.message);
        return null;
    }

    removeTyping();
    setBusy(false);

    sessionId = data.session_id || sessionId;

    if (data.status === "COMPLETED") {
        renderFeedback(data.feedback);
        return data;
    }

    if (data.question_number) {
        updateProgress(data.question_number);
    }

    addAI(data.question, data.day_title);

    conversation.push({
        role: "assistant",
        content: data.question
    });

    return data;
}

async function startInterview() {
    currentCandidate = document.getElementById("candidate-select").value || currentCandidate;
    conversation = [];
    sessionId = null;

    setBusy(true);
    await playIntro();
    setBusy(false);

    document.getElementById("chat").innerHTML = "";
    document.getElementById("answer").value = "";
    document.getElementById("answer").focus();

    updateProgress(1);

    const data = await ask({
        candidate_id: currentCandidate,
        conversation: []
    });

    if (data && data.question) {
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
        candidate_id: currentCandidate,
        session_id: sessionId,
        conversation
    });

    document.getElementById("answer").value = "";
    document.getElementById("answer").focus();
}

async function loadCandidates() {
    const select = document.getElementById("candidate-select");

    try {
        const response = await fetch("/api/candidates");
        const data = await response.json();

        data.candidates.forEach((candidate) => {
            const option = document.createElement("option");
            option.value = candidate.id;
            option.textContent = `${candidate.name} — ${candidate.role}`;
            select.appendChild(option);
        });
    } catch (err) {
        const option = document.createElement("option");
        option.value = "CAND-003";
        option.textContent = "Emily Chen — AI Engineer";
        select.appendChild(option);
    }

    select.value = currentCandidate;
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

loadCandidates().then(() => startInterview());
