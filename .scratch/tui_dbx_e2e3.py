"""E2E v3: session.create(model=databricks/glm-5-3, provider=aide-responses-io) → prompt.submit → sentinel."""
import subprocess, json, time, sys

PY = r"D:\01_Job\Tool\Hermes Agent\.venv\Scripts\python.exe"
p = subprocess.Popen([PY, "-m", "tui_gateway.entry"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8",
                    cwd=r"D:\01_Job\Tool\Hermes Agent", creationflags=subprocess.CREATE_NO_WINDOW)
log = []
def send(o):
    p.stdin.write(json.dumps(o) + "\n"); p.stdin.flush()
def wait_for(pred, t):
    end = time.time() + t
    while time.time() < end:
        line = p.stdout.readline()
        if not line: return None
        log.append(line.strip()[:280])
        try: m = json.loads(line)
        except Exception: continue
        if pred(m): return m
    return None

# [1] picker payload
send({"jsonrpc":"2.0","id":"s1","method":"model.options","params":{"include_unconfigured": True}})
m = wait_for(lambda x: x.get("id") == "s1", 90)
provs = (m or {}).get("result", {}).get("providers", [])
dbx = [q for q in provs if any("databricks" in str(mm) for mm in (q.get("models") or []))]
ok1 = bool(dbx)
print(f"[1] picker: {len(dbx)} provider rows with databricks -> {'PASS' if ok1 else 'FAIL'}")

# [2] create a session carrying the databricks pick (desktop draft-pick path)
send({"jsonrpc":"2.0","id":"s2","method":"session.create",
      "params":{"model":"databricks/glm-5-3","provider":"aide-responses-io","source":"cli"}})
m2 = wait_for(lambda x: x.get("id") == "s2", 180)
r2 = (m2 or {}).get("result") or {}
sid = r2.get("session_id") or r2.get("session") or ""
if isinstance(sid, dict): sid = sid.get("id") or ""
wants_build = isinstance(r2.get("building"), bool)
print(f"[2] session.create -> sid={sid!r} building={r2.get('building')} err={(m2 or {}).get('error')}")

# [3] wait for the agent build (agent.built / session.ready event) if building
if wants_build or not sid:
    built = wait_for(lambda x: x.get("method") == "event" and str(x.get("params", {}).get("type", "")).lower() in ("agent.built","session.ready","agent.ready"), 240)
    print(f"[3] build event: {str((built or {}).get('params', {}).get('type'))[:40]}")

# [4] prompt turn
send({"jsonrpc":"2.0","id":"s3","method":"prompt.submit","params":{"session_id":sid,"text":"Reply with exactly: DBX-TUI-E2E"}})
ack = wait_for(lambda x: x.get("id") == "s3", 60)
print(f"[4] prompt.submit ack: {json.dumps((ack or {}).get('result') or (ack or {}).get('error'))[:120]}")
sentry = wait_for(lambda x: "DBX-TUI-E2E" in json.dumps(x.get("params", {}).get("payload") or x) , 300)
ok4 = sentry is not None
print(f"[5] sentinel -> {'PASS' if ok4 else 'FAIL'}")
if not ok4:
    for l in log[-10:]: print("   ", l[:200])
p.kill()
print("OVERALL:", "PASS" if (ok1 and sid and ok4) else "FAIL")
sys.exit(0 if (ok1 and sid and ok4) else 1)
