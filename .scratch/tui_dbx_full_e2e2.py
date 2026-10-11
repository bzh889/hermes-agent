"""Full E2E via a REAL tui_gateway process:
   [1] model.options → databricks rows in picker payload
   [2] TUI-style config.set: pick databricks/glm-5-3 --provider aide-responses-io --session
   [3] session must exist first: prompt.submit WITHOUT session_id bootstraps one? No — use session.new.
   [4] prompt.submit (session_id from session.new result; param 'text') → real turn → sentinel
   Verifies via the SAME RPC surface the Ink TUI uses.
"""
import subprocess, json, time, sys

PY = r"D:\01_Job\Tool\Hermes Agent\.venv\Scripts\python.exe"
p = subprocess.Popen([PY, "-m", "tui_gateway.entry"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8",
                    cwd=r"D:\01_Job\Tool\Hermes Agent", creationflags=subprocess.CREATE_NO_WINDOW)
loglines = []
def send(o):
    p.stdin.write(json.dumps(o) + "\n"); p.stdin.flush()
def wait_for(pred, timeout):
    end = time.time() + timeout
    while time.time() < end:
        line = p.stdout.readline()
        if not line: return None
        loglines.append(line.strip()[:280])
        try: m = json.loads(line)
        except Exception: continue
        if pred(m): return m
    return None

ok1 = ok2 = ok3 = False
# [1] picker payload
send({"jsonrpc":"2.0","id":"s1","method":"model.options","params":{"include_unconfigured": True}})
m = wait_for(lambda x: x.get("id") == "s1", 90)
provs = (m or {}).get("result", {}).get("providers", [])
dbx = [q for q in provs if any("databricks" in str(mm) for mm in (q.get("models") or []))]
ok1 = bool(dbx)
print(f"[1] picker: {len(provs)} providers, {len(dbx)} with databricks -> {'PASS' if ok1 else 'FAIL'}")

# [2] what does a REAL session look like — discover via session.list then session.new
send({"jsonrpc":"2.0","id":"s0","method":"session.new","params":{}})
m0 = wait_for(lambda x: x.get("id") == "s0", 120)
sid = ""
if m0 and "result" in m0:
    r0 = m0["result"]
    sid = r0.get("session_id") or r0.get("id") or (r0.get("session") or {}).get("id") if isinstance(r0, dict) else ""
print(f"[2] session.new -> sid={sid!r} keys={list((m0 or {}).get('result', {}).keys())[:6] if m0 else 'None'}")

# [3] TUI-style model switch ON that session: config.set (what the picker's onSelect triggers)
send({"jsonrpc":"2.0","id":"s2","method":"config.set",
      "params":{"key":"model","session_id":sid,
                "value":"databricks/glm-5-3 --provider aide-responses-io --session",
                "confirm_expensive_model":True}})
m2 = wait_for(lambda x: x.get("id") == "s2", 150)
r2 = (m2 or {}).get("result") or {}
ok3 = "databricks" in json.dumps(r2)
print(f"[3] config.set switch -> {json.dumps(r2)[:200]} | {'PASS' if ok3 else 'FAIL'}")

# [4] real turn with sentinel
send({"jsonrpc":"2.0","id":"s3","method":"prompt.submit","params":{"session_id":sid,"text":"Reply with exactly: DBX-TUI-E2E"}})
sentinel = None
end = time.time() + 300
while time.time() < end:
    line = p.stdout.readline()
    if not line: break
    loglines.append(line.strip()[:280])
    if "DBX-TUI-E2E" in line:
        sentinel = True; break
print(f"[4] sentinel turn -> {'PASS' if sentinel else 'FAIL'}")
if not sentinel:
    print("    last gateway lines:")
    for l in loglines[-10:]: print("     ", l[:200])
p.kill()
print("OVERALL:", "PASS" if (ok1 and sid and ok3 and sentinel) else "FAIL")
sys.exit(0 if (ok1 and sid and ok3 and sentinel) else 1)
