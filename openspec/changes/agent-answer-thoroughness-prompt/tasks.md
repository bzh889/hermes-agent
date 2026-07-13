# agent-answer-thoroughness-prompt — Tasks

## 1. Config-level 快解（已完成，但未充分驗證）
- [x] 1.1 `~/.hermes/config.yaml` `agent.system_prompt` 加入 self-reflection 指示
- [ ] 1.2 **未做**：找 3-5 個過去曾出現「回答過短」的真實案例，關閉/開啟此 prompt
      各跑一次，比對回答品質差異，確認 prompt 真的有效而非安慰劑
- [ ] 1.3 **未做**：確認此 prompt 不會對簡單問候/閒聊誤觸發工具呼叫（過度使用工具
      也是問題——不必要的 web_search 拖慢回應且浪費 token）

## Backlog（長期正解，依賴其他 spec）
- [ ] B.1 P7 Persona 設計完成後，重新評估這個全域 prompt 是否該收斂進 persona
      prompt 裡，而非獨立的全域指示（避免兩處疊加造成 prompt 過長或衝突）
