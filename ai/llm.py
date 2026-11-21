"""Groq (OpenAI-compatible) chat client used as an explanation layer on every page.

The model only narrates numbers the platform computed; it never produces or alters results.
The API key is read from the sidebar, st.secrets or the GROQ_API_KEY environment variable and is never stored in the repo.
"""
from __future__ import annotations
import json
import requests

BASE = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

SYSTEM = (
    "You are a rigorous process-engineering analyst for a biochar screening platform. "
    "The supplied snapshot may include computed results, governing equations, calculation-log rows, "
    "source metadata and assumptions. Use only supplied numerical values; do not invent calculations, "
    "citations, prices or missing inputs. Explicitly distinguish measured/literature-derived values, "
    "user inputs, defaults and placeholders. Never call a screening proxy verified, bankable or creditable. "
    "For technical questions, explain: (1) quantity being calculated and its units; (2) governing equation; "
    "(3) numerical substitution using the supplied log; (4) result and physical interpretation; "
    "(5) dominant contributors or sensitivity if supported by supplied data; (6) assumptions, validity range "
    "and limitations; (7) what evidence or measurement is needed next. Explain every relevant term rather "
    "than paraphrasing the result. If an equation's required property or input is absent, say so. "
    "For non-technical pages, answer in a structured, evidence-led way and distinguish source facts from inference. "
    "Be detailed enough to teach an engineering student; do not impose an arbitrary five-bullet limit."
)

class LLMError(Exception):
    pass

def _headers(key): return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def list_models(key: str, post=None, timeout=15) -> list[str]:
    try:
        r = requests.get(f"{BASE}/models", headers=_headers(key), timeout=timeout)
    except requests.RequestException as ex:
        raise LLMError(f"Network error: {ex}")
    if r.status_code != 200: raise LLMError(_err(r))
    return sorted(m["id"] for m in r.json().get("data", []) if "whisper" not in m["id"] and "guard" not in m["id"])

def _err(r) -> str:
    try: msg = r.json().get("error", {}).get("message", r.text)
    except Exception: msg = r.text
    hint = {401: " (check the API key)", 404: " (model not found: pick another model in the sidebar)", 429: " (rate limited: wait and retry)"}.get(r.status_code, "")
    return f"Groq API error {r.status_code}: {msg[:300]}{hint}"

def ask(page: str, snapshot: dict, question: str | None, key: str, model: str = DEFAULT_MODEL,
        history: list | None = None, post=requests.post, timeout=45) -> str:
    if not key: raise LLMError("No API key set.")
    task = question or "Explain these results: what is driving them, what looks risky or inconsistent, and what to do next."
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"PAGE: {page}\nSNAPSHOT (JSON):\n{json.dumps(snapshot, default=str)[:12000]}"}]
    msgs += (history or [])[-6:]
    msgs.append({"role": "user", "content": task})
    try:
        r = post(f"{BASE}/chat/completions", headers=_headers(key), timeout=timeout,
                 json={"model": model, "messages": msgs, "temperature": 0.2, "max_tokens": 1400})
    except requests.RequestException as ex:
        raise LLMError(f"Network error: {ex}")
    if r.status_code != 200: raise LLMError(_err(r))
    try: return r.json()["choices"][0]["message"]["content"].strip()
    except Exception: raise LLMError("Unexpected response format from the API.")
