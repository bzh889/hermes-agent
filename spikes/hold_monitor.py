"""Live-catch monitor: prove whether max_tokens (the spend-precheck HOLD size) is
what makes Hermes 429 while Claude Code doesn't. Every ~4 min, fire the SAME tiny
prompt at max_tokens 8 / 32000 / 128000 on the same account (cc_tok). Successful
calls output only 'OK' (actual cost ~0; the big max_tokens is only a reserved hold
that is released). When the shared account next goes tight, a divergence
(128000->429 while 8/32000->200) proves the hold size is the differentiator.
"""
import json, time
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from agent.anthropic_adapter import build_anthropic_client

cc = json.load(open("C:/Users/mtk12265/.claude/.credentials.json"))["claudeAiOauth"]["accessToken"]
SYS = [{"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude."}]
LOG = "d:/01_Job/Tool/Hermes Agent/spikes/hold_monitor.log"

def one(mt):
    c = build_anthropic_client(api_key=cc, base_url="https://api.anthropic.com")
    try:
        with c.messages.stream(model="claude-sonnet-5", max_tokens=mt, system=SYS,
                messages=[{"role": "user", "content": "Say OK"}]) as s:
            for _ in s.text_stream:
                pass
        return 200
    except Exception as e:
        return getattr(getattr(e, "response", None), "status_code", "ERR")

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg, flush=True)

log("=== hold_monitor start ===")
rounds = 0
while rounds < 120:  # ~8h at 4min spacing
    rounds += 1
    r = {mt: one(mt) for mt in (8, 32000, 128000)}
    ts = time.strftime("%H:%M:%S")
    line = f"{ts} r{rounds}: mt8={r[8]} mt32k={r[32000]} mt128k={r[128000]}"
    diverge = (r[128000] == 429 and r[8] == 200)
    if diverge:
        line += "  <<< DIVERGENCE: 128k blocked, small passes — HOLD SIZE CONFIRMED"
    log(line)
    time.sleep(240)
log("=== hold_monitor done ===")
