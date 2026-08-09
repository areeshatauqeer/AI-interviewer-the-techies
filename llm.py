import json
import os
import re
import urllib.request

import prompt_log


def _config():
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    key = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")

    if provider == "ollama":
        base = os.getenv(
            "OLLAMA_BASE_URL",
            "http://localhost:11434"
        ).rstrip("/")
        return (
            f"{base}/v1/chat/completions",
            {},
            os.getenv("LLM_MODEL", "llama3.1")
        )

    if provider == "groq":
        return (
            "https://api.groq.com/openai/v1/chat/completions",
            {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        )

    base = os.getenv(
        "OPENAI_BASE_URL",
        "https://api.openai.com/v1"
    ).rstrip("/")
    return (
        f"{base}/chat/completions",
        {"Authorization": f"Bearer {key or ''}"},
        os.getenv("LLM_MODEL", "gpt-4o-mini")
    )


def model_name():
    """Resolve the model the next call would use (for logging)."""
    return _config()[2]


def available():
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "ollama":
        return True
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY"))


def chat(messages, temperature=0.7, max_tokens=600, timeout=40):
    if not available():
        return None

    url, headers, model = _config()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower() or "openai"
    headers["Content-Type"] = "application/json"

    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST"
    )

    record = {
        "type": "llm_call",
        "timestamp": prompt_log.now(),
        "provider": provider,
        "model": model,
        "endpoint": url,
        "messages": messages,
        "response": None,
        "ok": False,
    }

    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[llm] request failed: {exc}")
        record["error"] = str(exc)
        prompt_log.log_usage_record(record)
        return None

    record["ok"] = True
    record["response"] = content
    prompt_log.log_usage_record(record)
    return content


def chat_json(messages, **kwargs):
    text = chat(messages, **kwargs)
    if not text:
        return None

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception as exc:
        print(f"[llm] json parse failed: {exc}")
        return None
