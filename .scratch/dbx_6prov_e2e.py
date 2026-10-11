"""Layer-2 E2E: for each of the 6 aide-responses* providers, run a REAL
`_make_agent` (TUI agent-construction path) + one `run_conversation` turn
on databricks/glm-5-3. Records HTTP status semantics honestly:
  OK-200   = sentinel returned
  other    = exact error/response recorded (may be account quota state)
Sequential to avoid piling onto the busy gateway box.
"""
import sys, os, time, json
sys.path.insert(0, r"D:/01_Job/Tool/Hermes Agent")
os.environ["HERMES_TUI"] = "1"

PROVIDERS = ["aide-responses", "aide-responses-crlogai001", "aide-responses-ds901472",
             "aide-responses-molycrgpt001", "aide-responses-io", "aide-responses-io-ds901472"]
results = {}
try:
    from tui_gateway.server import _make_agent
    for i, prov in enumerate(PROVIDERS):
        t0 = time.time()
        sid = f"dbxe2e-{i}"
        try:
            ag = _make_agent(sid, sid, model_override={"model": "databricks/glm-5-3", "provider": prov})
            res = ag.run_conversation("Reply with exactly: DBX-E2E", task_id=sid)
            txt = str(res.get("final_response") or "")
            rec = {"build_s": round(time.time()-t0, 1), "model": getattr(ag, "model", None),
                   "sentinel": "DBX-E2E" in txt, "final": txt[:120]}
        except Exception as e:
            rec = {"error": f"{type(e).__name__}: {str(e)[:200]}", "sentinel": False}
        results[prov] = rec
        print(f"{prov:30s} -> {json.dumps(rec, ensure_ascii=False)[:220]}", flush=True)
finally:
    with open(r"D:/01_Job/Tool/Hermes Agent/.scratch/dbx_6prov_e2e_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
ok = sum(1 for v in results.values() if v.get("sentinel"))
print(f"SUMMARY: {ok}/{len(PROVIDERS)} providers completed a real databricks turn with sentinel")
