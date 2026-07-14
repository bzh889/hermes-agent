"""Detect degenerate final LLM output before it enters session history.

Motivation: analysis of state.db (2026-07-12) found 24 assistant messages
with characteristic multi-script gibberish text (U+FFFD replacement chars,
random Latin/CJK/Cyrillic/Arabic word salad, dense stray-symbol soup), all
produced by AIDE-proxied in-house models on the fallback or stream-
continuation paths after 429/quota events.  These outputs were being written
into session history as compacted=0, active=1 records, then re-read into
every subsequent context window, causing cascading corruption.

Scope contract: this detector is only for model-generated final assistant
output.  Never apply it to ``role=tool`` content.  Broken or mis-decoded tool
results must remain in context so the agent can repair the tool or post-process
its output; discarding an entire tool result would destroy evidence.

The heuristic is deliberately conservative (prefer false negatives over false
positives).  The regression suite includes representative confirmed garbage,
normal technical responses, CR-derived summaries, and coherent multilingual
content.

Key design decision — two-tier script check:
  Normal bilingual output (Chinese + English) appears with avg_scripts ≈ 2.0
  (CJK + Latin).  This is *expected* and must NOT trigger.  Only penalise when
  sparse fragments of "problem scripts" (Cyrillic, Arabic, Hangul, Thai) appear
  alongside other scripts.  Coherent multilingual paragraphs and translations
  are explicitly exempt; random low-density fragments remain suspicious.

Usage::

    from agent.garbage_detector import is_garbage

    if is_garbage(final_assistant_output):
        logger.warning("Corrupt final model output detected, retrying")
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
_THRESHOLD = 3.0      # separates bundled representative garbage/clean regressions


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
    script_counts = {name: 0 for name, _lo, _hi in _SCRIPT_RANGES}
    for ch in text:
        script = _script_of(ord(ch))
        if script is not None:
            script_counts[script] += 1
    # A script used consistently across the response is coherent multilingual
    # content, not contamination.  Garbage corpus samples contain only sparse,
    # isolated fragments of the unexpected scripts.
    coherent_floor = min(50, max(12, int(n * 0.02)))
    coherent_problem_scripts = {
        script for script in _PROBLEM_SCRIPTS
        if script_counts[script] >= coherent_floor
    }
    # Do not let a fixed-width window cross natural line boundaries.  A normal
    # CR or translation can contain one coherent language per paragraph; the
    # previous whole-string scan combined the end of an Arabic paragraph with
    # the start of a Russian one and falsely treated that as script soup.
    for line in text.splitlines() or [text]:
        for i in range(0, len(line) - window, window):
            chunk = line[i : i + window]
            scripts: set[str | None] = {_script_of(ord(ch)) for ch in chunk}
            scripts.discard(None)
            problem = (scripts & _PROBLEM_SCRIPTS) - coherent_problem_scripts
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
    # Require ≥40 Latin words (raised from 20) to avoid triggering on
    # bilingual content where isolated technical terms (variable names,
    # CR IDs, bug IDs) push past the old 20-word floor but are not
    # part of coherent English prose.
    latin_words = re.findall(r"[A-Za-z]+", text)
    if len(latin_words) >= 40:
        long_runs = len(re.findall(r"(?:[A-Za-z]+\s+){4,}[A-Za-z]+", text))
        run_density = long_runs / (len(latin_words) / 20)
        if run_density < 0.2:
            score += (0.2 - run_density) * 8

    # ── Signal 4: High stray-symbol density ──────────────────────────────
    # Strip HTML tags first so that <td>, <tr>, <div>, style attrs etc. don't
    # inflate the symbol count on legitimate formatted output (HTML tables,
    # branded message wrappers).  Only the *text* content is scored.
    _stripped = re.sub(r"<[^>]+>", "", text)
    _sn = len(_stripped) if _stripped else 1
    if _sn >= _MIN_CHARS:
        symbol_ratio = sum(1 for ch in _stripped if ch in _SYMBOL_SET) / _sn
    else:
        symbol_ratio = sum(1 for ch in text if ch in _SYMBOL_SET) / n
    if symbol_ratio > 0.06:
        score += (symbol_ratio - 0.06) * 40

    return score


def is_garbage(text: str | None) -> bool:
    """Return True if final model output looks degenerate or corrupted.

    Designed for fast in-loop use (pure Python, no I/O, ~microseconds per
    call).  Errs on the side of *not* flagging real output: only clearly
    corrupted text exceeds the threshold.  Returns False for None/empty/short
    content unconditionally.

    This function must never be called for tool-result content.  Tool output is
    evidence to preserve and repair, not model output eligible for discard.
    """
    if not text or len(text) < _MIN_CHARS:
        return False
    return _garbage_score(text) >= _THRESHOLD
