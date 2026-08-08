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
let speechToken = 0;
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
    const speakingTarget = document.querySelector(".shay-speaking-avatar");
    if (introTarget) introTarget.appendChild(template.content.cloneNode(true));
    if (liveTarget) liveTarget.appendChild(template.content.cloneNode(true));
    if (speakingTarget) speakingTarget.appendChild(template.content.cloneNode(true));
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

function playSigh({ duration = 1.0, strength = 0.5 } = {}) {
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        if (ctx.state === "suspended") ctx.resume();
        const sampleRate = ctx.sampleRate;
        const buffer = ctx.createBuffer(1, Math.floor(sampleRate * duration), sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < data.length; i++) {
            data[i] = Math.random() * 2 - 1;
        }
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        const filter = ctx.createBiquadFilter();
        filter.type = "lowpass";
        filter.frequency.value = 680;
        filter.Q.value = 0.7;
        const gain = ctx.createGain();
        const t0 = ctx.currentTime;
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(Math.max(0.05, strength), t0 + duration * 0.42);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
        source.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);
        source.start(t0);
        source.stop(t0 + duration + 0.05);
        setTimeout(() => ctx.close().catch(() => {}), duration * 1000 + 300);
    } catch (err) { /* audio unavailable */ }
}

function splitParagraphs(text) {
    return String(text).split(/\n{2,}/).map((s) => s.trim()).filter(Boolean);
}

function splitChunks(text) {
    const matches = String(text).match(/[^,;:!?.]+[,;:!?.]?/g) || [];
    return matches.map((s) => s.trim()).filter(Boolean);
}

function pauseForChunk(chunk) {
    const last = chunk.slice(-1);
    if (last === "!" || last === "?") return 600 + Math.random() * 250;
    if (last === ".") return 480 + Math.random() * 260;
    if (last === ";" || last === ":") return 320 + Math.random() * 220;
    if (last === ",") return 220 + Math.random() * 180;
    return 130 + Math.random() * 140;
}

function speak(text) {
    return new Promise((resolve) => {
        if (!("speechSynthesis" in window)) {
            resolve();
            return;
        }
        const token = ++speechToken;
        const paragraphs = splitParagraphs(text);
        if (!paragraphs.length) {
            resolve();
            return;
        }
        const voice = pickVoice();
        speechSynthesis.cancel();
        playSigh({ duration: 1.0, strength: 0.5 });

        (async () => {
            await wait(300);
            let chunkIndex = 0;
            for (const paragraph of paragraphs) {
                const chunks = splitChunks(paragraph);
                for (let i = 0; i < chunks.length; i++) {
                    if (token !== speechToken) {
                        resolve();
                        return;
                    }
                    const utterance = new SpeechSynthesisUtterance(chunks[i]);
                    utterance.lang = "en-US";
                    if (voice) utterance.voice = voice;
                    utterance.rate = 0.83 + Math.random() * 0.06;
                    utterance.pitch = 0.95 + Math.random() * 0.08;
                    utterance.volume = 0.92 + Math.random() * 0.08;
                    await new Promise((res) => {
                        utterance.onend = res;
                        utterance.onerror = res;
                        speechSynthesis.speak(utterance);
                        setTimeout(res, Math.max(4000, chunks[i].length * 115));
                    });
                    if (token !== speechToken) {
                        resolve();
                        return;
                    }
                    await wait(pauseForChunk(chunks[i]));
                    chunkIndex++;
                    if (chunkIndex % 7 === 3) {
                        playSigh({ duration: 0.7, strength: 0.3 });
                    }
                }
                await wait(700 + Math.random() * 400);
            }
            resolve();
        })();
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
    const speaking = document.getElementById("shay-speaking");

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
    if (speaking) {
        speaking.classList.toggle("visible", state === "speaking");
    }
}

function cancelVoiceActivity() {
    voiceToken++;
    speechToken++;
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

function ringSVG(score, size, cls) {
    const safe = Math.max(0, Math.min(100, Math.round(score)));
    const r = Math.round(size * 0.34);
    const c = 2 * Math.PI * r;
    const color = safe >= 75 ? "#34d399" : safe >= 55 ? "#fbbf24" : "#f87171";
    const target = (c * (1 - safe / 100)).toFixed(2);
    return `
        <svg class="ring-svg ring-${cls}" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">
            <circle class="ring-track" cx="${size / 2}" cy="${size / 2}" r="${r}"/>
            <circle class="ring-fill" cx="${size / 2}" cy="${size / 2}" r="${r}"
                stroke="${color}" stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${c.toFixed(2)}"
                data-target="${target}"/>
        </svg>`;
}

function buildFeedbackHTML(feedback) {
    const score = Math.max(0, Math.min(100, Math.round(feedback.overall_score || 0)));
    const topics = Object.values(feedback.topics || {});
    const strengths = feedback.strengths || [];
    const improvements = feedback.improvements || [];

    const topicRows = topics
        .map(
            (t, i) => `
            <div class="topic-row">
                <div class="topic-ring">${ringSVG(t.score, 64, `topic-${i}`)}</div>
                <div class="topic-meta">
                    <div class="topic-title">${escapeHtml(t.title || "Topic")}</div>
                    <div class="topic-score">${Math.round(t.score)}/100</div>
                </div>
            </div>`
        )
        .join("");

    const strengthItems = strengths
        .map(
            (s) => `
            <li>
                <span class="fb-icon fb-icon-good">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"/>
                    </svg>
                </span>
                <span>${escapeHtml(s)}</span>
            </li>`
        )
        .join("");

    const improveItems = improvements
        .map(
            (s) => `
            <li>
                <span class="fb-icon fb-icon-warn">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19"/>
                        <polyline points="5 12 12 19 19 12"/>
                    </svg>
                </span>
                <span>${escapeHtml(s)}</span>
            </li>`
        )
        .join("");

    return `
        <div class="feedback-card">
            <div class="feedback-head">
                <div class="feedback-badge">Interview Complete</div>
                <div class="feedback-candidate">${escapeHtml(feedback.candidate || "Candidate")}</div>
            </div>
            <div class="feedback-grid">
                <div class="feedback-overall">
                    <div class="donut">
                        ${ringSVG(score, 150, "overall")}
                        <div class="donut-center">
                            <span class="donut-num">${score}</span>
                            <span class="donut-unit">out of 100</span>
                        </div>
                    </div>
                    <div class="feedback-overall-label">Overall Score</div>
                </div>
                ${
                    topics.length
                        ? `<div class="feedback-topics">
                            <div class="feedback-section-title">Topic Breakdown</div>
                            ${topicRows}
                        </div>`
                        : ""
                }
            </div>
            <div class="feedback-summary">${escapeHtml(feedback.summary || "")}</div>
            <div class="feedback-lists">
                ${
                    strengthItems
                        ? `<div class="feedback-list fb-strengths">
                            <div class="feedback-list-title">Strengths</div>
                            <ul>${strengthItems}</ul>
                        </div>`
                        : ""
                }
                ${
                    improveItems
                        ? `<div class="feedback-list fb-improvements">
                            <div class="feedback-list-title">Improvements</div>
                            <ul>${improveItems}</ul>
                        </div>`
                        : ""
                }
            </div>
        </div>`;
}

function animateRings(container) {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            container.querySelectorAll(".ring-fill").forEach((el) => {
                el.style.strokeDashoffset = el.dataset.target;
            });
        });
    });
}

function addFeedbackCard(feedback) {
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
    bubble.className = "bubble feedback-bubble";
    bubble.innerHTML = buildFeedbackHTML(feedback);

    row.appendChild(avatar);
    row.appendChild(bubble);
    chat.appendChild(row);
    scrollToBottom();
    animateRings(bubble);
}

function renderFeedback(feedback) {
    document.getElementById("progress").textContent = "Completed";
    addFeedbackCard(feedback);

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
