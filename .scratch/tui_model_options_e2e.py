"""E2E: spawn a REAL tui_gateway process, send model.options over stdio JSON-RPC, verify databricks rows."""
import subprocess, json, sys, pathlib, time

PY = r"D:\01_Job\Tool\Hermes Agent\.venv\Scripts\python.exe"
proc = subprocess.Popen(
    [PY, "-m", "tui_gateway.entry"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding="utf-8", cwd=r"D:\01_Job\Tool\Hermes Agent",
    creationflags=subprocess.CREATE_NO_WINDOW,
)
def send(obj):
    proc.stdin.write(json.dumps(obj) + "\n"); proc.stdin.flush()
def recv(method_filter=None, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line: return None
        try: msg = json.loads(line)
        except Exception: continue
        if method_filter is None or msg.get("method") == method_filter or ("result" in msg and msg.get("id") == method_filter):
            return msg
    return None

# 1) model.options — exactly what the TUI picker sends
send({"jsonrpc": "2.0", "id": "e2e-1", "method": "model.options",
      "params": {"include_unconfigured": True}})
t0 = time.time()
# swallow ready/notification lines; find our result
msg = None
deadline = time.time() + 60
while time.time() < deadline:
    line = proc.stdout.readline()
    if not line: break
    try: m = json.loads(line)
    except Exception: continue
    if m.get("id") == "e2e-1":
        msg = m; break
elapsed = time.time() - t0
if not msg:
    print("FAIL: no model.options result in 60s"); proc.kill(); sys.exit(1)
res = msg.get("result", {})
provs = res.get("providers", [])
dbx = [(p.get("name"), p.get("slug"), [m if isinstance(m, str) else m.get("id") for m in (p.get("models") or []) if "databricks" in str(m)]) for p in provs]
dbx = [x for x in dbx if x[2]]
print(f"model.options via REAL tui_gateway: {len(provs)} providers, {len(dbx)} with databricks ({elapsed:.1f}s)")
for name, slug, models in dbx:
    print(f"  {slug}: {name} -> {models}")
ok = bool(dbx)
print("E2E RESULT:", "PASS" if ok else "FAIL — databricks rows missing from the live RPC payload")

# 2) session.new + one REAL turn on databricks/glm-5-3 -- full agent turn proves selection AND execution
send({"jsonrpc": "2.0", "id": "e2e-2", "method": "session.new", "params": {}})
send({"jsonrpc": "2.0", "id": "e2e-3", "method": "prompt.submit",
      "params": {"session_id": "e2e-sid", "prompt": "Reply with exactly: DBX-TUI-E2E",
                 "model": "databricks/glm-5-3", "provider": "aide-responses"}})
# look for a message.complete carrying the sentinel
found = None; deadline = time.time() + 120
while time.time() < deadline:
    line = proc.stdout.readline()
    if not line: break
    try: m = json.loads(line)
    except Exception: continue
    if m.get("method") in ("message.complete", "message.delta") and isinstance(m.get("params"), dict):
        txt = str(m["params"].get("content") or m["params"].get("text") or "")
        if "DBX-TUI-E2E" in txt: found = m["method"]; break
    if m.get("id") == "e2e-3" and "result" in m:
        # some gateways reply synchronously with the final text
        if "DBX-TUI-E2E" in json.dumps(m["result"]): found = "prompt.result"; break
print("TURN RESULT:", "PASS — sentinel seen via", found if found else "TIMEOUT — no sentinel in 120s")
proc.kill()
sys.exit(0 if (ok and found) else 1)
