"""FINAL reproduction at the REAL parameters captured from Hermes:
  model=claude-sonnet-5, max_tokens=128000, 27 real tools, large input.
Compare cc_tok (claude_code scope) vs h2_tok (Hermes minted). The spend precheck
estimates worst-case cost = input + max_tokens(output-priced); the real 128000
max_tokens is what my earlier <=64000 sweep never reached.
"""
import json
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from agent.anthropic_adapter import build_anthropic_client

CAP = "C:/Users/mtk12265/AppData/Local/Temp/claude/d--01-Job-Tool-Hermes-Agent/8cbcd724-2648-42ea-bf9f-5e17228ebaef/scratchpad/cap_kwargs.json"
cap = json.load(open(CAP, encoding="utf-8"))
tools = cap.get("tools") or []
system = cap.get("system")

_auth = json.load(open("C:/Users/mtk12265/.hermes/auth.json"))
h2_tok = _auth["credential_pool"]["anthropic-2"][0]["access_token"]
cc_tok = json.load(open("C:/Users/mtk12265/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]

BIG = ("The quick brown fox jumps over the lazy dog. " * 30 + "\n") * 1900  # ~250k tok

def run(label, tok, max_tokens, big):
    client = build_anthropic_client(api_key=tok, base_url="https://api.anthropic.com")
    content = (BIG + "\nReply with just: OK") if big else "Reply with just: OK"
    try:
        with client.messages.stream(
            model="claude-sonnet-5", max_tokens=max_tokens,
            system=system, tools=tools,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            for _ in stream.text_stream:
                pass
            fm = stream.get_final_message()
            print(f"  {label:24s} mt={max_tokens:<7} big={big!s:5} -> 200  in={fm.usage.input_tokens}")
    except Exception as e:
        resp = getattr(e, "response", None)
        st = getattr(resp, "status_code", "?")
        print(f"  {label:24s} mt={max_tokens:<7} big={big!s:5} -> {st}  {str(e)[:80]}")

print(f"tools={len(tools)}  system_blocks={len(system) if isinstance(system,list) else '?'}")
# small input, real max_tokens: isolate max_tokens effect
run("h2_tok", h2_tok, 128000, False)
run("cc_tok", cc_tok, 128000, False)
# large input + real max_tokens: full real cost profile
run("h2_tok", h2_tok, 128000, True)
run("cc_tok", cc_tok, 128000, True)
