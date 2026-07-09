"""THE max_tokens hypothesis. Small input, vary max_tokens only.
Anthropic's spend precheck estimates worst-case cost = input + max_tokens(*output price).
If a large max_tokens trips 429 while small does not, THAT is the differentiator my
earlier max_tokens=8 tests missed. Tested on both tokens.
"""
import json
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from agent.anthropic_adapter import build_anthropic_client

_auth = json.load(open("C:/Users/mtk12265/.hermes/auth.json"))
h2_tok = _auth["credential_pool"]["anthropic-2"][0]["access_token"]
cc_tok = json.load(open("C:/Users/mtk12265/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]
CC_SYS = "You are Claude Code, Anthropic's official CLI for Claude."

def run(label, tok, max_tokens):
    client = build_anthropic_client(api_key=tok, base_url="https://api.anthropic.com")
    try:
        with client.messages.stream(
            model="claude-sonnet-5",
            max_tokens=max_tokens,
            system=[{"type": "text", "text": CC_SYS}],
            messages=[{"role": "user", "content": "Reply with just: OK"}],
        ) as stream:
            for _ in stream.text_stream:
                pass
            print(f"  {label:26s} max_tokens={max_tokens:<6} -> 200 OK")
    except Exception as e:
        resp = getattr(e, "response", None)
        st = getattr(resp, "status_code", "?")
        print(f"  {label:26s} max_tokens={max_tokens:<6} -> {st} {str(e)[:70]}")

for mt in [8, 8192, 32000, 64000]:
    run("h2_tok (Hermes)", h2_tok, mt)
print()
for mt in [64000, 32000]:
    run("cc_tok (claude_code)", cc_tok, mt)
