"""Non-chat AIDE models via Azure-deployments routes: TTS + image (4 accounts).

Routes (Azure OpenAI convention, same as plugins/image_gen/aide):
  TTS   POST {gw}/openai/deployments/{m}/audio/speech?api-version=...
  Image POST {gw}/openai/deployments/{m}/images/generations?api-version=...
Quota/budget 403s are classified separately from route/model failures.
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

PRI = "https://mlop-azure-gateway.mediatek.inc"
IO = "https://mlop-azure-gateway-io.mediatek.inc"
ACCTS = [
    ("PRI mtk12265",  PRI, OA, "MTK12265"),
    ("IO  mtk12265",  IO, ENV["AIDE_IO_API_KEY"], "MTK12265"),
    ("IO  ds901472",  IO, ENV["AIDE_DS901472_IO_KEY"], "ds901472"),
    ("PRI ds901472",  PRI, ENV["AIDE_DS901472_PRI_KEY"], "ds901472"),
]
TTS_MODELS = ["aide-tts", "aide-tts-hd", "gpt-4o-mini-tts"]
IMG_MODELS = ["gpt-image-2", "Dalle3", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]

def classify(code, text):
    t = text[:200]
    if code == 200:
        return "OK"
    if code == 403 and "daily quota" in t:
        return "QUOTA(daily)"
    if code == 403 and "monthly budget" in t:
        return "BUDGET(monthly=0)"
    return f"{code} {t[:90].replace(chr(10), ' ')}"

rows = []
for name, base, key, uid in ACCTS:
    h = {"api-key": key, "Authorization": f"Bearer {key}", "x-user-id": uid, "Content-Type": "application/json"}
    for m in TTS_MODELS:
        url = f"{base}/openai/deployments/{m}/audio/speech?api-version=2025-03-01-preview"
        t0 = time.monotonic()
        try:
            r = httpx.post(url, headers=h, json={"model": m, "input": "你好，這是測試。", "voice": "alloy"}, timeout=90, verify=False)
            audio = r.status_code == 200 and len(r.content) > 500
            res = classify(r.status_code, r.text if r.status_code != 200 else "") + (f" audio={len(r.content)}B" if r.status_code == 200 else "")
            if r.status_code == 200 and not audio:
                res = f"200-but-tiny({len(r.content)}B)"
        except Exception as e:
            res = f"EXC {type(e).__name__}"
        rows.append((name, "tts", m, res, round(time.monotonic() - t0, 1)))
        print(rows[-1], flush=True)
    for m in IMG_MODELS:
        url = f"{base}/openai/deployments/{m}/images/generations?api-version=2024-05-01-preview"
        t0 = time.monotonic()
        body = {"prompt": "a plain red circle on white background", "n": 1, "size": "1024x1024"}
        try:
            r = httpx.post(url, headers=h, json=body, timeout=150, verify=False)
            if r.status_code == 200:
                d = (r.json().get("data") or [{}])[0]
                res = "OK " + ("b64" if d.get("b64_json") else ("url" if d.get("url") else "no-image-field"))
            else:
                res = classify(r.status_code, r.text)
        except Exception as e:
            res = f"EXC {type(e).__name__}"
        rows.append((name, "image", m, res, round(time.monotonic() - t0, 1)))
        print(rows[-1], flush=True)

Path("aide_nonchat_probe.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("DONE")
