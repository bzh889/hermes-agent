"""DECISIVE token-vs-header matrix, real Hermes tokens, Hermes venv.

spend ($10) bucket is MAXED (critical). So routing is visible in the status:
  200            -> billed to cinder_cove ($1000 pool)
  429 spend-limit-> routed to the (exhausted) $10 spend bucket   <-- the Hermes bug

Matrix isolates whether the differentiator is the TOKEN (scope) or the HEADERS:
  cc_tok  = ds_lisa Claude Code token   (scope user:sessions:claude_code)
  h2_tok  = ds_lisa Hermes pool token   (Hermes-minted, org:create_api_key)
  both tokens are the SAME account -> same usage buckets.
Tokens never printed.
"""
import ssl, json, httpx
try:
    import truststore; truststore.inject_into_ssl(); _SSL = "truststore"
except Exception as e:
    _SSL = f"no-truststore:{e}"

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
MSG_URL = "https://api.anthropic.com/v1/messages"
CC_SYS = "You are Claude Code, Anthropic's official CLI for Claude."
BETAS = "claude-code-20250219,oauth-2025-04-20"

cc_tok = json.load(open("C:/Users/mtk12265/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]
_auth = json.load(open("C:/Users/mtk12265/.hermes/auth.json"))
h2_tok = _auth["credential_pool"]["anthropic-2"][0]["access_token"]

def usage(tok):
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/json",
         "anthropic-beta": "oauth-2025-04-20", "User-Agent": "claude-code/2.1.0"}
    try:
        p = httpx.get(USAGE_URL, headers=h, timeout=25).json()
        cc = (p.get("cinder_cove") or {}).get("used_dollars")
        sp = ((p.get("spend") or {}).get("used") or {}).get("amount_minor")
        return cc, sp
    except Exception as e:
        return None, None

BIG = ("The quick brown fox jumps over the lazy dog. " * 24 + "\n") * 400  # ~40k tok

def send(tok, extra, big=False):
    h = {"authorization": f"Bearer {tok}", "anthropic-version": "2023-06-01",
         "anthropic-beta": BETAS, "content-type": "application/json"}
    h.update(extra)
    content = (BIG + "\nReply with just: OK") if big else "Reply with just: OK"
    body = {"model": "claude-sonnet-4-6", "max_tokens": 8,
            "system": [{"type": "text", "text": CC_SYS}],
            "messages": [{"role": "user", "content": content}]}
    try:
        r = httpx.post(MSG_URL, headers=h, json=body, timeout=60)
        m = ""
        if r.status_code != 200:
            try: m = r.json().get("error", {}).get("message", "")[:90]
            except Exception: m = r.text[:90]
        return r.status_code, m
    except Exception as e:
        return "EXC", str(e)[:90]

HERMES_HDRS = {"user-agent": "claude-cli/2.1.195 (external, cli)", "x-app": "cli",
               "x-anthropic-billing-header": "cc_version=2.1.195; cc_entrypoint=claude-code; cch=00000;"}
CC_HDRS = {"user-agent": "claude-cli/2.1.195 (external, cli)", "x-app": "cli",
           "x-anthropic-billing-header": "cc_version=2.1.195.d49; cc_entrypoint=claude-vscode; cch=00000;"}
NO_HDRS = {}

def send_model(tok, extra, model):
    h = {"authorization": f"Bearer {tok}", "anthropic-version": "2023-06-01",
         "anthropic-beta": BETAS, "content-type": "application/json"}
    h.update(extra)
    body = {"model": model, "max_tokens": 8,
            "system": [{"type": "text", "text": CC_SYS}],
            "messages": [{"role": "user", "content": "Reply with just: OK"}]}
    try:
        r = httpx.post(MSG_URL, headers=h, json=body, timeout=60)
        m = ""
        if r.status_code != 200:
            try: m = r.json().get("error", {}).get("message", "")[:100]
            except Exception: m = r.text[:100]
        return r.status_code, m
    except Exception as e:
        return "EXC", str(e)[:100]

MODELS = ["claude-sonnet-5", "claude-sonnet-4-6", "claude-sonnet-4-5",
          "claude-opus-4-8", "claude-3-5-sonnet-20241022"]

print(f"SSL={_SSL}  (small requests; token=h2_tok Hermes real; Hermes headers; vary MODEL)")
print(f"{'model':30s} {'status':8s} note")
for model in MODELS:
    st, msg = send_model(h2_tok, HERMES_HDRS, model)
    print(f"{model:30s} {str(st):8s} {msg}")
