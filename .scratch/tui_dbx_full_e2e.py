"""Full E2E via a REAL tui_gateway process:
   1) model.options → databricks rows present (picker visibility)
   2) config.set model='databricks/glm-5-3 --provider aide-responses-io --session' (what the TUI picker sends)
   3) prompt.submit (param name: text) → real agent turn → sentinel
"""
import subprocess, json, time, sys

PY = r"D:\01_Job\Tool\Hermes Agent\.venv\Scripts\python.exe"
p = subprocess.Popen([PY, "-m", "tui_gateway.entry"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8",
                    cwd=r"D:\01_Job\Tool\Hermes Agent", creationflags=subprocess.CREATE_NO_WINDOW)
out = {"lines": []}
def send(o):
    p.stdin.write(json.dumps(o) + "\n"); p.stdin.flush()
def wait_for(pred, timeout):
    end = time.time() + timeout
    while time.time() < end:
        line = p.stdout.readline()
        if not line: return None
        out["lines"].append(line.strip()[:300])
        try: m = json.loads(line)
        except Exception: continue
        if pred(m): return m
    return None

# --- 1) picker payload ---
send({"jsonrpc":"2.0","id":"s1","method":"model.options","params":{"include_unconfigured": True}})
m = wait_for(lambda x: x.get("id") == "s1", 90)
provs = (m or {}).get("result", {}).get("providers", [])
dbx = [q for q in provs if any("databricks" in str(mm) for mm in (q.get("models") or []))]
print(f"[1] model.options: {len(provs)} providers, {len(dbx)} with databricks -> {'PASS' if dbx else 'FAIL'}")

# --- 2) TUI-style model switch: config.set with the picker's value ---
send({"jsonrpc":"2.0","id":"s2","method":"config.set",
      "params":{"key":"model","value":"databricks/glm-5-3 --provider aide-responses-io --session","confirm_expensive_model":True}})
m2 = wait_for(lambda x: x.get("id") == "s2", 120)
r2 = (m2 or {}).get("result") or (m2 or {}).get("error") or {}
print(f"[2] config.set: {json.dumps(r2)[:220]}")
switched = "databricks" in json.dumps(r2)

# --- 3) real turn ---
send({"jsonrpc":"2.0","id":"s3","method":"prompt.submit",
      "params":{"text":"Reply with exactly: DBX-TUI-E2E"}})
sentinel = None
end = time.time() + 240
while time.time() < end:
    line = p.stdout.readline()
    if not line: break
    out["lines"].append(line.strip()[:300])
    if "DBX-TUI-E2E" in line:
        sentinel = line; break
print(f"[3] prompt.submit sentinel: {'PASS' if sentinel else 'FAIL — no sentinel in 240s'}")
if not sentinel:
    print("    last gateway lines:")
    for l in out["lines"][-8:]: print("     ", l)
p.kill()
ok = bool(dbx) and switched and bool(sentinel)
print("OVERALL:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
