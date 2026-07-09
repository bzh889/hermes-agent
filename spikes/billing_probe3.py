"""LARGE real-size reproduction via real SDK stream path, model=claude-sonnet-5.
Compares cc_tok (scope user:sessions:claude_code) vs h2_tok (Hermes-minted).
Large input (~150k tok) matches the failing session size (138k-303k).

If h2_tok -> 429 and cc_tok -> 200, the differentiator is the TOKEN SCOPE.
If both -> 429, it is pure request-cost vs the exhausted $10 spend precheck.
If both -> 200, the live-session trigger is elsewhere (must capture live request).
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

# ~150k tokens of filler
BIG = ("The quick brown fox jumps over the lazy dog. " * 30 + "\n") * 1150

def run(label, tok):
    client = build_anthropic_client(api_key=tok, base_url="https://api.anthropic.com")
    print(f"\n=== {label}  model=claude-sonnet-5  (~150k tok) ===")
    try:
        with client.messages.stream(
            model="claude-sonnet-5",
            max_tokens=8,
            system=[{"type": "text", "text": CC_SYS}],
            messages=[{"role": "user", "content": BIG + "\nReply with just: OK"}],
        ) as stream:
            txt = ""
            for ev in stream.text_stream:
                txt += ev
            fm = stream.get_final_message()
            u = getattr(fm, "usage", None)
            print(f"  -> 200 OK  text={txt!r}  usage={u}")
    except Exception as e:
        resp = getattr(e, "response", None)
        st = getattr(resp, "status_code", "?")
        print(f"  -> ERROR status={st} {type(e).__name__}: {str(e)[:180]}")

run("cc_tok (claude_code scope)", cc_tok)
run("h2_tok (Hermes minted)", h2_tok)
