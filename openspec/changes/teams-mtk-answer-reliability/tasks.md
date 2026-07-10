# Tasks: teams-mtk-answer-reliability

> **Execution discipline (SDD then TDD):**
> 1. RED: Write failing test in `tests/gateway/platforms/test_teams_mtk_reliability.py`.
> 2. GREEN: Implement minimal fix in `gateway/platforms/teams_mtk.py`.
> 3. REFACTOR/REGRESSION: Ensure existing tests pass.

## 1. Harden `edit_message` against 429s (TDD)
- [ ] 1.1 RED: Write `test_edit_message_429_backs_off_and_retries` (mocks 429 -> 200, asserts sleep and 2 calls).
- [ ] 1.2 RED: Write `test_edit_message_persistent_failure_never_raises` (mocks 429 -> 429 or ConnectionError, asserts False return, no raise).
- [ ] 1.3 GREEN: Implement 429 backoff and exception suppression in `TeamsMTKAdapter.edit_message`.
- [ ] 1.4 REGRESSION: Run existing gateway tests to ensure no breakage.

## 2. Harden `send` against 429s (TDD)
- [ ] 2.1 RED: Write `test_send_429_backs_off_and_retries`.
- [ ] 2.2 RED: Write `test_send_401_refresh_integrity` (ensure 401 logic isn't broken by 429 logic).
- [ ] 2.3 GREEN: Implement 429 backoff in `TeamsMTKAdapter.send`.
- [ ] 2.4 REGRESSION: Run existing gateway tests.

## 3. Verify Hermes Native Concurrency
- [ ] 3.1 Verify `display.busy_input_mode: queue` is set in `~/.hermes/config.yaml`.
- [ ] 3.2 Restart gateway. Verify via live Teams testing that follow-up messages are correctly queued and debounced by Hermes core.

## 4. Decommission PKB Daemon
- [ ] 4.1 Delete the 10 custom `teams_*.py` files in the PKB repository (excluding the legacy `teams_auth.py`).
- [ ] 4.2 Delete associated test files in PKB.

## 5. Echo guard, @mention preserve, parallel poll, token cache, edit throttle
- [x] 5.1 Echo guard: `_sent_message_ids: set` tracks ALL sent message IDs so poll never re-processes own echoes.
- [x] 5.2 @mention preserve: `<at id="...">hermes</at>` survives HTML strip via `re.sub(r"<at\s[^>]*>([^<]*)</at>", r"\1", raw)` before generic tag removal. No more empty inbound.
- [x] 5.3 Parallel poll: `asyncio.gather` replaces sequential `for` loop over `_conv_ids`. N convs fetch in ~1 RTT instead of N×RTT.
- [x] 5.4 Token cache atomic write: `_save` writes to `.json.tmp` then `os.rename` to prevent corruption from concurrent writes or power loss. `fsync` before rename.
- [x] 5.5 Token cache auto-purge: `_load` deletes corrupted cache file on unrecoverable `json.JSONDecodeError` so next poll triggers re-auth instead of permanently blocking.
- [x] 5.6 Edit throttle: `edit_message` calls `_maybe_throttle(chat_id)` before the HTTP PUT, sharing the same per-conv throttle as `send`. Prevents rapid edits from hitting 429.
- [x] 5.7 Self-reflection prompt (config-level quick-fix): `agent.system_prompt` in `config.yaml` instructs agent to check tool usage before answering. Objective check (did I use tools?) > subjective scoring (is my answer good?).
