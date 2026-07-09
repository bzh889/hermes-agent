"""Enumerate ALL triggering fragments in Hermes's system prompt. Each chunk is
tested IN ISOLATION (CC identity + chunk). A chunk that 429s in isolation
contains trigger content. Benign chunks -> 200. Retries on 502.
"""
import json, time, sys
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from agent.anthropic_adapter import build_anthropic_client

cc = json.load(open("C:/Users/mtk12265/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]
d = json.load(open("C:/Users/mtk12265/.hermes/sessions/request_dump_20260706_192026_8cf0b6_20260708_180035_087578.json", encoding="utf-8"))
body = d["request"]["body"]
if isinstance(body, str):
    body = json.loads(body)
sysm = body["system"]; CC = sysm[0]; t1 = sysm[1].get("text")
base = {k: body[k] for k in ("model", "messages", "tools", "tool_choice") if k in body}

CHUNK = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

def send(text):
    for _ in range(4):
        c = build_anthropic_client(api_key=cc, base_url="https://api.anthropic.com")
        kw = dict(base); kw["system"] = [CC, {"type": "text", "text": text}]; kw["max_tokens"] = 8
        try:
            with c.messages.stream(**kw) as s:
                for _ in s.text_stream:
                    break
            return 200
        except Exception as e:
            st = getattr(getattr(e, "response", None), "status_code", "ERR")
            if st in (502, "ERR"):
                time.sleep(2); continue
            return st
    return "502x"

print(f"block1 len={len(t1)} chunk={CHUNK}")
i = 0; idx = 0
while i < len(t1):
    seg = t1[i:i+CHUNK]
    r1 = send(seg)
    r2 = send(seg) if r1 == 429 else r1  # confirm 429s
    flag = "  <<< TRIGGER" if (r1 == 429 and r2 == 429) else ""
    head = seg[:70].replace("\n", " ")
    print(f"  chunk{idx:02d} [{i}:{i+len(seg)}] {r1}/{r2}{flag}  | {head!r}")
    i += CHUNK; idx += 1
