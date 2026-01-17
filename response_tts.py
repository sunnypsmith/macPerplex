"""
Response formatting + TL;DR extraction + local macOS TTS helpers.

Designed to be resilient:
- Prefer strict marker-based parsing, with safe fallbacks.
- Use built-in macOS `say` for low-latency local TTS.
- Provide Selenium scraping helpers to retrieve the latest Perplexity response text.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
import time
from typing import Optional


def _single_line(s: str) -> str:
    """Normalize to a single line (prevents accidental newline behavior in prompt inputs)."""
    return " ".join((s or "").strip().split())


@dataclass(frozen=True)
class TLDRFormatConfig:
    """
    Marker-based response format.

    We keep markers very unlikely to appear in normal text so parsing is deterministic.
    """

    tldr_marker: str = "<<<TLDR>>>"
    full_marker: str = "<<<FULL>>>"
    end_marker: str = "<<<END>>>"
    tldr_sentences: int = 2

    def build_append_hint(self) -> str:
        """
        Return a single-line instruction to append to user prompts.
        Note: Output is intentionally one line to avoid UI auto-submit edge cases.
        """
        n = max(1, int(self.tldr_sentences))
        return _single_line(
            f"Respond in EXACTLY this format: "
            f"{self.tldr_marker} <TL;DR in {n} sentence(s)> "
            f"{self.full_marker} <full answer> "
            f"{self.end_marker} (include the markers verbatim)."
        )


def extract_sections(response_text: str, cfg: TLDRFormatConfig) -> tuple[str, str]:
    """
    Extract (tldr, full) from a marker-formatted response.
    - TL;DR is between TLDR_MARKER and FULL_MARKER (or END_MARKER if FULL missing).
    - FULL is between FULL_MARKER and END_MARKER (or end-of-text if END missing).
    - If markers are present but malformed, returns ("", "") to avoid mis-speaking.
    """
    text = (response_text or "").strip()
    if not text:
        return ("", "")

    tldr_m = cfg.tldr_marker
    full_m = cfg.full_marker
    end_m = cfg.end_marker

    tldr_pos = text.find(tldr_m) if tldr_m else -1
    if tldr_pos == -1:
        return ("", "")

    after_tldr = text[tldr_pos + len(tldr_m) :]

    full_pos = after_tldr.find(full_m) if full_m else -1
    end_pos = after_tldr.find(end_m) if end_m else -1

    # TL;DR ends at FULL (preferred) or END (fallback)
    tldr_end_candidates = [i for i in (full_pos, end_pos) if i != -1]
    if not tldr_end_candidates:
        return ("", "")
    tldr_end = min(tldr_end_candidates)
    tldr = after_tldr[:tldr_end].strip()

    # FULL starts at FULL marker if present
    full = ""
    if full_pos != -1:
        after_full = after_tldr[full_pos + len(full_m) :]
        end_in_full = after_full.find(end_m) if end_m else -1
        if end_in_full != -1:
            full = after_full[:end_in_full].strip()
        else:
            full = after_full.strip()

    return (tldr, full)


def extract_tldr_lenient(response_text: str, cfg: TLDRFormatConfig) -> str:
    """
    Lenient TL;DR extraction intended for TTS:
    - If TLDR_MARKER exists, take everything after it up to FULL/END if present.
    - If FULL/END not present, take first N sentences (cfg.tldr_sentences) of the remaining text.
    - Never returns content after FULL/END.
    """
    text = (response_text or "").strip()
    if not text:
        return ""

    if cfg.tldr_marker and cfg.tldr_marker in text:
        tldr, _full = extract_sections(text, cfg)
        if tldr:
            return tldr

        # Markers present but malformed/missing terminator: take bounded snippet after TLDR marker.
        start = text.find(cfg.tldr_marker)
        if start != -1:
            after = text[start + len(cfg.tldr_marker) :].strip()
            if not after:
                return ""
            n = max(1, int(cfg.tldr_sentences))
            parts = re.split(r"(?<=[.!?])\s+", after)
            return " ".join([p.strip() for p in parts[:n] if p.strip()]).strip()

    # No markers: fallback to first non-empty line
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def extract_tldr(response_text: str, cfg: TLDRFormatConfig) -> str:
    """
    Extract TL;DR from the model response using markers.
    Fallback: first paragraph / first non-empty line.
    """
    text = (response_text or "").strip()
    if not text:
        return ""

    if cfg.tldr_marker and cfg.tldr_marker in text:
        tldr, _full = extract_sections(text, cfg)
        return tldr

    # Fallback: first non-empty paragraph/line
    for part in text.splitlines():
        p = part.strip()
        if p:
            return p
    return text


@dataclass(frozen=True)
class LocalTTSConfig:
    enabled: bool = False
    voice: str = ""  # empty -> default system voice
    rate_wpm: int = 200
    max_chars: int = 700  # keep spoken output short
    block: bool = False  # False -> speak asynchronously


def speak_local_mac(text: str, cfg: LocalTTSConfig) -> bool:
    """
    Speak text using macOS `say`. Returns True if a speak attempt was made.
    """
    if not cfg.enabled:
        return False

    msg = (text or "").strip()
    if not msg:
        return False

    if cfg.max_chars and len(msg) > cfg.max_chars:
        msg = msg[: cfg.max_chars].rstrip() + "…"

    cmd = ["say"]
    if cfg.voice:
        cmd += ["-v", cfg.voice]
    if cfg.rate_wpm:
        cmd += ["-r", str(int(cfg.rate_wpm))]
    cmd.append(msg)

    try:
        if cfg.block:
            subprocess.run(cmd, check=False)
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def find_response_nodes(driver):
    """
    Return candidate DOM nodes that likely contain assistant responses.
    We use multiple selectors to be resilient to Perplexity UI changes.
    """
    xpaths = [
        # Common "answer prose" container
        # Prefer div.prose containers (avoid matching li.prose-p* citation bullets)
        "//main//div[contains(@class,'prose')]",
        # Generic message blocks (fallback)
        "//main//div[@role='article']",
        "//main//article",
    ]
    nodes = []
    for xp in xpaths:
        try:
            found = driver.find_elements("xpath", xp)
            if found:
                nodes.extend(found)
        except Exception:
            continue
    return nodes


def count_response_nodes(driver) -> int:
    """Convenience wrapper used for before/after detection."""
    try:
        return len(find_response_nodes(driver))
    except Exception:
        return 0


def wait_for_latest_response_text(
    driver,
    *,
    timeout_s: float = 60.0,
    settle_s: float = 1.0,
    poll_s: float = 0.25,
    before_count: Optional[int] = None,
    prefer_marker: Optional[str] = None,
    require_all: Optional[list[str]] = None,
    require_any: Optional[list[str]] = None,
    return_immediately_if_contains: Optional[list[str]] = None,
    exclude_texts: Optional[list[str]] = None,
) -> str:
    """
    Poll the page for the latest assistant response text.

    Strategy:
    - Track candidate response nodes count; wait for it to increase (if before_count given).
    - Once we have non-empty text, wait for it to "settle" (unchanged for settle_s).
    """
    deadline = time.time() + float(timeout_s)
    last_text = ""
    last_change_t = time.time()

    while time.time() < deadline:
        try:
            nodes = find_response_nodes(driver)
            if before_count is not None and len(nodes) <= before_count:
                time.sleep(poll_s)
                continue

            # Prefer the last node with non-empty text
            txt = ""
            if prefer_marker:
                for node in reversed(nodes):
                    try:
                        t = (node.text or "").strip()
                    except Exception:
                        t = ""
                    if t and prefer_marker in t:
                        txt = t
                        break

            if not txt:
                for node in reversed(nodes):
                    try:
                        t = (node.text or "").strip()
                    except Exception:
                        t = ""
                    if t:
                        txt = t
                        break

            if not txt:
                time.sleep(poll_s)
                continue

            if exclude_texts and any(txt == ex for ex in exclude_texts if ex):
                time.sleep(poll_s)
                continue

            if require_all and any(req not in txt for req in require_all):
                time.sleep(poll_s)
                continue
            if require_any and not any(req in txt for req in require_any):
                time.sleep(poll_s)
                continue

            if return_immediately_if_contains and any(m in txt for m in return_immediately_if_contains):
                return txt

            if txt != last_text:
                last_text = txt
                last_change_t = time.time()
                time.sleep(poll_s)
                continue

            if time.time() - last_change_t >= float(settle_s):
                return last_text
        except Exception:
            # DOM changing rapidly; just keep polling
            time.sleep(poll_s)

    return last_text

