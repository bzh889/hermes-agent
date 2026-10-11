"""Phase B+C: reasoning effort discovery + E2E per user-specified scope.

Reasoning probe: for each chat model, try efforts high→… on /chat/completions.
For OpenAI-series (azure/gpt-*): use max_completion_tokens; others max_tokens.
Databricks responses: /v1/responses with reasoning.effort.

E2E: 一個 sentinel turn「Reply exactly: OK」。403 monthly-budget / 401 / quota-500
視為「可用性受限(帳號額度)」而不是模型失敗。
"""
import httpx, json, subprocess, time
from pathlib import Path

ENV = {}
for line in Path.home().joinpath(".hermes", ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        ENV[k.strip()] = v.strip().strip('"').strip("'")
OA = subprocess.run(["bash", "-lc", "cd ~/.cchelper && ./coding-cli-helper.exe auth token --tool claude --domain oa"],
                    capture_output=True, text=True, timeout=60).stdout.strip()

ACCT = {
    "aide":             ("https://mlop-azure-gateway.mediatek.inc",    OA,                          "MTK12265"),
    "aide-io":          ("https://mlop-azure-gateway-io.mediatek.inc", ENV.get("AIDE_IO_API_KEY"),  "MTK12265"),
    "aide-io-ds901472": ("https://mlop-azure-gateway-io.mediatek.inc", ENV.get("AIDE_DS901472_IO_KEY"), "ds901472"),
    "aide-ds901472":    ("https://mlop-azure-gateway.mediatek.inc",    ENV.get("AIDE_DS901472_PRI_KEY"), "ds901472"),
    "aide-molycrgpt001":("https://mlop-azure-gateway.mediatek.inc",    ENV.get("AIDE_MOLYCRGPT001_KEY"), "srv_molyCRGPT001"),
    "aide-crlogai001":  ("https://mlop-azure-gateway.mediatek.inc",     ENV.get("AIDE_CRLOGAI001_KEY"),  "srv_cr_log_ai001"),
}
CAT = json.loads(Path(sorted(Path(".").glob("aide_catalog_*.json"))[-1]).read_text(encoding="utf-8"))
INHOUSE_ONLY = {"aide-ds901472", "aide-molycrgpt001", "aide-crlogai001"}

EFFORTS_CHAT = ["xhigh", "high", "medium", "low", "minimal"]  # try in order; store max accepted + per-level errors

def probe_chat(base, key, uid, model):
    """Return (max_effort_accepted, probe_detail)."""
    h = {"Authorization": f"Bearer {key}", "x-user-id": uid, "Content-Type": "application/json"}
    is_openai_series = model.startswith("azure/") or model.startswith("openai/")
    tok_key = "max_completion_tokens" if is_openai_series else "max_tokens"
    results = {}
    accepted = None
    for eff in ["none"] + EFFORTS_CHAT:
        body = {"model": model, tok_key: 40, "reasoning_effort": eff,
                "messages": [{"role": "user", "content": "hi"}], "stream": False}
        if model.startswith("mtk/"):
            body["extra_body"] = {"chat_template_kwargs": {"enable_thinking": eff != "none"}}
        try:
            q = httpx.post(f"{base}/v1/chat/completions", headers=h, json=body, timeout=45, verify=False)
            ok = q.status_code == 200
            results[eff] = q.status_code
            if ok and eff != "none" and accepted is None:
                accepted = eff
        except Exception as e:
            results[eff] = f"EXC:{type(e).__name__}"
    return accepted, results

def e2e_chat(base, key, uid, model):
    h = {"Authorization": f"Bearer {key}", "x-user-id": uid, "Content-Type": "application/json"}
    is_openai_series = model.startswith("azure/") or model.startswith("openai/")
    tok_key = "max_completion_tokens" if is_openai_series else "max_tokens"
    body = {"model": model, tok_key: 60, "messages": [{"role": "user", "content": "Reply exactly: OK"}], "stream": False}
    if model.startswith("mtk/"):
        body["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    t0 = time.monotonic()
    try:
        q = httpx.post(f"{base}/v1/chat/completions", headers=h, json=body, timeout=90, verify=False)
        el = round(time.monotonic() - t0, 2)
        if q.status_code == 200:
            j = q.json()
            ch = (j.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            txt = (msg.get("content") or "") or (msg.get("reasoning_content") or "")
            return {"status": 200, "ok": True, "text": txt[:40], "finish": ch.get("finish_reason"), "elapsed": el}
        body_txt = q.text[:220]
        if q.status_code == 403 and ("monthly budget" in body_txt or "commercial models" in body_txt):
            return {"status": 403, "ok": None, "note": "monthly commercial budget=0 (allowed; not model failure)", "elapsed": el}
        if q.status_code == 500 and "quota is exhausted" in body_txt:
            return {"status": 500, "ok": None, "note": "daily quota exhausted", "elapsed": el}
        return {"status": q.status_code, "ok": False, "error": body_txt, "elapsed": el}
    except Exception as e:
        return {"status": "EXC", "ok": False, "error": f"{type(e).__name__}: {str(e)[:100]}", "elapsed": round(time.monotonic()-t0,2)}

results = {}
for slug, (base, key, uid) in ACCT.items():
    if not key:
        results[slug] = {"error": "NO_KEY"}
        continue
    models = CAT[slug]["chat_models"]
    if slug in INHOUSE_ONLY:
        models = [m for m in models if m.startswith("mtk/")]
    rows = {}
    for m in models:
        entry = {}
        # Quick E2E first (cheap single call) — only for in-scope models
        entry["e2e"] = e2e_chat(base, key, uid, m)
        # Reasoning probe only when E2E reachable/e2e not budget-blocked, and model family worth probing
        if entry["e2e"].get("status") == 200:
            max_eff, detail = probe_chat(base if True else None, key, uid, m)
            entry["max_reasoning_effort"] = max_eff
            entry["effort_probe"] = detail
        rows[m] = entry
        print(slug, m, "e2e:", entry["e2e"].get("status"), "OK" if entry["e2e"].get("ok") else (entry["e2e"].get("note") or entry["e2e"].get("error",""))[:60],
              "| max_effort:", entry.get("max_reasoning_effort"), flush=True)
    results[slug] = rows

ts = time.strftime("%Y%m%d_%H%M%S")
Path(f"aide_e2e_efforts_{ts}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("saved", f"aide_e2e_efforts_{ts}.json")
