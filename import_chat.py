import argparse
import hashlib
import json
import os
import sys

import prompt_log


ROLE_MARKERS = {
    "user": ("you said:", "you:", "user:", "you asked", "me:", "human:",
             "interviewer:"),
    "assistant": ("copilot said:", "copilot:", "bing:", "assistant said:",
                  "assistant:", "ai:", "claude:", "chatgpt:", "gemini:"),
}

FILLER_PREFIXES = (
    "searching for", "generating", "thinking", "planning", "reading",
    "selecting tools", "selecting a tool", "autopilot", "sent a web page",
    "image of the web page", "badge:", "copilot uses",
)

BANNED_ROLES = {"system", "plugin", "tool", "function", "notice"}


def messages_key(messages):
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def existing_keys():
    keys = set()
    if not os.path.exists(prompt_log.LOG_PATH):
        return keys
    with open(prompt_log.LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") in ("external_chat", "attachment") \
                    and record.get("key"):
                keys.add(record["key"])
    return keys


def _clean_content(text):
    return (text or "").strip()


def parse_messages_json(data):
    if isinstance(data, dict):
        data = (
            data.get("messages") or data.get("conversation")
            or data.get("turns") or data.get("items") or []
        )
    if not isinstance(data, list):
        raise ValueError("JSON must be an array of messages or an object "
                         "with a 'messages' key")

    messages = []
    for item in data:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("author") or item.get("sender") \
            or item.get("speaker") or item.get("from")
        content = (
            item.get("content") or item.get("text") or item.get("message")
            or item.get("value")
        )
        if not content:
            continue
        role = str(role).strip().lower()
        if role in BANNED_ROLES:
            continue
        if role in ("user", "human", "you", "me"):
            role = "user"
        else:
            role = "assistant"
        content = _clean_content(content)
        if content:
            messages.append({"role": role, "content": content})

    return messages


def parse_transcript(text):
    messages = []
    current_role = None
    current_lines = []
    leading_lines = []
    saw_marker = False

    def flush():
        nonlocal current_role, current_lines
        if current_role is None:
            return
        content = "\n".join(current_lines).strip()
        if content:
            messages.append({"role": current_role, "content": content})
        current_role = None
        current_lines = []

    def flush_leading():
        nonlocal leading_lines
        content = "\n".join(leading_lines).strip()
        if content:
            messages.append({"role": "user", "content": content})
        leading_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith(FILLER_PREFIXES) and len(line) < 120:
            continue

        matched = None
        for role, markers in ROLE_MARKERS.items():
            for marker in markers:
                if lower.startswith(marker):
                    matched = role
                    break
            if matched:
                break

        if matched:
            if not saw_marker:
                flush_leading()
                saw_marker = True
            flush()
            current_role = matched
            rest = line.split(":", 1)[1].strip() if ":" in line else ""
            if rest:
                current_lines.append(rest)
        else:
            if current_role:
                current_lines.append(line)
            elif not saw_marker:
                leading_lines.append(line)

    flush()
    if not saw_marker:
        flush_leading()

    if not messages:
        raise ValueError(
            "No recognizable chat turns found. Use 'You:' / 'Copilot:' "
            "markers, or supply a JSON file instead."
        )
    return messages


def read_messages(path):
    raw = open(path, "r", encoding="utf-8").read().strip()
    if not raw:
        raise ValueError(f"{path} is empty")
    try:
        data = json.loads(raw)
    except ValueError:
        return parse_transcript(raw), "transcript"
    return parse_messages_json(data), "json"


def build_record(source, title, messages, session_id=""):
    key = messages_key(messages)
    return {
        "type": "external_chat",
        "source": source,
        "key": key,
        "timestamp": prompt_log.now(),
        "title": title or "",
        "session_id": session_id or None,
        "messages": messages,
        "num_messages": len(messages),
    }


def import_messages(source, title, messages, session_id=""):
    if not messages:
        return None, False
    record = build_record(source, title, messages, session_id)
    if record["key"] in existing_keys():
        return record, False
    prompt_log.log_record(record)
    return record, True


def extract_pdf_text(path):
    import pypdf
    reader = pypdf.PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(pages).strip()
    return text, len(reader.pages)


def import_attachment(source, title, path, url=""):
    if not os.path.exists(path):
        return None, False
    filename = os.path.basename(path)
    stat = os.stat(path)
    key = hashlib.sha1(
        f"{filename}|{stat.st_size}|{stat.st_mtime}".encode("utf-8")
    ).hexdigest()
    if key in existing_keys():
        return None, False

    text, pages = extract_pdf_text(path)
    record = {
        "type": "attachment",
        "source": source,
        "key": key,
        "filename": filename,
        "title": title or filename,
        "timestamp": prompt_log.now(),
        "url": url,
        "num_pages": pages,
        "text": text,
        "text_length": len(text),
    }
    prompt_log.log_record(record)
    return record, True


def main():
    parser = argparse.ArgumentParser(
        description="Import an AI chat (Microsoft Copilot, etc.) into "
                    "PROMPT.md as an external_chat record.")
    parser.add_argument("path", nargs="?", help="Path to a chat JSON or "
                                                "transcript text file")
    parser.add_argument("--title", default="", help="Optional topic label")
    parser.add_argument("--source", default="microsoft_copilot",
                        help="AI source name (default: microsoft_copilot)")
    parser.add_argument("--url", default="",
                        help="Optional URL where the file is served from")
    args = parser.parse_args()

    if not args.path:
        parser.print_help()
        return 1

    if args.path.lower().endswith(".pdf"):
        record, is_new = import_attachment(
            args.source, args.title, args.path, url=args.url
        )
        if record is None:
            print("[import_chat] document already in log, skipping")
        elif is_new:
            print(f"[import_chat] imported document "
                  f"{record['filename']} ({record['num_pages']} pages, "
                  f"{record['text_length']} chars) as an attachment record")
        errors = prompt_log.validate_log()
        return 1 if errors else 0

    messages, fmt = read_messages(args.path)
    record = build_record(args.source, args.title, messages)
    if record is None:
        print("[import_chat] no messages to import")
        return 1

    if record["key"] in existing_keys():
        print("[import_chat] already in log, skipping duplicate")
    else:
        prompt_log.log_record(record)
        print(f"[import_chat] imported {record['num_messages']} messages "
              f"({fmt}) as an external_chat record")

    errors = prompt_log.validate_log()
    if errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
