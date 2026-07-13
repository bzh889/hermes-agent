"""Benchmark candidate fallback models for stability under repeated / long-context
load, to pick real fallback_providers entries instead of guessing by name.

For each (provider, model) candidate:
  - Fire N requests with an artificially large context (~40k-80k tokens of
    real-ish text, mimicking a long session) + a request that specifically
    forces a long completion (to stress output generation, since observed
    garbage outputs were long completions after long context).
  - Measure: success rate, latency, and a garbage-output heuristic score.

Garbage heuristic (matches the actual observed corruption pattern from
session state.db analysis 2026-07-12):
  - High density of the U+FFFD replacement character
  - High density of isolated short tokens (<=3 chars) separated by spaces/
    brackets with no coherent multi-word phrases (bag-of-fragments pattern)
  - Language-mixing entropy: many distinct Unicode scripts appearing in a
    short window (Latin+CJK+Cyrillic+Arabic in the same paragraph is a red
    flag; normal multilingual output doesn't randomly interleave scripts
    mid-sentence)

Run: python scripts/benchmark_fallback_candidates.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hermes_cli.config import load_config  # noqa: E402

CANDIDATES: list[dict[str, str]] = [
    {"provider": "aide", "model": "mtk/wfm-pro-glm5-1-744b"},   # current primary/fallback baseline
    {"provider": "aide", "model": "mtk/glm-5-1"},                # observed garbage source
    {"provider": "aide", "model": "mtk/qwen3-5-397b-a17b"},      # candidate 1
    {"provider": "aide", "model": "mtk/qwen3-5-122b-a10b"},      # candidate 2 (smaller qwen)
    {"provider": "aide", "model": "mtk/wfm-reasoning-oa-qwen3-thinking-235b"},  # candidate 3
    {"provider": "aide", "model": "mtk/gpt-oss-120b"},           # candidate 4
    {"provider": "aide", "model": "mtk/wfm-flash-oa-gpt-oss-120b"},  # candidate 5
]

N_TRIALS = 4          # requests per candidate
LONG_CONTEXT_CHARS = 60_000  # ~40-60k tokens filler, matches observed 60-130k token sessions
FORCE_LONG_OUTPUT_PROMPT = (
    "Write a detailed, structured technical summary (at least 1500 words) covering: "
    "(1) how HTTP long-polling works, (2) common failure modes in long-lived TCP "
    "connections behind corporate proxies, (3) a step-by-step retry/backoff design, "
    "and (4) a worked example in pseudocode. Be exhaustive and use full sentences "
    "throughout — this is a stress test for sustained coherent generation, not a summary."
)

_SCRIPT_RANGES = {
    "Latin": (0x0041, 0x007A),
    "CJK": (0x4E00, 0x9FFF),
    "Cyrillic": (0x0400, 0x04FF),
    "Arabic": (0x0600, 0x06FF),
    "Hangul": (0xAC00, 0xD7A3),
    "Thai": (0x0E00, 0x0E7F),
}


def _script_of(ch: str) -> str | None:
    cp = ord(ch)
    for name, (lo, hi) in _SCRIPT_RANGES.items():
        if lo <= cp <= hi:
            return name
    return None


def garbage_score(text: str) -> dict[str, Any]:
    """Return a dict of garbage-heuristic signals; higher = more suspicious."""
    if not text:
        return {"score": 0.0, "reasons": ["empty"]}

    reasons = []
    score = 0.0

    n = len(text)
    fffd_count = text.count("\ufffd")
    fffd_ratio = fffd_count / n
    if fffd_ratio > 0.001:
        score += min(fffd_ratio * 500, 5.0)
        reasons.append(f"replacement_char_ratio={fffd_ratio:.4f}")

    # Script-mixing entropy: count distinct scripts appearing in each
    # sliding 40-char window; average distinct-script count per window.
    scripts_per_window = []
    window = 40
    for i in range(0, n - window, window):
        chunk = text[i:i + window]
        scripts = {s for ch in chunk if (s := _script_of(ch))}
        scripts_per_window.append(len(scripts))
    if scripts_per_window:
        avg_scripts = sum(scripts_per_window) / len(scripts_per_window)
        max_scripts = max(scripts_per_window)
        if avg_scripts > 1.3:
            score += (avg_scripts - 1.0) * 2
            reasons.append(f"avg_scripts_per_window={avg_scripts:.2f}")
        if max_scripts >= 3:
            score += 2.0
            reasons.append(f"max_scripts_per_window={max_scripts}")

    # Fragment-soup pattern: short bracket/paren fragments with no long
    # coherent word run. Count runs of >=4 consecutive alphabetic words
    # (a proxy for "coherent sentence exists") vs total word count.
    words = re.findall(r"[A-Za-z\u4e00-\u9fff]+", text)
    total_words = len(words)
    long_runs = len(re.findall(r"(?:[A-Za-z]+\s+){4,}[A-Za-z]+", text))
    if total_words > 50:
        run_density = long_runs / (total_words / 20)
        if run_density < 0.3:
            score += (0.3 - run_density) * 10
            reasons.append(f"low_coherent_run_density={run_density:.3f}")

    # Excessive stray punctuation/bracket density (bag-of-symbols pattern)
    symbol_count = sum(1 for ch in text if ch in "[]{}()<>|�°∙›⟩‌‍")
    symbol_ratio = symbol_count / n
    if symbol_ratio > 0.03:
        score += (symbol_ratio - 0.03) * 50
        reasons.append(f"symbol_ratio={symbol_ratio:.4f}")

    return {"score": round(score, 3), "reasons": reasons}


def build_filler_context(target_chars: int) -> str:
    """Deterministic filler text that resembles real session content (mixed
    code/log/prose) rather than pure repetition, to better match the
    conditions under which garbage output was actually observed."""
    unit = (
        "2026-07-11 05:26:12,045 INFO gateway.platforms.teams_mtk: TeamsMTK: "
        "inspecting msg id=1783718771143 type=RichText/Html conv=19:6e8a676c\n"
        "def _process_new_messages(self, conv_id, messages):\n"
        "    for msg in messages:\n"
        "        content = msg.get('content', '')\n"
        "        # strip HTML entities and normalize whitespace before dispatch\n"
        "澳門特別行政區政府 has announced updated guidance regarding cross-border "
        "logistics; 詳細內容請參閱附件。The gateway retried the request three times "
        "before falling back to the secondary endpoint, logging a WARNING each time.\n"
    )
    reps = (target_chars // len(unit)) + 1
    return (unit * reps)[:target_chars]


def resolve_api_key(provider_cfg: dict[str, Any]) -> str:
    key_env = provider_cfg.get("key_env")
    if key_env:
        import os
        val = os.getenv(key_env, "").strip()
        if val:
            return val
    helper = provider_cfg.get("api_key_helper")
    if helper:
        try:
            out = subprocess.run(helper.split() if " " in helper else [helper, "key"],
                                  capture_output=True, text=True, timeout=15)
            val = out.stdout.strip()
            if val:
                return val
        except Exception:
            pass
    return ""


def call_model(provider_name: str, provider_cfg: dict[str, Any], model: str,
                context_filler: str) -> dict[str, Any]:
    api_base = provider_cfg["api"].rstrip("/")
    api_key = resolve_api_key(provider_cfg)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(provider_cfg.get("default_headers", {}))

    messages = [
        {"role": "system", "content": "You are a helpful technical assistant."},
        {"role": "user", "content": f"BACKGROUND LOG CONTEXT (reference only):\n{context_filler}"},
        {"role": "assistant", "content": "Understood, I have reviewed the background context."},
        {"role": "user", "content": FORCE_LONG_OUTPUT_PROMPT},
    ]

    t0 = time.monotonic()
    try:
        resp = requests.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "max_tokens": 2000, "temperature": 0.7},
            timeout=120,
            verify=False,
        )
        latency = time.monotonic() - t0
        if resp.status_code != 200:
            return {"ok": False, "status": resp.status_code, "latency": latency,
                    "error": resp.text[:300]}
        data = resp.json()
        content = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
            or ""
        )
        gscore = garbage_score(content)
        return {
            "ok": True, "status": 200, "latency": round(latency, 1),
            "output_chars": len(content), "garbage": gscore,
            "sample": content[:200],
        }
    except Exception as e:
        return {"ok": False, "status": None, "latency": time.monotonic() - t0,
                "error": str(e)[:300]}


def main() -> None:
    cfg = load_config()
    providers_cfg = cfg.get("providers", {})
    context_filler = build_filler_context(LONG_CONTEXT_CHARS)

    results: dict[str, list[dict[str, Any]]] = {}
    for cand in CANDIDATES:
        key = f"{cand['model']} (via {cand['provider']})"
        provider_cfg = providers_cfg.get(cand["provider"])
        if not provider_cfg:
            results[key] = [{"ok": False, "error": "provider not in config"}]
            continue
        trials = []
        for i in range(N_TRIALS):
            print(f"[{key}] trial {i+1}/{N_TRIALS}...", flush=True)
            trials.append(call_model(cand["provider"], provider_cfg, cand["model"], context_filler))
            time.sleep(1.0)
        results[key] = trials

    print("\n" + "=" * 100)
    print(f"{'Candidate':<55} {'OK':>4} {'AvgLatency':>11} {'AvgGarbage':>11} {'MaxGarbage':>11}")
    print("-" * 100)
    summary = []
    for key, trials in results.items():
        ok_trials = [t for t in trials if t.get("ok")]
        n_ok = len(ok_trials)
        avg_lat = sum(t["latency"] for t in ok_trials) / n_ok if n_ok else float("nan")
        garbage_scores = [t["garbage"]["score"] for t in ok_trials if "garbage" in t]
        avg_g = sum(garbage_scores) / len(garbage_scores) if garbage_scores else float("nan")
        max_g = max(garbage_scores) if garbage_scores else float("nan")
        summary.append((key, n_ok, avg_lat, avg_g, max_g))
        print(f"{key:<55} {n_ok:>2}/{len(trials)} {avg_lat:>10.1f}s {avg_g:>11.2f} {max_g:>11.2f}")

    out_path = REPO_ROOT / "scripts" / "benchmark_fallback_candidates_result.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull raw results written to: {out_path}")
    print("=" * 100)


if __name__ == "__main__":
    main()
