"""The real 882-msg dump payload 429s deterministically (even at max_tokens=8),
while synthetic large payloads 200. Bisect WHICH part of the real payload triggers
the spend-precheck 429. All variants at max_tokens=8.
"""
import json, copy
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from agent.anthropic_adapter import build_anthropic_client

cc = json.load(open("C:/Users/mtk12265/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]
dump = "C:/Users/mtk12265/.hermes/sessions/request_dump_20260706_192026_8cf0b6_20260708_180035_087578.json"
d = json.load(open(dump, encoding="utf-8"))
body = d["request"]["body"]
if isinstance(body, str):
    body = json.loads(body)
base = {k: body[k] for k in ("model", "system", "messages", "tools", "tool_choice") if k in body}

def strip_cache(obj):
    if isinstance(obj, dict):
        return {k: strip_cache(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [strip_cache(x) for x in obj]
    return obj

def send(kw):
    c = build_anthropic_client(api_key=cc, base_url="https://api.anthropic.com")
    k = dict(kw); k["max_tokens"] = 8
    try:
        with c.messages.stream(**k) as s:
            for _ in s.text_stream:
                break
        return "200"
    except Exception as e:
        st = getattr(getattr(e, "response", None), "status_code", "ERR")
        return f"{st}"

def V(name, kw):
    print(f"  {name:34s} n_msgs={len(kw.get('messages') or []):3d} n_tools={len(kw.get('tools') or []):2d} -> {send(kw)}")

V("full (baseline)", base)
# drop tools
b2 = dict(base); b2.pop("tools", None); b2.pop("tool_choice", None)
V("no tools", b2)
# tiny system
b3 = dict(base); b3["system"] = [{"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude."}]
V("tiny system", b3)
# first 4 messages only
b4 = dict(base); b4["messages"] = base["messages"][:4]
V("first 4 msgs", b4)
# last 4 messages only
b5 = dict(base); b5["messages"] = base["messages"][-4:]
V("last 4 msgs", b5)
# strip all cache_control
b6 = strip_cache(dict(base))
V("strip cache_control", b6)
# minimal: tiny system + 1 msg + no tools
b7 = {"model": base["model"], "system": b3["system"],
      "messages": [{"role": "user", "content": "Say OK"}]}
V("minimal (tiny sys,1 msg,no tools)", b7)
