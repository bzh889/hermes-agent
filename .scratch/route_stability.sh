#!/usr/bin/env bash
# Routing STABILITY test: 8 held-out prompts x 3 independent fresh sessions (read-only).
# Output: .scratch/route_stability.tsv  (rep \t expected \t got \t status \t prompt)
cd "D:/01_Job/Tool/Hermes Agent" || exit 1
OUT=.scratch/route_stability.tsv; : > "$OUT"
PREFIX='Routing test only. Do NOT perform the task and do NOT call any tool except those needed to inspect the skill list. Reply with exactly one line: SKILL=<name> naming the single installed skill you would load FIRST for this request. Request: '
run() {
  local rep="$1" expected="$2"; shift 2
  local prompt="$*" raw got status
  raw=$(timeout 170 ./.venv/Scripts/python.exe -m hermes_cli.main chat -Q -t skills --max-turns 4 \
        --provider aide-io -m mtk/wfm-plus-deepseek-v4-flash -q "${PREFIX}${prompt}" 2>&1)
  rc=$?
  got=$(printf '%s' "$raw" | grep -oE 'SKILL=[A-Za-z0-9_.-]+' | tail -1)
  if [ -n "$got" ]; then status=ok; elif [ "$rc" = 124 ]; then status=TIMEOUT; else status=NOANSWER; fi
  printf '%s\t%s\t%s\t%s\t%s\n' "$rep" "$expected" "${got:-<none>}" "$status" "$prompt" >> "$OUT"
}
CASES=(
 "mtk-ai-api|gateway 回 429 了,是 AIDE 的 daily quota 用完嗎?要等到幾點才會重置"
 "mtk-ai-api|wfm-pro 實測的 context window 上限是多少 token"
 "mtk-ai-api|AIDE 上有沒有可以直接呼叫的 TTS 或 gpt-image 端點"
 "mtk-ai-api|fallback_providers 用同一個 AIDE 帳號為什麼還是 500"
 "video-to-pkb|把這個 mp4 會議錄影轉成 PKB 頁面"
 "video-to-pkb|這批 E:\\Video 的影片要 ingest 進知識庫,STT 用哪個 gw-account"
 "webex|幫我把今天 Webex 的新錄影抓下來存到 E:\\Video"
 "jira|幫我登入 JIRA 查某張 ticket 現在的狀態"
)
for rep in 1 2 3; do
  for c in "${CASES[@]}"; do
    run "$rep" "${c%%|*}" "${c#*|}"
  done
done
echo done >> "$OUT"
