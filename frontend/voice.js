const API = "/api/interview";
const MIN_QUESTIONS = 8;

let conversation = [];
let sessionId = null;
let currentCandidate = "CAND-003";
let recognition = null;
let listening = false;
let busy = false;
let speechToken = 0;
let currentQuestion = null;
let completed = false;

const scene = document.getElementById("scene");
const subtitleEl = document.getElementById("subtitle");
const statusEl = document.getElementById("seat-status");
const micBtn = document.getElementById("mic-btn");
const progressEl = document.getElementById("progress");

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function setSubtitle(text) {
    subtitleEl.textContent = text || "…";
}

function setSceneState(state) {
    scene.classList.toggle("speaking", state === "speaking");
    scene.classList.toggle("listening", state === "listening");
    micBtn.classList.toggle("recording", state === "listening");
    statusEl.textContent =
        state === "speaking"
            ? "Speaking"
            : state === "listening"
                ? "Listening…"
                : "Ready";
}

function updateProgress(current) {
    progressEl.textContent = `Question ${Math.min(current, MIN_QUESTIONS)} / ${MIN_QUESTIONS}`;
}

// ---------------- Human voice engine ----------------

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

function speak(text, onChunk) {
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
                    if (onChunk) onChunk(chunks[i]);
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

function cancelAll() {
    speechToken++;
    if (recognition) {
        try { recognition.abort(); } catch (err) { /* noop */ }
    }
    if ("speechSynthesis" in window) {
        speechSynthesis.cancel();
    }
    listening = false;
    busy = false;
}

// ---------------- Interview flow ----------------

async function askQuestion() {
    let data;
    try {
        const response = await fetch(API, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                candidate_id: currentCandidate,
                session_id: sessionId,
                conversation
            })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        data = await response.json();
    } catch (err) {
        setSubtitle("Connection lost — please try again.");
        return null;
    }

    sessionId = data.session_id || sessionId;

    if (data.status === "COMPLETED") {
        handleComplete(data.feedback);
        return null;
    }

    if (data.question_number) {
        updateProgress(data.question_number);
    }

    return data;
}

async function runTurn(question) {
    currentQuestion = question;
    setSceneState("speaking");
    await speak(question, setSubtitle);
    if (completed) return;
    setSubtitle("Your turn — go ahead and answer.");
    setSceneState("listening");
    const transcript = await listenOnce();
    if (completed) return;
    if (!transcript) {
        setSubtitle("");
        setSceneState("speaking");
        await speak("Sorry, I didn't quite catch that. Could you try again?", setSubtitle);
        if (completed) return;
        setSubtitle("Your turn — go ahead and answer.");
        setSceneState("listening");
        const retry = await listenOnce();
        if (completed) return;
        if (!retry) {
            setSceneState("idle");
            setSubtitle("Tap the mic when you're ready to answer.");
            return;
        }
        await sendTurn(retry);
        return;
    }
    await sendTurn(transcript);
}

async function sendTurn(text) {
    conversation.push({ role: "user", content: text });
    const data = await askQuestion();
    if (data) {
        await runTurn(data.question);
    }
}

function handleComplete(feedback) {
    completed = true;
    setSceneState("speaking");
    speak(
        feedback.early_exit && feedback.summary
            ? feedback.summary
            : "That's the end of your interview. Thank you so much for your time!",
        setSubtitle
    ).then(() => {
        showCompletion(feedback);
    });
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML.replace(/\n/g, "<br>");
}

function buildCompletionFeedbackHTML(feedback) {
    const rubric = feedback.rubric || [];
    const scorecard = feedback.scorecard || [];
    const parts = [];

    if (feedback.borderline) {
        parts.push(
            '<div class="cmp-banner"><strong>Borderline result.</strong> ' +
            "See the per-answer scorecard below for exactly why each answer " +
            "earned its points.</div>"
        );
    }

    if (rubric.length) {
        parts.push('<div class="cmp-section"><div class="cmp-section-title">Scoring Rubric</div>');
        rubric.forEach((d) => {
            parts.push(
                `<div class="cmp-rubric-row"><span class="cmp-rubric-label">${escapeHtml(d.label)}</span>` +
                `<span class="cmp-rubric-max">up to ${d.max} pts</span></div>`
            );
        });
        parts.push("</div>");
    }

    if (scorecard.length) {
        parts.push('<div class="cmp-section"><div class="cmp-section-title">Per-Answer Scorecard</div>');
        scorecard.forEach((entry, i) => {
            const dims = (entry.dimensions || [])
                .map(
                    (d) => `
                    <div class="cmp-dim">
                        <div class="cmp-dim-top"><span>${escapeHtml(d.label)}</span><span>${d.score}/${d.max}</span></div>
                        <div class="cmp-bar"><i style="width:${Math.min(100, (d.score / d.max) * 100)}%"></i></div>
                        <div class="cmp-reason">${escapeHtml(d.reason || "")}</div>
                    </div>`
                )
                .join("");
            parts.push(`
                <details class="cmp-entry" ${i === 0 ? "open" : ""}>
                    <summary>
                        <span class="cmp-qnum">Q${i + 1}</span>
                        <span class="cmp-qtitle">Day ${escapeHtml(entry.day)} · ${escapeHtml(entry.title || "Topic")}</span>
                        <span class="cmp-qscore">${Math.round(entry.score)}</span>
                    </summary>
                    <div class="cmp-entry-body">
                        <div class="cmp-qa"><span>Question</span><div>${escapeHtml(entry.question || "")}</div></div>
                        <div class="cmp-qa"><span>Answer</span><div>${escapeHtml(entry.answer || "(no answer)")}</div></div>
                        ${entry.comment ? `<div class="cmp-comment">${escapeHtml(entry.comment)}</div>` : ""}
                        <div class="cmp-dims">${dims}</div>
                    </div>
                </details>`);
        });
        parts.push("</div>");
    }

    return parts.join("");
}

function showCompletion(feedback) {
    const score = Math.max(0, Math.min(100, Math.round(feedback.overall_score || 0)));
    const box = document.getElementById("completion");
    const fill = document.getElementById("comp-ring-fill");
    const c = 2 * Math.PI * 52;

    document.getElementById("comp-num").textContent = score;
    document.getElementById("comp-name").textContent =
        feedback.candidate || "Candidate";
    fill.style.stroke = score >= 75 ? "#34d399" : score >= 55 ? "#fbbf24" : "#f87171";
    fill.style.strokeDasharray = c.toFixed(2);
    fill.style.strokeDashoffset = c.toFixed(2);

    const target = document.getElementById("completion-feedback");
    if (target) {
        target.innerHTML = buildCompletionFeedbackHTML(feedback);
    }

    box.hidden = false;

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            fill.style.strokeDashoffset = (c * (1 - score / 100)).toFixed(2);
        });
    });
}

async function answerByVoice() {
    if (!recognition) {
        if (!initRecognition()) {
            setSubtitle("Voice needs Chrome or Edge for this experience.");
            return;
        }
    }
    if (busy || listening || completed) return;
    if (scene.classList.contains("speaking")) return;
    busy = true;
    setSceneState("listening");
    const transcript = await listenOnce();
    busy = false;
    if (completed) return;
    if (!transcript) {
        setSceneState("idle");
        setSubtitle("I didn't hear anything — tap the mic to try again.");
        return;
    }
    setSubtitle("");
    await sendTurn(transcript);
}

function replayQuestion() {
    if (completed || !currentQuestion) return;
    cancelAll();
    setSceneState("speaking");
    speak(currentQuestion, setSubtitle);
}

async function startVoiceInterview() {
    cancelAll();
    currentCandidate = document.getElementById("candidate-select").value || currentCandidate;
    conversation = [];
    sessionId = null;
    currentQuestion = null;
    completed = false;

    document.getElementById("completion").hidden = true;
    scene.classList.remove("entered", "speaking", "listening");
    void scene.offsetWidth;
    scene.classList.add("entered");

    setSceneState("idle");
    setSubtitle("Shay is coming in…");
    updateProgress(1);

    await wait(1600);

    setSceneState("speaking");
    await speak(
        "Hi, I'm Shay. Please make yourself comfortable — we'll have a relaxed conversation today.",
        setSubtitle
    );
    if (completed) return;

    const data = await askQuestion();
    if (data) {
        await runTurn(data.question);
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

if (!initRecognition()) {
    setSubtitle("Voice needs Chrome or Edge for this experience.");
}

loadCandidates().then(() => startVoiceInterview());
