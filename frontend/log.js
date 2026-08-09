let DATA = null;
let filter = "all";

function esc(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
}

function fmtTimestamp(value) {
    if (!value) return "";
    if (typeof value === "number") {
        return new Date(value * 1000).toLocaleString();
    }
    return value;
}

async function load() {
    const sub = document.getElementById("log-sub");
    try {
        const res = await fetch("/api/log");
        DATA = await res.json();
        sub.textContent =
            `${DATA.count} records · ${DATA.sessions} interviews · ` +
            `${DATA.external_chats} imported chats`;
        render();
    } catch (err) {
        sub.textContent = "Failed to load log";
        document.getElementById("records").textContent = String(err);
    }
}

function renderStats() {
    const row = document.getElementById("stats-row");
    const items = [
        ["Records", DATA.count],
        ["Interviews", DATA.sessions],
        ["Q&A turns", DATA.turns],
        ["Answers", DATA.answers],
        ["LLM calls", DATA.llm_calls],
        ["Imported chats", DATA.external_chats],
        ["Documents", DATA.attachments],
        ["Completed", DATA.completed],
    ];
    row.innerHTML = items.map(
        ([label, value]) =>
            `<div class="stat-card"><div class="stat-value">${esc(value)}</div>` +
            `<div class="stat-label">${esc(label)}</div></div>`
    ).join("");
}

function sessionCard(records, meta) {
    const turns = records.filter(r => r.type === "turn");
    const answers = records.filter(r => r.type === "answer");
    const complete = records.find(r => r.type === "session_complete");

    const body = turns.map(turn => {
        const answer = turn.answer || (answers.find(
            a => a.turn === turn.turn
        ) || {}).answer;
        return `
            <div class="log-q">
                <div class="log-row-label">Q${turn.turn} · ${esc(turn.mode)}</div>
                <div class="log-row role-assistant">${esc(turn.question)}</div>
                ${answer ? `<div class="log-row role-user"><b>A:</b> ${esc(answer)}</div>` : ""}
            </div>`;
    }).join("");

    const feedback = complete && complete.feedback
        ? `<div class="log-feedback">
             <div class="log-row-label">Feedback · score ${esc(complete.feedback.overall_score)}/100 · ${esc(complete.feedback.verdict)}</div>
             <div class="log-row">${esc(complete.feedback.summary || "")}</div>
           </div>`
        : "";

    return `
        <div class="log-card">
            <div class="log-card-head">
                <div class="log-card-title">Interview · ${esc(meta.candidate_id || "—")}</div>
                <div class="log-card-meta">${fmtTimestamp(meta.timestamp)} · ${turns.length} turns</div>
            </div>
            <div class="log-session-id">${esc(meta.session_id || "")}</div>
            ${body}
            ${feedback}
        </div>`;
}

function llmCallCard(record) {
    const promptHtml = (record.messages || []).map(m =>
        `<div class="log-row role-${m.role === "user" ? "user" : "assistant"}">
            <b>${esc(m.role)}:</b> ${esc(m.content)}
         </div>`
    ).join("");

    const output = record.raw_output
        ? `<div class="log-row role-assistant"><b>raw_output:</b> ${esc(JSON.stringify(record.raw_output, null, 2))}</div>`
        : "";

    return `
        <div class="log-card">
            <div class="log-card-head">
                <div class="log-card-title">LLM call · ${esc(record.kind || "")}</div>
                <div class="log-card-meta">${fmtTimestamp(record.timestamp)}</div>
            </div>
            <div class="log-session-id">${esc(record.candidate_id || "")} · day ${esc(record.day || "")} · ${esc(record.mode || "")} · Q${esc(record.question_number || "")} · ${esc(record.level || "")}</div>
            <details class="log-details"><summary>Prompt (${(record.messages || []).length} messages)</summary>${promptHtml}</details>
            ${output ? `<details class="log-details"><summary>Output</summary>${output}</details>` : ""}
        </div>`;
}

function externalChatCard(record) {
    const body = (record.messages || []).map(m =>
        `<div class="log-row role-${m.role === "user" ? "user" : "assistant"}">
            <div class="log-row-label">${m.role === "user" ? "You" : esc(record.source || "AI")}</div>
            ${esc(m.content)}
         </div>`
    ).join("");

    return `
        <div class="log-card">
            <div class="log-card-head">
                <div class="log-card-title">${esc(record.title || "Imported chat")} <span class="source-badge">${esc(record.source || "ai")}</span></div>
                <div class="log-card-meta">${fmtTimestamp(record.timestamp)} · ${record.num_messages} messages</div>
            </div>
            ${body}
        </div>`;
}

function attachmentCard(record) {
    const textPreview = (record.text || "").slice(0, 600);
    return `
        <div class="log-card">
            <div class="log-card-head">
                <div class="log-card-title">${esc(record.title || record.filename)} <span class="source-badge">${esc(record.source || "doc")}</span></div>
                <div class="log-card-meta">${fmtTimestamp(record.timestamp)} · ${esc(record.num_pages)} pages</div>
            </div>
            <div class="log-session-id">${esc(record.filename || "")}</div>
            ${record.url ? `<a class="log-file-link" href="${esc(record.url)}" target="_blank" rel="noopener">Open PDF</a>` : ""}
            ${textPreview ? `<details class="log-details"><summary>Preview (${esc(record.text_length)} chars)</summary><div class="log-row">${esc(textPreview)}${record.text_length > 600 ? " …" : ""}</div></details>` : ""}
        </div>`;
}

function render() {
    renderStats();
    const container = document.getElementById("records");

    const sessions = {};
    (DATA.records || []).forEach(r => {
        if (["session_start", "turn", "answer", "session_end", "session_complete"].includes(r.type)) {
            if (!sessions[r.session_id]) sessions[r.session_id] = { meta: null, records: [] };
            sessions[r.session_id].records.push(r);
            if (r.type === "session_start") sessions[r.session_id].meta = r;
        }
    });

    let html = "";
    if (filter === "all" || filter === "sessions") {
        const order = Object.entries(sessions).sort(
            (a, b) => (b[1].meta && a[1].meta && String(b[1].meta.timestamp).localeCompare(String(a[1].meta.timestamp)))
        );
        html += order.map(([sid, group]) => sessionCard(group.records, group.meta || { session_id: sid })).join("");
    }
    if (filter === "all" || filter === "llm_calls") {
        html += (DATA.records || []).filter(r => r.type === "llm_call").map(llmCallCard).join("");
    }
    if (filter === "all" || filter === "external_chats") {
        html += (DATA.records || []).filter(r => r.type === "external_chat").map(externalChatCard).join("");
    }
    if (filter === "all" || filter === "attachments") {
        html += (DATA.records || []).filter(r => r.type === "attachment").map(attachmentCard).join("");
    }
    container.innerHTML = html || '<div class="log-empty">Nothing here yet.</div>';
}

function setFilter(btn) {
    filter = btn.dataset.filter;
    document.querySelectorAll(".filter-chip").forEach(b => b.classList.toggle("active", b === btn));
    render();
}

function toggleImport(force) {
    const panel = document.getElementById("import-panel");
    const show = force === undefined ? panel.hidden : !force;
    panel.hidden = !show;
    if (show) document.getElementById("import-title").focus();
}

async function submitImport() {
    const title = document.getElementById("import-title").value.trim();
    const text = document.getElementById("import-text").value.trim();
    const status = document.getElementById("import-status");

    if (!text) {
        status.textContent = "Paste a conversation first.";
        status.className = "import-status error";
        return;
    }

    status.textContent = "Importing…";
    status.className = "import-status";
    try {
        const res = await fetch("/api/import-chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, text }),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || res.statusText);
        }
        status.textContent = data.imported
            ? `Imported ${data.num_messages} messages into the log.`
            : "That chat is already in the log (skipped).";
        status.className = "import-status ok";
        setTimeout(() => toggleImport(false), 900);
        setTimeout(load, 400);
    } catch (err) {
        status.textContent = "Import failed: " + err.message;
        status.className = "import-status error";
    }
}

load();
