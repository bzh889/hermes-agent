#!/usr/bin/env bash
# Fresh-session routing retest. One independent `hermes chat` per prompt (no shared context).
# Output: .scratch/route_retest.tsv  (expected \t got \t prompt)
cd "D:/01_Job/Tool/Hermes Agent" || exit 1
OUT=.scratch/route_heldout.tsv; : > "$OUT"
PREFIX='Routing test only. Do NOT perform the task and do NOT call any tool except those needed to inspect the skill list. Reply with exactly one line: SKILL=<name> naming the single installed skill you would load FIRST for this request. Request: '
run() {
  local expected="$1"; shift
  local prompt="$*"
  local got
  got=$(timeout 150 ./.venv/Scripts/python.exe -m hermes_cli.main chat -Q -t skills --max-turns 4 \
        --provider aide-io -m mtk/wfm-plus-deepseek-v4-flash -q "${PREFIX}${prompt}" 2>&1 \
        | grep -oE 'SKILL=[A-Za-z0-9_.-]+' | tail -1)
  printf '%s\t%s\t%s\n' "$expected" "${got:-<none>}" "$prompt" >> "$OUT"
}
# HELD-OUT: wording that appears nowhere in SKILL.md tables
run mtk-ai-api   "gateway 回 429 了,是 AIDE 的 daily quota 用完嗎?要等到幾點才會重置"
run mtk-ai-api   "wfm-pro 實測的 context window 上限是多少 token"
run mtk-ai-api   "AIDE 上有沒有可以直接呼叫的 TTS 或 gpt-image 端點"
run jira         "幫我登入 JIRA 查某張 ticket 現在的狀態"
run video-to-pkb "把這個 mp4 會議錄影轉成 PKB 頁面"
echo done >> "$OUT"
