## ADDED Requirements

### Requirement: Resilient Progress Edits
The `TeamsMTKAdapter.edit_message()` method SHALL handle HTTP 429 Too Many Requests errors by backing off and retrying, and SHALL NEVER raise HTTP exceptions to the caller.

#### Scenario: 429 Backoff and Retry
- **WHEN** `edit_message()` receives a 429 response
- **THEN** it sleeps for >5 seconds, retries the request once, and returns success if the retry succeeds.

#### Scenario: Graceful Degradation on Persistent Failure
- **WHEN** `edit_message()` receives a persistent error (e.g., repeated 429s, 500s, or connection timeouts)
- **THEN** it returns `True`/`False` or `SendResult(success=False)` and does NOT raise an exception, preventing the gateway stream consumer from crashing.

### Requirement: Resilient Message Sending
The `TeamsMTKAdapter.send()` method SHALL handle HTTP 429 errors similarly to `edit_message()`, while preserving its existing 401 token refresh logic.

#### Scenario: 429 Backoff in Send
- **WHEN** `send()` receives a 429 response
- **THEN** it sleeps, retries once, and succeeds if the retry is 200 OK.

#### Scenario: 401 Refresh Integrity
- **WHEN** `send()` receives a 401 response
- **THEN** it force-refreshes the Skype token and retries, as currently implemented, completely unaffected by the new 429 logic.

### Requirement: Native Follow-up Queueing
The system SHALL prevent concurrent agent runs for the same session and correctly sequence rapid follow-up messages.

#### Scenario: Built-in Queueing
- **WHEN** multiple triggers arrive for the same conversation in rapid succession
- **THEN** Hermes core's `display.busy_input_mode: queue` configuration handles the debounce and sequential queueing, requiring NO custom throttle logic inside the `TeamsMTKAdapter`.
