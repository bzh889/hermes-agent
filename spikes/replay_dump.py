"""Replay a real Hermes request_dump at different max_tokens to prove whether
the spend-precheck 429 is driven by the reserved hold (max_tokens). Reads the
dump's request.body (full 882-msg payload), replays it with a valid token at
max_tokens 128000 / 32000 / 8. Run RIGHT AFTER a live repro (account tight) to
catch: 128000->429 while 32000/8->200.

Usage: replay_dump.py [dump.json]   (defaults to newest failing dump)
"""
import json, sys, glob, os
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from agent.anthropic_adapter import build_anthropic_client

cc = json.load(open("C:/Users/mtk12265/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]

if len(sys.argv) > 1:
    dump = sys.argv[1]
else:
    files = glob.glob("C:/Users/mtk12265/.hermes/sessions/request_dump_*.json")
    dump = max(files, key=os.path.getmtime)
print("dump:", os.path.basename(dump))

d = json.load(open(dump, encoding="utf-8"))
body = d["request"]["body"]
if isinstance(body, str):
    body = json.loads(body)

model = body.get("model")
n_msgs = len(body.get("messages") or [])
print(f"model={model} orig_max_tokens={body.get('max_tokens')} n_msgs={n_msgs} n_tools={len(body.get('tools') or [])}")

# Keep the payload as-is except max_tokens; drop fields the SDK may reject when
# replayed raw, add them back only if needed.
base = {k: body[k] for k in ("model", "system", "messages", "tools", "tool_choice") if k in body}

def replay(mt):
    c = build_anthropic_client(api_key=cc, base_url="https://api.anthropic.com")
    kw = dict(base); kw["max_tokens"] = mt
    try:
        with c.messages.stream(**kw) as s:
            for _ in s.text_stream:
                break
        return "200"
    except Exception as e:
        st = getattr(getattr(e, "response", None), "status_code", "ERR")
        return f"{st} {str(e)[:70]}"

for mt in (8, 32000, 128000):
    print(f"  replay max_tokens={mt:<7} -> {replay(mt)}")
