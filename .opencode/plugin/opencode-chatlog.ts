import { createHash } from "node:crypto"
import { existsSync, readFileSync, writeFileSync, mkdirSync, renameSync } from "node:fs"
import { join, dirname } from "node:path"
import type { Plugin } from "@opencode-ai/plugin"

const STATE_PATH = join(".opencode", ".chatlog-state.json")
let logPath = "PROMPT.md"

function now() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function messagesKey(messages: Array<{ role: string; content: string }>) {
  return createHash("sha1")
    .update(JSON.stringify(messages))
    .digest("hex")
}

function textOfParts(parts: any[]): string {
  const out: string[] = []
  for (const p of parts || []) {
    if (!p || typeof p !== "object") continue
    if (p.type === "text") {
      if (p.text && !p.synthetic) out.push(p.text)
    } else if (p.type === "tool") {
      out.push(`[tool: ${p.tool} ${p.state?.status || ""}]`.trim())
    }
  }
  return out.join("\n").trim()
}

function loadState(): Record<string, string> {
  try {
    if (existsSync(STATE_PATH)) {
      return JSON.parse(readFileSync(STATE_PATH, "utf-8"))
    }
  } catch {
    /* ignore */
  }
  return {}
}

function saveState(state: Record<string, string>) {
  try {
    mkdirSync(dirname(STATE_PATH), { recursive: true })
    writeFileSync(STATE_PATH, JSON.stringify(state, null, 2))
  } catch {
    /* ignore */
  }
}

function upsertRecord(record: any) {
  try {
    mkdirSync(dirname(logPath), { recursive: true })
    let lines: string[] = []
    if (existsSync(logPath)) {
      lines = readFileSync(logPath, "utf-8").split("\n")
    }
    const json = JSON.stringify(record)
    const sid = record.session_id
    let found = false
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim()
      if (!line) continue
      try {
        const r = JSON.parse(line)
        if (r.type === "external_chat" && r.session_id === sid) {
          lines[i] = json
          found = true
          break
        }
      } catch {
        /* keep line */
      }
    }
    if (!found) {
      lines.push(json)
    }
    const tmp = logPath + ".tmp"
    writeFileSync(tmp, lines.join("\n") + "\n")
    renameSync(tmp, logPath)
  } catch {
    /* never crash opencode */
  }
}

async function flushSession(client: any, sessionID: string, state: Record<string, string>) {
  let rows: any[] = []
  try {
    const res = await client.session.messages({ path: { id: sessionID } })
    rows = res?.data || rows
  } catch {
    return
  }
  if (!Array.isArray(rows) || rows.length === 0) return

  const messages: Array<{ role: string; content: string }> = []
  for (const row of rows) {
    const info = row?.info
    const parts = row?.parts || []
    if (!info) continue
    const content = textOfParts(parts)
    if (!content) continue
    const role = info.role === "user" ? "user" : "assistant"
    messages.push({ role, content })
  }
  if (messages.length === 0) return

  const key = messagesKey(messages)
  if (state[sessionID] === key) return

  let title = `opencode session ${sessionID.slice(0, 8)}`
  try {
    const sres = await client.session.get({ path: { id: sessionID } })
    const sdata = sres?.data
    if (sdata?.title) title = String(sdata.title)
  } catch {
    /* keep default */
  }

  const record = {
    type: "external_chat",
    source: "opencode",
    key,
    timestamp: now(),
    title,
    session_id: sessionID,
    messages,
    num_messages: messages.length,
  }

  upsertRecord(record)
  state[sessionID] = key
  saveState(state)
}

export default (async ({ client, directory }) => {
  logPath = join(directory, "PROMPT.md")
  const state = loadState()

  return {
    event: async ({ event }: any) => {
      if (!event) return
      if (event.type === "session.idle" && event.properties?.sessionID) {
        await flushSession(client, event.properties.sessionID, state)
      }
    },
  }
}) satisfies Plugin
