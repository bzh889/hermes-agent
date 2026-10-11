"""AIDE 6-provider catalog 盤點: /v1/models (data[] chat + models[] codex) + /llm/v3/models.

輸出 aide_catalog_<ts>.json — 供後續 reasoning probe / E2E / footer 驗證共用。
不輸出任何 key。分類: in-house = mtk/* 與 databricks/*；commercial = 其他。
"""
import httpx, json, subprocess, time
from pathlib import Path

ENV = {}
for line in Path.home().joinpath(".hermes", ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        ENV[k.strip()] = v.strip().strip('"').strip("'")

r = subprocess.run(
    ["bash", "-lc", "cd ~/.cchelper && ./coding-cli-helper.exe auth token --tool claude --domain oa"],
    capture_output=True, text=True, timeout=60)
OA_KEY = r.stdout.strip()

PROVIDERS = {
    # slug: (gateway_base, key, x-user-id, scope)
    "aide":               ("https://mlop-azure-gateway.mediatek.inc",      OA_KEY,                       "MTK12265",        "all"),
    "aide-io":            ("https://mlop-azure-gateway-io.mediatek.inc",   ENV.get("AIDE_IO_API_KEY"),   "MTK12265",        "all"),
    "aide-ds901472":      ("https://mlop-azure-gateway.mediatek.inc",      ENV.get("AIDE_DS901472_PRI_KEY"), "ds901472",     "in_house_only"),
    "aide-molycrgpt001":  ("https://mlop-azure-gateway.mediatek.inc",      ENV.get("AIDE_MOLYCRGPT001_KEY"), "srv_molyCRGPT001", "in_house_only"),
    "aide-crlogai001":    ("https://mlop-azure-gateway.mediatek.inc",      ENV.get("AIDE_CRLOGAI001_KEY"),   "srv_cr_log_ai001",  "in_house_only"),
    "aide-io-ds901472":   ("https://mlop-azure-gateway-io.mediatek.inc",   ENV.get("AIDE_DS901472_IO_KEY"),  "ds901472",     "all"),
    # databricks (responses-only) providers
    "aide-responses":            ("https://mlop-azure-gateway.mediatek.inc",    OA_KEY,                     "MTK12265",   "all"),
    "aide-responses-io":         ("https://mlop-azure-gateway-io.mediatek.inc", ENV.get("AIDE_IO_API_KEY"), "MTK12265",   "all"),
    "aide-responses-io-ds901472":("https://mlop-azure-gateway-io.mediatek.inc", ENV.get("AIDE_DS901472_IO_KEY"), "ds901472","all"),
    "aide-responses-ds901472":   ("https://mlop-azure-gateway.mediatek.inc",    ENV.get("AIDE_DS901472_PRI_KEY"), "ds901472","all"),
    "aide-responses-molycrgpt001":("https://mlop-azure-gateway.mediatek.inc",   ENV.get("AIDE_MOLYCRGPT001_KEY"), "srv_molyCRGPT001", "all"),
    "aide-responses-crlogai001": ("https://mlop-azure-gateway.mediatek.inc",    ENV.get("AIDE_CRLOGAI001_KEY"), "srv_cr_log_ai001", "all"),
}

def classify(mid: str) -> str:
    m = (mid or "").lower()
    if m.startswith("mtk/") or m.startswith("databricks/"):
        return "in-house"
    return "commercial"

out = {}
for slug, (base, key, uid, scope) in PROVIDERS.items():
    if not key:
        out[slug] = {"error": "NO_KEY"}
        continue
    h = {"Authorization": f"Bearer {key}", "x-user-id": uid}
    entry = {"base": base, "uid": uid, "scope": scope}
    try:
        v1 = httpx.get(f"{base}/v1/models", headers=h, timeout=30, verify=False).json()
        entry["chat_models"] = sorted({
            m["id"] for m in v1.get("data", [])
            if isinstance(m, dict) and m.get("type") == "chat"
        })
        entry["responses_models"] = sorted({
            m["slug"] for m in (v1.get("models") or [])
            if isinstance(m, dict) and m.get("slug")
        })
        entry["responses_meta"] = {
            m["slug"]: {
                "ctx": m.get("context_window"),
                "efforts": [e.get("effort") for e in (m.get("supported_reasoning_levels") or [])],
                "supported_in_api": m.get("supported_in_api"),
                "visibility": m.get("visibility"),
            }
            for m in (v1.get("models") or []) if isinstance(m, dict) and m.get("slug")
        }
        v3r = httpx.get(f"{base}/llm/v3/models", headers=h, timeout=30, verify=False)
        if v3r.status_code == 200:
            v3 = v3r.json().get("data", [])
            entry["v3_meta"] = {}
            for e in v3:
                if not isinstance(e, dict):
                    continue
                entry["v3_meta"][e["id"]] = {
                    "max_model_len": e.get("max_model_len"),
                    "root": e.get("root"),
                    "aliases": e.get("aliases", []),
                    "available": e.get("available"),
                }
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {str(e)[:150]}"
    out[slug] = entry
    print(slug, "chat:", len(entry.get("chat_models", [])),
          "responses:", len(entry.get("responses_models", [])),
          "v3:", len(entry.get("v3_meta", {})),
          "err:", entry.get("error"))

ts = time.strftime("%Y%m%d_%H%M%S")
Path(f"aide_catalog_{ts}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("saved aide_catalog_" + ts + ".json")
