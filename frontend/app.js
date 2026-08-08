const API = "/api/interview";
const MIN_QUESTIONS = 8;

const INTRO_TEXT = "Hi, I'm Shay. I will be interviewing you today!";

let conversation = [];
let sessionId = null;
let currentCandidate = "CAND-003";
let voiceMode = false;
let recognition = null;
let listening = false;
let voiceBusy = false;
let voiceToken = 0;
let lastQuestionText = null;

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
    lastQuestionText = text;
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

function mountShay() {
    const template = document.getElementById("shay-svg-template");
    if (!template) return;
    const introTarget = document.getElementById("shay-avatar");
    const liveTarget = document.querySelector(".shay-live-avatar");
    if (introTarget) introTarget.appendChild(template.content.cloneNode(true));
    if (liveTarget) liveTarget.appendChild(template.content.cloneNode(true));
    if ("speechSynthesis" in window) {
        speechSynthesis.getVoices();
        speechSynthesis.addEventListener?.("voiceschanged", () => speechSynthesis.getVoices());
    }
}

// ---------------- Voice interaction ----------------

function initRecognition() {
    if (recognition) return true;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return false;
    recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    return true;
}

function pickVoice() {
    if (!("speechSynthesis" in window)) return null;
    const voices = speechSynthesis.getVoices();
    const english = voices.filter((v) =>
        v.lang && v.lang.toLowerCase().startsWith("en")
    );
    return (
        english.find((v) =>
            /female|woman|shay|samantha|zira|jenny|aria|serena|victoria|karen|moira|tessa/i.test(v.name)
        ) ||
        english.find((v) => v.default) ||
        english[0] ||
        null
    );
}

function speak(text) {
    return new Promise((resolve) => {
        if (!("speechSynthesis" in window)) {
            resolve();
            return;
        }
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "en-US";
        const voice = pickVoice();
        if (voice) utterance.voice = voice;
        utterance.rate = 1;
        utterance.pitch = 1.05;
        utterance.onend = () => resolve();
        utterance.onerror = () => resolve();
        speechSynthesis.cancel();
        speechSynthesis.speak(utterance);
        setTimeout(resolve, Math.max(12000, text.length * 90));
    });
}

function listenOnce() {
    return new Promise((resolve) => {
        if (!recognition || listening) {
            resolve(null);
            return;
        }
        listening = true;
        let done = false;
        const finish = (text) => {
            if (done) return;
            done = true;
            listening = false;
            resolve(text);
        };
        recognition.onresult = (event) => {
            const result = event.results[0];
            finish(result && result[0] ? result[0].transcript.trim() : null);
        };
        recognition.onerror = () => finish(null);
        recognition.onend = () => finish(null);
        try {
            recognition.start();
        } catch (err) {
            finish(null);
        }
    });
}

function setVoiceState(state) {
    const status = document.getElementById("voice-status");
    const hint = document.getElementById("voice-hint");
    const panel = document.getElementById("voice-panel");
    const mic = document.getElementById("mic-btn");
    const dock = document.getElementById("voice-dock");
    const badge = document.getElementById("shay-live-badge");

    if (panel) panel.dataset.state = state;
    if (status) {
        status.textContent =
            state === "speaking"
                ? "Shay is speaking…"
                : state === "listening"
                    ? "Listening… speak your answer"
                    : "Tap the mic and speak";
    }
    if (hint) hint.textContent = state === "speaking" ? "Hold on a moment…" : "Tap the mic and speak your answer";
    if (mic) mic.classList.toggle("recording", state === "listening");
    if (dock) {
        dock.classList.toggle("speaking", state === "speaking");
        dock.classList.toggle("listening", state === "listening");
    }
    if (badge) {
        badge.textContent =
            state === "speaking"
                ? "Speaking"
                : state === "listening"
                    ? "Listening"
                    : "Ready";
    }
}

function cancelVoiceActivity() {
    voiceToken++;
    if (recognition) {
        try { recognition.abort(); } catch (err) { /* noop */ }
    }
    if ("speechSynthesis" in window) {
        speechSynthesis.cancel();
    }
    listening = false;
    voiceBusy = false;
}

function warmUpMicrophone() {
    if (!recognition) return;
    try {
        recognition.start();
    } catch (err) {
        return;
    }
    setTimeout(() => {
        try { recognition.abort(); } catch (err) { /* noop */ }
    }, 800);
}

function toggleVoiceMode() {
    const toggle = document.getElementById("voice-toggle");
    const live = document.getElementById("shay-live");
    const panel = document.getElementById("voice-panel");
    const composer = document.getElementById("composer-input");
    const hint = document.getElementById("composer-hint");

    if (!voiceMode) {
        if (!initRecognition()) {
            alert("Voice mode needs Chrome or Edge (Web Speech API). Falling back to text.");
            return;
        }
        voiceMode = true;
        toggle.classList.add("active");
        toggle.setAttribute("aria-pressed", "true");
        live.hidden = false;
        panel.hidden = false;
        composer.hidden = true;
        hint.hidden = true;
        setVoiceState("idle");
        warmUpMicrophone();
        if (lastQuestionText) {
            voiceTurn(lastQuestionText);
        }
    } else {
        voiceMode = false;
        cancelVoiceActivity();
        toggle.classList.remove("active");
        toggle.setAttribute("aria-pressed", "false");
        live.hidden = true;
        panel.hidden = true;
        composer.hidden = false;
        hint.hidden = false;
        setVoiceState("idle");
        const box = document.getElementById("answer");
        if (box) box.focus();
    }
}

async function answerByVoice() {
    if (!voiceMode || voiceBusy || listening) return;
    voiceBusy = true;
    const token = voiceToken;
    setVoiceState("listening");
    const transcript = await listenOnce();
    if (token !== voiceToken || !voiceMode) return;
    setVoiceState("idle");
    voiceBusy = false;
    if (transcript) {
        await sendAnswer(transcript);
    }
}

function voiceTurn(question) {
    if (!voiceMode || voiceBusy) return;
    voiceBusy = true;
    const token = voiceToken;

    (async () => {
        setVoiceState("speaking");
        await speak(question);
        if (token !== voiceToken || !voiceMode) {
            voiceBusy = false;
            return;
        }
        setVoiceState("listening");
        const transcript = await listenOnce();
        if (token !== voiceToken || !voiceMode) {
            voiceBusy = false;
            return;
        }
        setVoiceState("idle");
        voiceBusy = false;
        if (transcript) {
            await sendAnswer(transcript);
        }
    })();
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

    if (voiceMode) {
        speak(INTRO_TEXT);
    }

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

    if (voiceMode) {
        setVoiceState("speaking");
        speak("That's the end of your interview, thank you for your time!");
    }
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

    if (voiceMode) {
        voiceTurn(data.question);
    }

    return data;
}

async function startInterview() {
    currentCandidate = document.getElementById("candidate-select").value || currentCandidate;
    conversation = [];
    sessionId = null;

    cancelVoiceActivity();
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

async function sendAnswer(text) {
    const fromText = text === undefined || text === null;
    const answer = fromText
        ? document.getElementById("answer").value.trim()
        : String(text).trim();

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

    if (fromText) {
        document.getElementById("answer").value = "";
        document.getElementById("answer").focus();
    }
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

mountShay();
loadCandidates().then(() => startInterview());
