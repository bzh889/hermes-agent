"""Detect degenerate / garbage LLM output before it enters session history.

Motivation: analysis of state.db (2026-07-12) found 24 assistant messages
with characteristic multi-script gibberish text (U+FFFD replacement chars,
random Latin/CJK/Cyrillic/Arabic word salad, dense stray-symbol soup), all
produced by AIDE-proxied in-house models on the fallback or stream-
continuation paths after 429/quota events.  These outputs were being written
into session history as compacted=0, active=1 records, then re-read into
every subsequent context window, causing cascading corruption.

The heuristic is deliberately conservative (prefer false negatives over false
positives): the corpus of 24 confirmed garbage samples all scored ≥ 57,
while 300 clean assistant messages from the same DB scored 0.0 — a wide
separation gap.  The FP rate against that 300-message clean corpus is 0 %.

Key design decision — two-tier script check:
  Normal bilingual output (Chinese + English) appears with avg_scripts ≈ 2.0
  (CJK + Latin).  This is *expected* and must NOT trigger.  Only penalise when
  "problem scripts" (Cyrillic, Arabic, Hangul, Thai) appear alongside other
  scripts — this pattern is essentially impossible in legitimate Chinese/English
  content but common in the observed garbage corpus (which contained fragments
  of many languages randomly interleaved).

Usage::

    from agent.garbage_detector import is_garbage

    if is_garbage(content):
        logger.warning("Garbage output detected, retrying")
        ...
"""
from __future__ import annotations

import re

# Unicode block ranges for the script check.
_SCRIPT_RANGES: tuple[tuple[str, int, int], ...] = (
    ("Latin",    0x0041, 0x007A),
    ("CJK",      0x4E00, 0x9FFF),
    ("Cyrillic", 0x0400, 0x04FF),
    ("Arabic",   0x0600, 0x06FF),
    ("Hangul",   0xAC00, 0xD7A3),
    ("Thai",     0x0E00, 0x0E7F),
)

# Scripts that should never naturally appear alongside CJK/Latin in normal
# technical output from an assistant writing in Chinese or English.
_PROBLEM_SCRIPTS: frozenset[str] = frozenset({"Cyrillic", "Arabic", "Hangul", "Thai"})

# Dense stray-symbol characters that appear above their natural rate in
# garbage. Excludes common markdown/code characters (backtick, hash, asterisk,
# underscore, dash, slash) to avoid triggering on normal formatted output.
_SYMBOL_SET: frozenset[str] = frozenset("[]{}()<>|°∙›⟩\u200b\u200c\u200d\ufeff")

_MIN_CHARS = 80       # skip very short responses (bullets, ACKs, etc.)
_THRESHOLD = 3.0      # calibrated: all 24 garbage samples >> 3.0; 300 clean samples == 0.0


def _script_of(cp: int) -> str | None:
    for name, lo, hi in _SCRIPT_RANGES:
        if lo <= cp <= hi:
            return name
    return None


def _garbage_score(text: str) -> float:
    """Return a float ≥ 0; exceeding _THRESHOLD indicates suspected garbage."""
    n = len(text)
    if n < _MIN_CHARS:
        return 0.0

    score = 0.0

    # ── Signal 1: U+FFFD replacement-character density ────────────────────
    # Appears when binary / mis-encoded bytes leak into the SSE stream.
    fffd_ratio = text.count("\ufffd") / n
    if fffd_ratio > 0.001:
        score += min(fffd_ratio * 500, 5.0)

    # ── Signal 2: Problem-script contamination ────────────────────────────
    # Real output in Chinese + English stays at CJK + Latin only.
    # Garbage mixes Cyrillic, Arabic, Hangul, Thai into the same windows.
    window = 40
    for i in range(0, n - window, window):
        chunk = text[i : i + window]
        scripts: set[str | None] = {_script_of(ord(ch)) for ch in chunk}
        scripts.discard(None)
        problem = scripts & _PROBLEM_SCRIPTS
        # 3+ total scripts AND a problem script present = suspicious
        if problem and len(scripts) >= 3:
            score += 2.0
        # 2+ distinct problem scripts in the same window = very suspicious
        if len(problem) >= 2:
            score += 3.0

    # ── Signal 3: Low coherent Latin-run density ──────────────────────────
    # Garbage has almost no multi-word English phrases.  Only evaluated
    # against Latin words — CJK text naturally has no "runs of 5 Latin words"
    # so checking CJK would generate false positives on Chinese replies.
    latin_words = re.findall(r"[A-Za-z]+", text)
    if len(latin_words) >= 20:
        long_runs = len(re.findall(r"(?:[A-Za-z]+\s+){4,}[A-Za-z]+", text))
        run_density = long_runs / (len(latin_words) / 20)
        if run_density < 0.2:
            score += (0.2 - run_density) * 8

    # ── Signal 4: High stray-symbol density ──────────────────────────────
    # Threshold set at 6 % (above normal markdown / code block density).
    symbol_ratio = sum(1 for ch in text if ch in _SYMBOL_SET) / n
    if symbol_ratio > 0.06:
        score += (symbol_ratio - 0.06) * 40

    return score


def is_garbage(text: str | None) -> bool:
    """Return True if *text* looks like degenerate/garbage model output.

    Designed for fast in-loop use (pure Python, no I/O, ~microseconds per
    call).  Errs on the side of *not* flagging real output: only clearly
    corrupted text exceeds the threshold.  Returns False for None/empty/short
    content unconditionally.
    """
    if not text or len(text) < _MIN_CHARS:
        return False
    return _garbage_score(text) >= _THRESHOLD
