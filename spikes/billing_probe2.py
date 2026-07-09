"""Reproduce via the REAL Hermes SDK path: build_anthropic_client + messages.stream,
model=claude-sonnet-5, h2_tok. If this 429s where raw httpx 200'd, the diff is what
the SDK/streaming adds. Also dumps the ACTUAL request headers the SDK sent (redacted).
"""
import ssl, json
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass

from agent.anthropic_adapter import build_anthropic_client

_auth = json.load(open("C:/Users/mtk12265/.hermes/auth.json"))
h2_tok = _auth["credential_pool"]["anthropic-2"][0]["access_token"]
CC_SYS = "You are Claude Code, Anthropic's official CLI for Claude."

client = build_anthropic_client(api_key=h2_tok, base_url="https://api.anthropic.com")

def dump_sent_headers(resp):
    try:
        hdrs = dict(resp.request.headers)
        for k in list(hdrs):
            if k.lower() in ("authorization", "x-api-key"):
                hdrs[k] = f"<redacted len={len(hdrs[k])}>"
        print("  SENT request headers:")
        for k, v in hdrs.items():
            print(f"    {k}: {v}")
    except Exception as e:
        print("  (could not read sent headers:", e, ")")

for model in ["claude-sonnet-5", "claude-sonnet-4-6"]:
    print(f"\n=== messages.stream model={model} (real SDK path) ===")
    try:
        with client.messages.stream(
            model=model,
            max_tokens=8,
            system=[{"type": "text", "text": CC_SYS}],
            messages=[{"role": "user", "content": "Reply with just: OK"}],
        ) as stream:
            dump_sent_headers(getattr(stream, "response", None))
            text = ""
            for ev in stream.text_stream:
                text += ev
            print(f"  -> 200 OK  text={text!r}")
    except Exception as e:
        # dump the response headers/status if present
        resp = getattr(e, "response", None)
        st = getattr(resp, "status_code", "?")
        print(f"  -> ERROR status={st} {type(e).__name__}: {str(e)[:160]}")
        if resp is not None:
            dump_sent_headers(resp)
