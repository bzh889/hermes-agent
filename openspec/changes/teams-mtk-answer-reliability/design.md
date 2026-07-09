# Design: TeamsMTK Answer Reliability & Concurrency

## Background
The initial attempt to add Teams auto-reply capabilities involved building a standalone daemon within the Personal Knowledge Base (PKB) repository. This was architecturally incorrect. Hermes Agent already possesses a fully-featured `TeamsMTKAdapter` (`gateway/platforms/teams_mtk.py`) that handles polling, mention gating, and echo prevention natively. Furthermore, Hermes core natively supports advanced concurrency controls (`busy_input_mode`), rendering custom throttling implementations redundant.

## Architecture
This change shifts all Teams auto-reply responsibilities back to the native `TeamsMTKAdapter` and hardens it against Teams API limitations.

### 1. 429 Rate Limit Handling (Adapter Level)
Teams enforces a `3Per05Secs` rate limit. Progress streaming (rapid `edit_message` calls as the LLM streams tokens) frequently trips this.
- **Current Flaw**: `edit_message` and `send` call `resp.raise_for_status()`. A 429 raises an HTTPError, crashing the stream consumer or the delivery pipeline, leaving messages half-finished and triggering retry storms.
- **Design**: Catch HTTP 429. Introduce a `_RATE_LIMIT_BACKOFF_S = 5.5` sleep, then retry exactly once. If the retry fails (or any other HTTP/Transport error occurs), the methods will catch the exception and return a boolean or `SendResult(success=False)` instead of raising. This allows graceful degradation (a dropped mid-stream edit is merely cosmetic) without crashing the agent loop.

### 2. Concurrency & Throttling (Core Level)
We will NOT implement a custom "throttle" or "waiting window" inside `teams_mtk.py`.
- Hermes core (`gateway/run.py` and `base.py`) already implements `busy_input_mode: queue`.
- When active, incoming messages during an executing agent run are queued (`_pending_messages`).
- **Debounce & Merge**: The `_queue_text_debounce` mechanism automatically aggregates rapid follow-up messages from the same sender (joining them with `\n`) before the agent processes them.
- **Design**: Rely entirely on Hermes's native `queue` mode. No new code is required in the adapter for throttling. We only need to ensure the user's `config.yaml` is set to `busy_input_mode: queue`.

### 3. Decommissioning the PKB Daemon
Once the Hermes adapter is hardened and verified, the 10 custom `teams_*.py` files incorrectly placed in the PKB repository (which reinvented the wheel) will be permanently deleted to prevent dual-polling and technical debt.
