## Why

The TeamsMTK adapter (`gateway/platforms/teams_mtk.py`) already polls
whitelisted conversations, gates on `@hermes`, sends replies, and streams
progress via `edit_message()`. But it is missing two reliability guards that
a live multi-user Teams deployment provably needs — both discovered by a
real colleague @mentioning the bot in a shared group, not by simulation:

1. **No 429 (rate-limit) handling.** Teams' chat-service caps writes at
   ~3 calls / 5s (`429 API calls quota exceeded! 3Per05Secs`). During
   progress-streaming (`send` placeholder → rapid `edit_message` deltas →
   finalize `edit_message`), the burst trips 429. `send()`/`edit_message()`
   currently call `resp.raise_for_status()`, so a 429 throws — the reply
   is left half-streamed at "思考中…" and the exception propagates. Every
   subsequent poll re-dispatches the same trigger, producing a retry storm.

2. **Concurrency and Debouncing issues.** Two @mentions seconds apart spawn full agent runs concurrently, feeding the 429 above. We previously wrote a custom debounce and sequential queueing logic for this, but Hermes already has `display.busy_input_mode: queue` built-in, which natively handles queuing follow-ups and preventing concurrent runs for the same session.

A prior iteration of this logic was mistakenly built as a standalone daemon
inside an unrelated project (a personal knowledge base). That was the wrong
home: reply-generation needs the agent brain + full toolset, which only the
Hermes gateway has. This change brings the 429 handling directly to the adapter and delegates the queueing to Hermes' native config, and the daemon is deleted.

This change is deliberately scoped to **reliability only** (429 + queueing + progress-edit backpressure). Richer per-conversation reply presentation
(natural-language template editing) is explicitly out of scope and tracked
as a separate follow-up.

## What Changes

- `edit_message()` in `teams_mtk.py`: on HTTP 429, back off once (sleep just
  past the 5s Teams window) and retry; on any persistent failure return
  `SendResult(success=False)` instead of raising, so a dropped mid-stream
  edit or a failed finalize never aborts the whole reply or crashes the
  progress sender.
- `send()` in `teams_mtk.py`: same 429 backoff-then-retry on the message POST;
  transport/HTTP errors already return `SendResult(success=False)` and stay
  that way (no `raise_for_status` regression).
- Leverage Hermes core's `display.busy_input_mode: queue` setting in `config.yaml` to handle debounce and sequential queuing of messages per session, natively preventing concurrent agent runs.

## Capabilities

### New Capabilities
- `teams-mtk-answer-reliability`: rate-limit-aware send/edit for the TeamsMTK adapter, and leveraging native sequential queueing.

### Modified Capabilities
（無現有 spec 受影響 — 這是 TeamsMTK adapter 現有送訊息/編輯路徑上新增的可靠性保證，不改既有 spec 的 requirements。）

## Impact

- **Affected code**:
  - `gateway/platforms/teams_mtk.py` (`send()`, `edit_message()`)
- **Config**: `~/.hermes/config.yaml` must have `display.busy_input_mode: queue` set. No new `.env` var.
- **Removed (separate project, not this repo)**: the standalone Teams
  monitor daemon and its 10 self-authored `scripts/teams_*.py` modules +
  tests are deleted from the PKB project (the pre-existing `teams_auth.py`,
  which predates the daemon, is retained — Teams token handling stays in the
  teams skill). Tracked in this change's tasks for completeness but touches
  a different repo.
- **Compatibility**: 429 handling is a pure robustness upgrade (previously crashed, now degrades gracefully). No change to mention gating, echo guard, or SessionSource. Relying on `busy_input_mode: queue` correctly standardizes behavior.
- **Restart requirement**: gateway code change requires a gateway restart to
  take effect (existing convention).
- **Out of scope (follow-up)**: per-conversation natural-language reply
  templates; "monitor ALL conversations" passive ingest (flagged as
  ill-defined, to be redesigned separately).
