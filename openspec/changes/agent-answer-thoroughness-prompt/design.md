# agent-answer-thoroughness-prompt

全域 `agent.system_prompt` self-reflection 設定：修復 echo-loop bug 移除後 agent
不再被動重試，改用全域提示引導 agent 主動檢查工具使用。

## Scope Correction

此變更**原本被誤放進 `teams-mtk-answer-reliability`**（Teams 專屬 spec），
已移除歸屬並重新獨立成 spec。理由：

- `agent.system_prompt` 是 `~/.hermes/config.yaml` 的**全域**設定
  （見 `gateway/run.py:4406` `cfg_get(cfg, "agent", "system_prompt", ...)`），
  影響**所有平台**的所有對話，不是 Teams 特定行為。
- 錯置的後果：若日後要單獨關閉/調整此提示，開發者會去 Teams spec 找，找不到；
  若要 revert Teams 專屬修復，也可能誤連動改到全域提示。

## Background

Teams echo-loop bug（agent 對自己發的訊息重複觸發）修掉後（見
`teams-mtk-answer-reliability` §5.1 echo guard），副作用是 agent 不再有
「被動重試」的機制驅動它多想一輪。原本這個 bug 意外造成的重試，讓部分過於
簡短的回答會被迫重跑；修掉之後，如果 agent 第一輪回答草率，不會再有第二次
機會。

## Design

在 `config.yaml` `agent.system_prompt` 加入 self-reflection 指示：

```yaml
agent:
  system_prompt: >
    Before finishing your response, ask yourself: "Is my answer thorough
    enough for the user's question?" If the question requires research
    and you have not used any tools yet, you MUST use web_search,
    web_extract, or delegate_task before answering. A superficial answer
    is worse than a delayed thorough one.
```

**為何選這個字串而非打分數式提示**：檢查「有沒有用工具」是客觀事實（可由
`tool_calls` 是否為空來驗證），檢查「回答好不好」是主觀判斷，容易被模型自我
說服「已經夠好」。客觀檢查比主觀評分更可靠。

## Retracted / Not Yet Verified

- ~~"echo loop 修掉後只跑一次不會被動 retry" 已完整解決~~ — 目前只是
  config-level 快解，**未經真實 A/B 對照驗證**（沒有同一問題測過「有此
  prompt / 無此 prompt」的回答品質差異）。這是暫時緩解，非長期正解。
- 長期正解仍是 P7 Persona + streaming 策略（見 teams-mtk-streaming-reliability
  的 backlog），本 spec 只覆蓋短期 config 快解。

## Verification Status

- [x] 設定已寫入 `~/.hermes/config.yaml`（本機環境，非 repo 內建 config）
- [ ] **未做**：A/B 測試證明此 prompt 確實改善回答品質
- [ ] **未做**：確認此 prompt 不會誤觸發（例如簡單問候也被迫查工具）
