#!/usr/bin/env bash
# Fresh-session routing retest. One independent `hermes chat` per prompt (no shared context).
# Output: .scratch/route_retest.tsv  (expected \t got \t prompt)
cd "D:/01_Job/Tool/Hermes Agent" || exit 1
OUT=.scratch/route_retest.tsv; : > "$OUT"
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
# mtk-ai-api: positives (wording = the table rows in SKILL.md)
run mtk-ai-api   "AIDE 回 500 quota is exhausted,fallback 沒有生效,怎麼查?"
run mtk-ai-api   "azure/gpt-6-luna 帶 tools 回 400 Function tools with reasoning_effort"
run mtk-ai-api   "AIDE 某個模型的 context 上限到底是多少,少了 databricks 模型"
run mtk-ai-api   "用 cch 拿個人 aide 的 token 打 gateway"
# overlap: Hermes-side symptoms must go to hermes-model-routing
run hermes-model-routing "TUI footer 顯示的 context 跟預期不同,/model 切過去後沒變"
# negatives: other skills
run teams        "怎麼拿 Graph token 發 Teams 訊息"
run mtk-people-org "幫我查某位同事的主管和組織圖"
# video-to-pkb
run video-to-pkb "把 E:\\Video\\PSA\\x.mp4 inject 進 PKB"
run webex        "更新我的會議影片到 E:\\Video,把新的 Webex 錄影下載下來"
run pkb-ingest   "這份 .md 會議記錄幫我入庫"
echo done >> "$OUT"
