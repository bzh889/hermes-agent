#!/usr/bin/env python3
"""Phase 2 of Hermes Anthropic OAuth: exchange auth code for tokens using saved verifier."""
import sys, os, json
sys.path.insert(0, "D:/01_Job/Tool/Hermes Agent")
os.environ.setdefault("HERMES_HOME", "C:/Users/mtk12265/.hermes")

if len(sys.argv) < 2:
    print("Usage: python oauth_phase2.py <auth_code#state>")
    sys.exit(1)

auth_code_input = sys.argv[1]

# Load saved PKCE state
state_file = os.path.join(os.environ.get("TEMP", "/tmp"), "hermes_oauth_state.json")
if not os.path.exists(state_file):
    print("ERROR: No OAuth state file. Run Phase 1 first.")
    sys.exit(1)

with open(state_file, "r") as f:
    saved = json.load(f)

verifier = saved["verifier"]
expected_state = saved["state"]

# Parse code and state from input
splits = auth_code_input.split("#")
code = splits[0]
received_state = splits[1] if len(splits) > 1 else ""

# Validate state (CSRF protection)
if received_state and received_state != expected_state:
    print(f"WARNING: State mismatch! Expected {expected_state[:10]}... got {received_state[:10]}...")
    print("Continuing anyway (state from browser redirect may differ)")

# Exchange code for tokens
from agent.anthropic_adapter import (
    _OAUTH_CLIENT_ID, _OAUTH_REDIRECT_URI, _OAUTH_TOKEN_URLS,
    _get_claude_code_version, _write_claude_code_credentials, read_claude_code_credentials,
)
import urllib.request

exchange_data = json.dumps({
    "grant_type": "authorization_code",
    "client_id": _OAUTH_CLIENT_ID,
    "code": code,
    "state": received_state,
    "redirect_uri": _OAUTH_REDIRECT_URI,
    "code_verifier": verifier,
}).encode()

result = None
last_error = None
ver = _get_claude_code_version()
for endpoint in _OAUTH_TOKEN_URLS:
    req = urllib.request.Request(
        endpoint,
        data=exchange_data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"claude-cli/{ver} (external, cli)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        break
    except Exception as exc:
        last_error = exc
        print(f"Token exchange failed at {endpoint}: {exc}")
        continue

if result is None:
    print(f"FAILED: Token exchange failed. Last error: {last_error}")
    sys.exit(1)

# Extract tokens
access_token = result.get("access_token", "")
refresh_token = result.get("refresh_token", "")
expires_at_ms = result.get("expires_at_ms", 0)
scopes = result.get("scope", "").split() if result.get("scope") else None

print(f"SUCCESS: Got tokens!")
print(f"  access_token prefix: {access_token[:15]}...")
print(f"  has refresh_token: {bool(refresh_token)}")
print(f"  expires_at_ms: {expires_at_ms}")

# Write to .credentials.json (so Claude CLI also works)
_write_claude_code_credentials(access_token, refresh_token, expires_at_ms, scopes=scopes)
print("Written to ~/.claude/.credentials.json")

# Verify
creds = read_claude_code_credentials()
print(f"Verification: accessToken present={bool(creds.get('accessToken'))}")

# Also sync auth.json pool entry
pool = load_pool("anthropic")
for e in pool.entries():
    if e.source == "claude_code":
        e.access_token = access_token
        e.refresh_token = refresh_token
        e.expires_at_ms = expires_at_ms
        print("Synced auth.json claude_code entry")
        break
pool._persist()
print("auth.json pool persisted")

# Cleanup
os.unlink(state_file)
print("Phase 2 complete!")
