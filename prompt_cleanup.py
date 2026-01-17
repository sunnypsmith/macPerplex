"""
Prompt cleanup (Groq) for macPerplex.

Goal: take a raw speech-to-text transcript and return a cleaned version that:
- preserves meaning
- fixes punctuation/casing/spacing
- removes filler words and obvious transcription noise
- does NOT expand or add assumptions

This module is intentionally dependency-light: it uses `requests` against Groq's
OpenAI-compatible Chat Completions API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CleanupConfig:
    api_key: str
    model: str
    base_url: str = "https://api.groq.com/openai/v1"
    timeout_s: float = 2.5


_SYSTEM_PROMPT = """You are a transcription cleanup engine.

Rewrite the user's text with STRICT cleanup-only rules:
- Preserve meaning exactly. Do not add new ideas, facts, assumptions, or steps.
- Do not expand the request. Do not make it more detailed.
- Preserve the user's intent and *speech act* (question vs command vs statement).
  - If the input is a question, the output MUST remain a question.
  - Do NOT turn a question into advice (e.g., do NOT rewrite "Can you...?" into "You should...").
- Do NOT remove or summarize any substantive context (background details, constraints, entities, environment).
  - Keep platform/product/context words (e.g., "Ubuntu", "smartctl", "Perplexity", filenames, error codes).
  - You may remove only filler words and obvious STT noise; do not delete meaningful clauses.
- Remove filler words (um, uh, like) and obvious STT artifacts.
- Fix punctuation, casing, and spacing.
- Keep technical terms, filenames, code identifiers, and acronyms unchanged.
- Keep the output as a single line (no newlines).

Return ONLY the cleaned text. No preamble, no quotes, no bullet points.
"""


def _collapse_whitespace(s: str) -> str:
    return " ".join((s or "").strip().split())


def cleanup_prompt_via_groq(text: str, cfg: CleanupConfig) -> Optional[str]:
    """
    Returns cleaned text, or None if Groq is unavailable / request fails.
    """
    text = _collapse_whitespace(text)
    if not text:
        return None

    # Import locally to keep module import cheap if feature is disabled.
    import requests

    url = f"{(cfg.base_url or '').rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.model,
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=cfg.timeout_s)
        if resp.status_code != 200:
            return None

        data = resp.json()
        content = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        cleaned = _collapse_whitespace(content)
        return cleaned or None
    except Exception:
        return None

