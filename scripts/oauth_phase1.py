#!/usr/bin/env python3
"""Phase 1 of Hermes Anthropic OAuth: generate PKCE + auth URL, save verifier to temp file."""
import sys, os, json, secrets, hashlib, base64
sys.path.insert(0, "D:/01_Job/Tool/Hermes Agent")
os.environ.setdefault("HERMES_HOME", "C:/Users/mtk12265/.hermes")

from agent.anthropic_adapter import _generate_pkce, _OAUTH_CLIENT_ID, _OAUTH_REDIRECT_URI, _OAUTH_SCOPES
from urllib.parse import urlencode

verifier, challenge = _generate_pkce()
oauth_state = secrets.token_urlsafe(32)

params = {
    "code": "true",
    "client_id": _OAUTH_CLIENT_ID,
    "response_type": "code",
    "redirect_uri": _OAUTH_REDIRECT_URI,
    "scope": _OAUTH_SCOPES,
    "code_challenge": challenge,
    "code_challenge_method": "S256",
    "state": oauth_state,
}

auth_url = f"https://claude.ai/oauth/authorize?{urlencode(params)}"

# Save verifier + state to temp file for Phase 2
state_file = os.path.join(os.environ.get("TEMP", "/tmp"), "hermes_oauth_state.json")
with open(state_file, "w") as f:
    json.dump({"verifier": verifier, "state": oauth_state}, f)

print(f"AUTH_URL={auth_url}")
print(f"STATE_FILE={state_file}")
