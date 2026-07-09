"""Last untested dimension: CONCURRENCY. Fire several large requests at once on
h2_tok. If some 429 while isolated ones 200, the trigger is concurrent in-flight
cost against the exhausted $10 spend precheck (many TUIs + Claude Code sharing
the account). Otherwise the live 429 was transient account-state.
"""
import json, concurrent.futures as cf
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from agent.anthropic_adapter import build_anthropic_client

_auth = json.load(open("C:/Users/mtk12265/.hermes/auth.json"))
h2_tok = _auth["credential_pool"]["anthropic-2"][0]["access_token"]
CC_SYS = "You are Claude Code, Anthropic's official CLI for Claude."
BIG = ("The quick brown fox jumps over the lazy dog. " * 30 + "\n") * 1150  # ~big

def one(i):
    client = build_anthropic_client(api_key=h2_tok, base_url="https://api.anthropic.com")
    try:
        with client.messages.stream(
            model="claude-sonnet-5", max_tokens=32000,
            system=[{"type": "text", "text": CC_SYS}],
            messages=[{"role": "user", "content": BIG + f"\n[req {i}] Reply with just: OK"}],
        ) as stream:
            for _ in stream.text_stream:
                pass
        return f"req{i}: 200"
    except Exception as e:
        resp = getattr(e, "response", None)
        return f"req{i}: {getattr(resp,'status_code','?')} {str(e)[:60]}"

with cf.ThreadPoolExecutor(max_workers=6) as ex:
    for r in ex.map(one, range(6)):
        print(" ", r)
