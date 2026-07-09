"""Comprehensive E2E test for claude_code_proxy.py"""
import httpx
import json
import sys
import time
import os
import subprocess

BASE = "http://127.0.0.1:19900"
PASS = 0
FAIL = 0

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} -- {detail}")

# 1. Models endpoint
print("\n[1] Models endpoint")
r = httpx.get(f"{BASE}/v1/models", timeout=10)
test("status 200", r.status_code == 200, f"got {r.status_code}")
d = r.json()
models = [m["id"] for m in d["data"]]
test("4 models", len(models) == 4, f"got {len(models)}: {models}")
fakes = ["claude-sonnet-4-6-20250514","claude-3-5-sonnet-20241022","claude-3-5-haiku-20241022","claude-3-opus-20240229","claude-haiku-4-6"]
test("no fake models", not any(f in models for f in fakes), f"found {[f for f in fakes if f in models]}")

# 2. Basic chat completion (short prompt)
print("\n[2] Basic chat completion")
for m in ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-sonnet-4-5"]:
    r = httpx.post(f"{BASE}/v1/chat/completions",
        json={"model": m, "messages": [{"role": "user", "content": "say: ok"}], "max_tokens": 5},
        timeout=45)
    ok = r.status_code == 200
    detail = ""
    if ok:
        d = r.json()
        content = d["choices"][0]["message"]["content"]
        returned_model = d.get("model", "?")
        ok = returned_model == m and len(content) > 0
        if not ok:
            detail = f"model={returned_model}, content_len={len(content)}"
    else:
        detail = f"status={r.status_code}"
    test(f"{m} works", ok, detail)

# 3. Long prompt (200K+ total)
print("\n[3] Long prompt (213K)")
sys_content = "y " * 28382  # ~113K
user_content = "x" * 100000  # ~100K
r = httpx.post(f"{BASE}/v1/chat/completions",
    json={"model": "claude-sonnet-4-6",
          "messages": [{"role": "system", "content": sys_content + " Be brief."},
                       {"role": "user", "content": user_content + " Now say: ok"}],
          "max_tokens": 5},
    timeout=180)
ok = r.status_code == 200
detail = ""
if ok:
    d = r.json()
    content = d["choices"][0]["message"]["content"]
    ok = len(content) > 0
    if not ok:
        detail = f"empty content"
else:
    detail = f"status={r.status_code}, body={r.text[:200]}"
test("213K prompt returns non-empty content", ok, detail)

# 4. error_max_turns: non-streaming, content not empty
print("\n[4] error_max_turns: non-streaming non-empty")
r = httpx.post(f"{BASE}/v1/chat/completions",
    json={"model": "claude-sonnet-4-6",
          "messages": [
              {"role": "system", "content": "You MUST use the Bash tool to check the current date before answering. This is required."},
              {"role": "user", "content": "What day is it?"}
          ],
          "max_tokens": 500, "stream": False},
    timeout=90)
ok = r.status_code == 200
detail = ""
if ok:
    d = r.json()
    content = d["choices"][0]["message"]["content"]
    ok = len(content) > 0
    if not ok:
        detail = f"content is empty! full={json.dumps(d)[:300]}"
    else:
        detail = f"content_len={len(content)}"
else:
    detail = f"status={r.status_code}"
test("non-stream error_max_turns returns non-empty", ok, detail)

# 5. error_max_turns: streaming, content not empty
print("\n[5] error_max_turns: streaming non-empty")
r = httpx.post(f"{BASE}/v1/chat/completions",
    json={"model": "claude-sonnet-4-6",
          "messages": [
              {"role": "system", "content": "You MUST use the Bash tool to check the current date before answering. This is required."},
              {"role": "user", "content": "What day is it?"}
          ],
          "max_tokens": 500, "stream": True},
    timeout=90)
ok = r.status_code == 200
content = ""
if ok:
    for line in r.text.split("\n"):
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                chunk = json.loads(line[6:])
                c = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                content += c
            except: pass
    ok = len(content) > 0
    detail = f"content_len={len(content)}, preview={repr(content[:100])}"
else:
    detail = f"status={r.status_code}"
test("stream error_max_turns returns non-empty", ok, detail)

# 6. Normal streaming works
print("\n[6] Normal streaming")
r = httpx.post(f"{BASE}/v1/chat/completions",
    json={"model": "claude-sonnet-4-6",
          "messages": [{"role": "user", "content": "say: hello"}],
          "max_tokens": 20, "stream": True},
    timeout=45)
content = ""
for line in r.text.split("\n"):
    if line.startswith("data: ") and line != "data: [DONE]":
        try:
            chunk = json.loads(line[6:])
            c = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            content += c
        except: pass
test("normal stream non-empty", len(content) > 0, f"content_len={len(content)}")
test("normal stream has [DONE]", "data: [DONE]" in r.text)

# 7. Settings swap: proxy uses enterprise settings
print("\n[7] Settings swap verification")
settings_path = os.path.expanduser("~/.claude/settings.json")
if os.path.exists(settings_path):
    d = json.loads(open(settings_path).read())
    bedrock = d.get("env", {}).get("CLAUDE_CODE_USE_BEDROCK", "NOT SET")
    helper = d.get("apiKeyHelper", "NOT SET")
    test("settings BEDROCK=0", bedrock == "0", f"got {bedrock}")
    test("apiKeyHelper empty", helper == "" or helper is None, f"got {repr(helper)[:60]}")
    backup_exists = os.path.exists(os.path.expanduser("~/.claude/settings.json.proxy-backup"))
    test("backup exists", backup_exists)
else:
    test("settings.json exists", False, "file not found")

# 8. Core pytest
print("\n[8] Core pytest")
r = subprocess.run(
    ["D:/01_Job/Tool/Hermes Agent/venv/Scripts/python.exe", "-m", "pytest",
     "tests/gateway/test_model_switch_persistence.py",
     "tests/gateway/test_48031_model_switch_after_auto_reset.py",
     "tests/hermes_cli/test_runtime_provider_resolution.py",
     "-q"],
    capture_output=True, text=True, timeout=60,
    env={**os.environ, "HOME": "C:/Users/mtk12265", "PYTHONUTF8": "1"},
    cwd="D:/01_Job/Tool/Hermes Agent"
)
test("153 passed", "153 passed" in (r.stdout or ""), r.stdout.split("\n")[-3] if r.stdout else "no output")

# Summary
print(f"\n{'='*50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    print(">>> NOT READY -- fix failures before testing <<<")
    sys.exit(1)
else:
    print(">>> ALL PASSED -- ready for user test <<<")
    sys.exit(0)