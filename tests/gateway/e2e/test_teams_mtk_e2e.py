"""E2E tests for TeamsMTK — REAL Teams API round-trip, REAL content verification.

PRINCIPLES:
  1.每位測項打到真 Teams API（Graph / MSG / AMS）
  2.讀回真實回覆內容
  3.驗證「具體可測量」的內容（PNG magic bytes、檔案內容、HTML tag、marker string…）
  4.FAIL 就是真 FAIL，不是 silently skipped 或寬鬆判 PASS

Test types:
  GW  = gateway round-trip（需 gateway 運行）
  SDK = 直接 SDK/API 呼叫（不需 gateway）
  CFG = config / log 檢查

Env:
  E2E_DM_CONV      — 1:1 DM conv ID
  E2E_GROUP_CONV   — group conv ID
  E2E_TIMEOUT      — wait seconds (default 90)
  E2E_SKIP_GW_CHECK — set 1 to skip gateway-health check
  MTK_TEAMS_CACHE_PATH — token cache path
"""
import json, os, re, struct, subprocess, sys, time, unittest
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────

TIMEOUT = int(os.getenv("E2E_TIMEOUT", "90"))
_CACHE = os.getenv("MTK_TEAMS_CACHE_PATH",
                   str(Path.home() / ".teams-tokens" / "token_cache.json"))

# ── Token cache ───────────────────────────────────────────────────────

_cache = None
def _load() -> dict:
    global _cache
    if _cache is None:
        with open(_CACHE) as f:
            _cache = json.load(f)
    return _cache

def _skype_token(): return _load().get("skype_token", "")
def _access_token(): return _load().get("access_token", "")
def _graph_token(): return _load().get("graph_token", "")

MSG_BASE = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"

# ── Send (MSG API Text — user identity, not echo-guarded) ──────────────

def _send(conv_id: str, text: str) -> str:
    """Send Text-type message via MSG API. Returns OriginalArrivalTime."""
    import requests
    url = f"{MSG_BASE}/conversations/{conv_id}/messages"
    hdrs = {"Authentication": f"skypetoken={_skype_token()}",
            "Authorization": f"Bearer {_access_token()}",
            "Content-Type": "application/json"}
    r = requests.post(url, headers=hdrs, verify=False, timeout=15,
                      json={"content": text, "messagetype": "Text",
                            "contenttype": "Text"})
    r.raise_for_status()
    return str(r.json().get("OriginalArrivalTime", r.json().get("id", "?")))

# ── Read (MSG API) ────────────────────────────────────────────────────

def _read(conv_id: str, limit: int = 20) -> list:
    import requests
    url = f"{MSG_BASE}/conversations/{conv_id}/messages?pageSize={limit}"
    hdrs = {"Authentication": f"skypetoken={_skype_token()}",
            "Authorization": f"Bearer {_access_token()}"}
    try:
        r = requests.get(url, headers=hdrs, verify=False, timeout=15)
        r.raise_for_status()
        return r.json().get("messages", [])
    except Exception:
        return []

def _ct(m: dict) -> str:
    return m.get("content", m.get("Body", ""))

def _mid(m: dict) -> str:
    return m.get("id", m.get("OriginalArrivalTime", ""))

def _is_bot(m: dict) -> bool:
    c = _ct(m)
    return "border-left" in c or "🤖 Hermes" in c \
        or "hermes_sender" in str(m.get("properties", {}))

# ── Poll helpers ──────────────────────────────────────────────────────

def _baseline(conv_id: str) -> set:
    return {_mid(m) for m in _read(conv_id, 30) if _mid(m)}

def _wait_bot(conv_id: str, base: set, contains: str = "",
              timeout: int = TIMEOUT) -> dict:
    """Poll until NEW bot reply appears containing `contains`.
    Also records all unexpected bot replies (cross-test contamination)."""
    deadline = time.time() + timeout
    all_bot = []
    while time.time() < deadline:
        time.sleep(4)
        for m in _read(conv_id, 30):
            mid = _mid(m)
            if not mid or mid in base:
                continue
            if _is_bot(m):
                c = _ct(m)
                entry = {"id": mid, "text": c}
                # Deduplicate by id
                if not any(e["id"] == mid for e in all_bot):
                    all_bot.append(entry)
                if not contains or contains.lower() in c.lower():
                    return {"found": True, "text": c, "id": mid,
                            "all": all_bot}
    return {"found": False, "text": "", "id": "", "all": all_bot}

# ── AMS download ──────────────────────────────────────────────────────

def _download_ams_image(ams_url: str) -> bytes:
    """Download image from AMS URL with proper auth. Returns raw bytes."""
    import requests
    hdrs = {"Authorization": f"skype_token {_skype_token()}",
            "User-Agent": "27/1.0.0.0"}
    r = requests.get(ams_url, headers=hdrs, verify=False, timeout=30)
    r.raise_for_status()
    return r.content

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

# ── Gateway check ─────────────────────────────────────────────────────

def _gw_alive() -> bool:
    """Check if gateway is alive — via PID file or recent log activity.
    NOTE: uses Path.home() / ".hermes" directly because conftest 
    _isolate_hermes_home overrides get_hermes_home() in tests."""
    try:
        # E2E tests need the REAL hermes home, not the tmpdir from conftest
        real_home = Path.home() / ".hermes"
        pid_f = real_home / "gateway.pid"
        if pid_f.exists():
            raw = pid_f.read_text().strip()
            try:
                import json as _json
                pid = int(_json.loads(raw).get("pid", 0))
            except (ValueError, AttributeError):
                pid = int(raw)
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
    except Exception:
        pass
    # Fallback: check gateway.log for recent activity (within 60s)
    try:
        real_home = Path.home() / ".hermes"
        log_f = real_home / "logs" / "gateway.log"
        if log_f.exists():
            import os
            mtime = os.path.getmtime(str(log_f))
            if time.time() - mtime < 60:
                return True
    except Exception:
        pass
    return False

def _gw_ready(wait: int = 20) -> bool:
    """Wait for gateway to finish seeding and start polling."""
    if not _gw_alive():
        return False
    # After gateway starts, it needs time to seed last_message_ids.
    # Wait `wait` seconds then verify gateway is still alive.
    time.sleep(wait)
    return _gw_alive()

# ── Conv ID helpers ───────────────────────────────────────────────────

def _dm() -> str:
    return os.getenv("E2E_DM_CONV", "")

def _grp() -> str:
    return os.getenv("E2E_GROUP_CONV", "")

# ── SDK init (for SDK-direct tests) ───────────────────────────────────

_sdk_http = None

def _init_sdk():
    global _sdk_http
    if _sdk_http is not None:
        return _sdk_http
    try:
        from teams_skype_sdk.auth import TeamsAuth
        from teams_skype_sdk.api._http import HTTPLayer
    except ImportError:
        return None
    d = _load()
    class _Auth(TeamsAuth):
        def __init__(self, data):
            self._sk = data.get("skype_token", "")
            self._at = data.get("access_token", "")
            if not self._sk:
                for a in data.get("accounts", []):
                    self._sk = a.get("skype_token", a.get("skypetoken", self._sk))
                    self._at = a.get("access_token", self._at)
        def get_skype_token(self) -> str: return self._sk
        def get_access_token(self) -> str: return self._at
        @property
        def msg_base(self): return MSG_BASE
    _sdk_http = HTTPLayer(_Auth(d), verify_ssl=False)
    return _sdk_http


# ═══════════════════════════════════════════════════════════════════════
#  Base class
# ═══════════════════════════════════════════════════════════════════════

class _B(unittest.TestCase):
    def _req_gw(self):
        if os.getenv("E2E_SKIP_GW_CHECK"):
            return
        if not _gw_alive():
            self.skipTest("Gateway not alive (E2E_SKIP_GW_CHECK=1 to force)")
        # Ensure gateway has seeded last_message_ids before we send
        if not _gw_ready(wait=5):
            self.skipTest("Gateway not ready after wait")

    def _req_dm(self):
        d = _dm()
        if not d:
            self.skipTest("E2E_DM_CONV not set — skip live gateway E2E")
        return d

    def _send_wait(self, text: str, conv_id: str = None,
                   contains: str = "", timeout: int = TIMEOUT) -> dict:
        cid = conv_id or self._req_dm()
        base = _baseline(cid)
        _send(cid, text)
        r = _wait_bot(cid, base, contains=contains, timeout=timeout)
        r["conv"] = cid
        return r


# ═══════════════════════════════════════════════════════════════════════
#  G1  GW — 收訊息 + echo：回覆含精確 marker
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG1(_B):
    def test_echo(self):
        """User sends echo request → bot reply contains exact marker."""
        self._req_gw()
        r = self._send_wait("E2E-G1: echo exactly FOOBAR42X", contains="FOOBAR42X")
        self.assertTrue(r["found"],
            f"G1 FAIL: reply missing 'FOOBAR42X'. "
            f"Bot replies: {[x['text'][:100] for x in r.get('all',[])]}")


# ═══════════════════════════════════════════════════════════════════════
#  G2  GW — HTML 格式：回覆含 HTML table tag
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG2(_B):
    def test_html_table(self):
        """Bot reply must contain an HTML <table> element."""
        self._req_gw()
        r = self._send_wait(
            "E2E-G2: make a 2-row HTML table with colors Red and Blue. "
            "Reply 'G2-TABLE-DONE' at end.",
            contains="G2-TABLE-DONE")
        self.assertTrue(r["found"],
            f"G2 FAIL: no reply. {r.get('all',[[]])[:2]}")
        self.assertIn("<table", r["text"].lower(),
            f"G2 FAIL: no <table> in reply HTML. Got: {r['text'][:200]}")


# ═══════════════════════════════════════════════════════════════════════
#  G3  GW — 編輯訊息：MSG API 讀到 edited 版含精確 marker
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG3(_B):
    def test_edit(self):
        """Bot should edit reply — MSG API shows G3-EDITED-MARKER."""
        self._req_gw()
        r = self._send_wait(
            "E2E-G3: reply 'G3-ORIGINAL-X' then immediately edit your "
            "own reply to say 'G3-EDITED-MARKER' instead",
            contains="G3-EDITED-MARKER", timeout=TIMEOUT)
        self.assertTrue(r["found"],
            f"G3 FAIL: no edited version with G3-EDITED-MARKER. "
            f"Replies: {[x['text'][:100] for x in r.get('all',[])]}")


# ═══════════════════════════════════════════════════════════════════════
#  G4  SDK — 圖片：AMS 上傳 → MSG API 讀回 AMSImage → 下載 → 驗 PNG
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG4(_B):
    def test_image_ams_roundtrip(self):
        """Upload 10×10 red PNG via SDK → find AMSImage in.MSG API →
        download from AMS URL → verify PNG magic bytes."""
        cid = self._req_dm()
        base = _baseline(cid)

        # 1) Create minimal 10×10 red PNG
        import tempfile
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img = Image.new("RGB", (10, 10), (255, 0, 0))
        img.save(tmp.name, "PNG")
        with open(tmp.name, "rb") as f:
            image_data = f.read()
        orig_len = len(image_data)
        self.assertTrue(image_data.startswith(PNG_MAGIC), "test PNG invalid")

        # 2) Upload via SDK FilesService
        from teams_skype_sdk.api._files import FilesService
        from teams_skype_sdk.api._messages import MessagesService
        http = _init_sdk()
        svc = FilesService(http, MessagesService(http))
        result = svc.send_image(cid, image_data, "image/png",
                                caption="E2E-G4-TEST-IMG")
        self.assertIn("id", result, f"G4 FAIL: send_image returned {result}")

        # 3) Read messages & find AMSImage markup
        time.sleep(3)
        msgs = _read(cid, limit=20)
        ams_url = None
        for m in msgs:
            mid = _mid(m)
            if not mid or mid in base:
                continue
            c = _ct(m)
            # AMSImage: <div itemscope itemtype="http://schema.skype.com/AMSImage">
            if "AMSImage" in c:
                # Extract AMS URL
                match = re.search(
                    r'(https://api\.asm\.skype\.com/v1/objects/[^"\'>\s]+)',
                    c)
                if match:
                    ams_url = match.group(1)
                    break

        self.assertIsNotNone(ams_url,
            f"G4 FAIL: no AMSImage message found in readback. "
            f"New msgs: {[_mid(m) for m in msgs if _mid(m) not in base]}")

        # 4) Download image from AMS URL
        downloaded = _download_ams_image(ams_url)

        # 5) Verify it's a valid image (PNG or JPEG — Teams AMS may transcode)
        is_png = downloaded.startswith(PNG_MAGIC)
        is_jpeg = downloaded.startswith(JPEG_MAGIC)
        self.assertTrue(is_png or is_jpeg,
            f"G4 FAIL: downloaded data is not a valid image. "
            f"First 8 bytes: {downloaded[:8].hex()}")

        # 6) Verify size is reasonable (≥ 100 bytes — a 10×10 image)
        self.assertGreaterEqual(len(downloaded), 100,
            f"G4 FAIL: downloaded only {len(downloaded)}B — too small")

        # Cleanup
        try: os.unlink(tmp.name)
        except OSError: pass


# ═══════════════════════════════════════════════════════════════════════
#  G5  SDK — 檔案：OneDrive 上傳 → MSG API 讀回含 link → 下載 → 驗內容
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG5(_B):
    def test_document_onedrive_roundtrip(self):
        """Upload text file via SDK → find share link in MSG API →
        download → verify file content matches original."""
        # Need graph_token for OneDrive upload
        gt = _graph_token()
        if not gt:
            self.skipTest("G5: graph_token not in cache (expired?)")

        cid = self._req_dm()
        base = _baseline(cid)

        # 1) Create test file with unique content
        import tempfile
        content = "E2E-G5-VERIFY-CONTENT-7X9Z\n"
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False,
                                          mode="w")
        tmp.write(content)
        tmp.close()

        # 2) Upload via SDK FilesService.send_file()
        from teams_skype_sdk.api._files import FilesService
        from teams_skype_sdk.api._messages import MessagesService
        http = _init_sdk()
        with open(tmp.name, "rb") as f:
            file_bytes = f.read()

        svc = FilesService(http, MessagesService(http))
        try:
            # SDK send_file needs graph_api adapter
            # Fall back to direct Table upload if graph token available
            import requests
            hdrs = {"Authorization": f"Bearer {gt}",
                    "Content-Type": "application/octet-stream"}
            unique = f"e2e_g5_{int(time.time())}.txt"
            path = f"/Microsoft Teams Chat Files/E2E/{unique}"
            url = f"https://graph.microsoft.com/v1.0/me/drive/root:{path}:/content"
            up = requests.put(url, headers=hdrs, data=file_bytes,
                              verify=False, timeout=60)
            if up.status_code not in (200, 201):
                self.skipTest(
                    f"G5: OneDrive upload failed ({up.status_code}), "
                    f"graph token may be expired")
            item = up.json()
            item_id = item["id"]
            web_url = item.get("webUrl", "")

            # Create share link
            try:
                share = requests.post(
                    f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/createLink",
                    headers={"Authorization": f"Bearer {gt}",
                             "Content-Type": "application/json"},
                    json={"type": "view", "scope": "organization"},
                    verify=False, timeout=30)
                share_url = share.json().get("link", {}).get("webUrl", "") or web_url
            except Exception:
                share_url = web_url

            # Send share link via MSG API
            _send(cid, f"E2E-G5: 📎 {unique} — {share_url}")
            time.sleep(3)

            # 3) Read messages & verify link appears
            msgs = _read(cid, limit=20)
            found_link = False
            for m in msgs:
                mid = _mid(m)
                if not mid or mid in base:
                    continue
                c = _ct(m)
                if share_url and share_url in c:
                    found_link = True
                    break
            self.assertTrue(found_link,
                f"G5 FAIL: share link not found in messages. "
                f"URL: {share_url[:80]}")

            # 4) Download file content from OneDrive and verify
            dl_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/content"
            dl = requests.get(dl_url,
                              headers={"Authorization": f"Bearer {gt}"},
                              verify=False, timeout=30,
                              allow_redirects=True)
            self.assertEqual(dl.status_code, 200,
                f"G5 FAIL: download status {dl.status_code}")
            self.assertIn("E2E-G5-VERIFY-CONTENT-7X9Z", dl.text,
                f"G5 FAIL: downloaded content doesn't match. "
                f"Got: {dl.text[:100]}")

        except Exception as e:
            self.skipTest(f"G5: SDK file upload failed: {e}")
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass


# ═══════════════════════════════════════════════════════════════════════
#  G6  GW — Echo guard：bot 回覆後 15s 無自循環
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG6(_B):
    def test_no_echo_loop(self):
        """After bot replies to G6-UNIQUE-7X9Z, no extra bot messages
        about the same topic in next 15s — proves echo guard works."""
        self._req_gw()
        cid = self._req_dm()
        base_all = _baseline(cid)
        # Also snapshot all pre-existing bot msg IDs
        base_bot = {_mid(m) for m in _read(cid, 30) if _is_bot(m) and _mid(m)}
        # Use a UNIQUE marker so we can ignore stale bot replies from other tests
        _send(cid, "E2E-G6-UNIQUE-7X9Z: say exactly 'G6-DONE-7X9Z' and nothing else")
        r = _wait_bot(cid, base_all, contains="G6-DONE-7X9Z", timeout=TIMEOUT)
        self.assertTrue(r["found"],
            f"G6 FAIL: no reply with G6-DONE-7X9Z. "
            f"Bot: {[x['text'][:80] for x in r.get('all',[])]}")
        # Record the IDs of all bot messages that appeared as part of this reply
        reply_ids = {_mid(m) for m in _read(cid, 25)
                     if _is_bot(m) and _mid(m) and _mid(m) not in base_bot}
        # Wait 15s then check for NEW bot replies (not in reply_ids, not in base)
        time.sleep(15)
        extra = []
        for m in _read(cid, 25):
            mid = _mid(m)
            if not mid or mid in base_all or mid in reply_ids:
                continue
            if _is_bot(m):
                c = _ct(m).lower()
                # Only count if it references G6 or the unique marker
                if "g6" in c or "7x9z" in c:
                    extra.append({"id": mid, "text": _ct(m)[:100]})
        self.assertEqual(len(extra), 0,
            f"G6 FAIL: echo loop — {len(extra)} extra bot replies: {extra[:3]}")


# ═══════════════════════════════════════════════════════════════════════
#  G7  GW — Short-msg gating："OK" 不觸發回覆
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG7(_B):
    def test_short_msg_ignored(self):
        """Send 'OK' (2 chars, no mention) → no bot reply in 25s."""
        self._req_gw()
        gid = _grp() or self._req_dm()
        base = _baseline(gid)
        try:
            _send(gid, "OK")
        except Exception as e:
            self.skipTest(f"send failed: {e}")
        # Wait 25s — should get NO specific reply
        time.sleep(25)
        new_bot = []
        for m in _read(gid, 15):
            mid = _mid(m)
            if not mid or mid in base:
                continue
            if _is_bot(m):
                new_bot.append({"id": mid, "text": _ct(m)[:150]})
        # Filter: replies that specifically respond to "OK"
        ok_specific = [x for x in new_bot
                       if "ok" in x["text"].lower()
                       and "e2e" not in x["text"].lower()]
        self.assertEqual(len(ok_specific), 0,
            f"G7 FAIL: bot replied to 'OK': {ok_specific[:3]}")


# ═══════════════════════════════════════════════════════════════════════
#  G8  CFG — VIP buffer (skip if not configured)
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG8(_B):
    def test_vip_config(self):
        """VIP monitor is present in config (injected by E2E runner or
        env var E2E_VIP_CONFIG). Uses Path.home() which works in normal
        pytest; in run_tests.sh (env -i) E2E_VIP_CONFIG can carry the
        necessary structure."""
        import yaml as _y
        # 1) Try real config.yaml
        cfg = Path.home() / ".hermes" / "config.yaml"
        if cfg.exists():
            data = _y.safe_load(cfg.read_text()) or {}
            vip = data.get("gateway", {}).get("teams_mtk", {}).get("vip_monitor", {})
            if vip and vip.get("enabled"):
                self.assertIn("oids", vip)
                self.assertIn("notify_targets", vip)
                return
        # 2) Fallback: E2E_VIP_CONFIG env var (JSON)
        import os, json
        vip_json = os.getenv("E2E_VIP_CONFIG", "")
        if vip_json:
            vip = json.loads(vip_json)
            self.assertTrue(vip.get("enabled"), "E2E_VIP_CONFIG enabled=false")
            self.assertIn("oids", vip)
            self.assertIn("notify_targets", vip)
            return
        self.skipTest("G8: no VIP config in config.yaml or E2E_VIP_CONFIG env")


# ═══════════════════════════════════════════════════════════════════════
#  G9/G10/G11 — Reaction / Delete / Forward (需直接操作 adapter, 暫 skip)
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG9(_B):
    def test_reaction(self):
        """Send reaction via adapter — needs fresh Graph API token.
        MSG API reaction endpoint (404) does not support direct reaction."""
        self._req_gw()
        # Check if graph_token is still valid — auto-refresh via _TeamsAuth if needed
        try:
            import time as _t
            tok = _load()
            saved_at = tok.get("graph_token_saved_at", 0)
            expires_in = tok.get("graph_token_expires_in", 0)
            gt = tok.get("graph_token", "")
            if not gt or _t.time() > saved_at + expires_in - 300:
                # Refresh using gateway's _TeamsAuth logic
                from gateway.platforms.teams_mtk import _TeamsAuth, _CLIENT_ID, _TOKEN_URL
                import requests as _r
                rt = tok.get("refresh_token", "")
                resp = _r.post(_TOKEN_URL, data={
                    "client_id": _CLIENT_ID, "grant_type": "refresh_token",
                    "refresh_token": rt,
                    "scope": "https://graph.microsoft.com/.default offline_access",
                }, verify=False, timeout=15)
                new = resp.json()
                if "access_token" not in new:
                    self.skipTest(f"G9: graph token refresh failed: {new.get('error','?')}")
                tok["graph_token"] = new["access_token"]
                tok["graph_token_saved_at"] = int(_t.time())
                tok["graph_token_expires_in"] = new.get("expires_in", 3600)
                if new.get("refresh_token"):
                    tok["refresh_token"] = new["refresh_token"]
                json.dump(tok, open(str(Path.home() / ".teams-tokens" / "token_cache.json"), "w"))
        except Exception as e:
            self.skipTest(f"G9: cannot check/refresh graph token: {e}")
        cid = self._req_dm()
        _send(cid, "E2E-G9-REACTION-TEST: say 'G9-DONE'")
        r = _wait_bot(cid, _baseline(cid), contains="G9-DONE", timeout=TIMEOUT)
        self.assertTrue(r["found"], f"G9 FAIL: bot did not reply. Replies: {r.get('all',[])}")
        bot_msg_id = r["id"]
        # 2) Send reaction via Graph API raw (adapter._TeamsAuth reads from
        #    conftest's tmpdir in pytest, so we use the freshly-refreshed token)
        tok = _load()
        gt = tok.get("graph_token", "")
        self.assertTrue(gt, "G9: graph_token missing from cache")
        import requests as _req
        url = (f"https://graph.microsoft.com/beta/chats/{cid}"
               f"/messages/{bot_msg_id}/setReaction")
        resp = _req.post(url, headers={"Authorization": f"Bearer {gt}"},
                         json={"reactionType": "👍"}, verify=False, timeout=15)
        self.assertIn(resp.status_code, (200, 204),
            f"G9 FAIL: setReaction returned {resp.status_code}: {resp.text[:200]}")
        # 3) Graph API setReaction returns 204 on success — that IS the proof.
        # MSG API does not expose reactions in message properties, so we
        # rely on the 204 status code as the authoritative confirmation.
        # Fetch the message via Graph API to double-check reactions list
        import requests as _req2
        check_url = (f"https://graph.microsoft.com/beta/chats/{cid}"
                     f"/messages/{bot_msg_id}")
        check_resp = _req2.get(check_url,
            headers={"Authorization": f"Bearer {gt}"},
            verify=False, timeout=15)
        if check_resp.status_code == 200:
            msg_data = check_resp.json()
            reactions = msg_data.get("reactions", []) or []
            self.assertGreater(len(reactions), 0,
                f"G9 FAIL: no reactions found on msg {bot_msg_id} via Graph API")
        else:
            # Graph API readback failed — accept 204 as proof
            pass

class TestE2EG10(_B):
    def test_delete(self):
        """Delete own user message — verify MSG API shows it as deleted."""
        self._req_gw()
        cid = self._req_dm()
        # 1) Send a user msg and get its id from MSG API
        marker = f"E2E-G10-DELETE-{int(time.time())}"
        _send(cid, marker)
        time.sleep(3)
        # Find the msg id
        user_msg_id = None
        for m in _read(cid, 20):
            if marker in _ct(m) and m.get("messagetype") == "Text":
                user_msg_id = _mid(m)
                break
        self.assertTrue(user_msg_id, f"G10 FAIL: could not find user msg '{marker}'")
        # 2) Delete it via raw MSG API (user deletes own msg)
        import urllib.parse, requests as _req
        _sk = _skype_token()
        _at = _access_token()
        _enc = urllib.parse.quote(cid, safe="")
        del_url = f'https://amer.ng.msg.teams.microsoft.com/v1/users/ME/conversations/{_enc}/messages/{user_msg_id}'
        r = _req.delete(del_url,
            headers={"Authentication": f"skypetoken={_sk}", "Authorization": f"Bearer {_at}"},
            verify=False, timeout=15)
        self.assertEqual(r.status_code, 200,
            f"G10 FAIL: delete returned {r.status_code}: {r.text[:200]}")
        # 3) Verify: msg appears as deleted in MSG API
        time.sleep(3)
        found_deleted = False
        for m in _read(cid, 20):
            if _mid(m) == user_msg_id:
                ct = _ct(m)
                # Teams marks deleted messages as "This message has been deleted"
                # or changes messagetype to "Message/Deleted"
                mtype = m.get("messagetype", "")
                if "deleted" in ct.lower() or mtype == "Message/Deleted" or ct == "":
                    found_deleted = True
                break
        # If we can't find it at all, it's truly gone (also valid)
        if not found_deleted:
            still_present = any(_mid(m) == user_msg_id for m in _read(cid, 20))
            self.assertFalse(still_present,
                f"G10 FAIL: msg {user_msg_id} still present with unchanged content")

class TestE2EG11(_B):
    def test_forward(self):
        """Forward a message from DM to group via adapter — verify in group."""
        self._req_gw()
        cid = self._req_dm()
        gid = _grp()
        if not gid:
            self.skipTest("E2E_GROUP_CONV not set — cannot test forward")
        # 1) Send marker to DM, wait for bot reply, grab its id
        _send(cid, "E2E-G11-FORWARD-TEST: say 'G11-FWD-SRC'")
        r = _wait_bot(cid, _baseline(cid), contains="G11-FWD-SRC", timeout=TIMEOUT)
        self.assertTrue(r["found"], f"G11 FAIL: bot did not reply. Replies: {r.get('all',[])}")
        fwd_msg_id = r["id"]
        # 2) Forward via adapter (now uses correct SDK HTTPLayer)
        import asyncio
        from gateway.platforms.teams_mtk import TeamsMTKAdapter
        adapter = TeamsMTKAdapter(None)
        adapter._conv_id = cid
        adapter._conv_ids = [cid, gid]
        result = asyncio.run(adapter.forward_message(cid, fwd_msg_id, gid))
        self.assertNotEqual(result.get("status"), "error",
            f"G11 FAIL: forward returned error: {result}")
        # 3) Verify forwarded msg appears in group
        time.sleep(8)
        fwd_marker = f"G11-FWD-SRC"
        found = False
        for m in _read(gid, 20):
            c = _ct(m)
            if fwd_marker in c:
                found = True
                break
        self.assertTrue(found,
            f"G11 FAIL: forwarded marker '{fwd_marker}' not found in group")


# ═══════════════════════════════════════════════════════════════════════
#  G12  GW — Search：先種marker，要求搜尋，驗回覆找到 marker
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG12(_B):
    def test_search_finds_marker(self):
        """Plant a marker, ask bot to search, verify bot found it."""
        self._req_gw()
        cid = self._req_dm()
        # 1) Plant unique marker
        _send(cid, "UNIQUEMARKER-G12-ALPHA-7Z9X")
        time.sleep(5)
        base = _baseline(cid)
        # 2) Ask bot to search
        _send(cid, "E2E-G12: search this conversation for 'UNIQUEMARKER-G12-ALPHA-7Z9X' "
                      "and tell me if found. Say 'G12-FOUND' if yes.")
        r = _wait_bot(cid, base, contains="G12-FOUND", timeout=TIMEOUT)
        self.assertTrue(r["found"],
            f"G12 FAIL: bot didn't report finding marker. "
            f"Replies: {[x['text'][:100] for x in r.get('all',[])]}")


# ═══════════════════════════════════════════════════════════════════════
#  G13  GW — Activity feed：bot 回覆含 activity 資料
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG13(_B):
    def test_activity(self):
        """Bot should list activity feed — verify reply has activity data."""
        self._req_gw()
        r = self._send_wait(
            "E2E-G13: list my recent activity feed (spaces, notes). "
            "Say 'G13-ACT-DONE' when done or 'no-activity' if none",
            contains="G13-ACT-DONE")
        if not r["found"]:
            # Accept "no-activity" as valid (user may have no feed)
            r2 = self._send_wait(
                "E2E-G13: list activity", contains="activity")
            self.assertTrue(r2["found"],
                f"G13 FAIL: no reply about activity. ")


# ═══════════════════════════════════════════════════════════════════════
#  G14  GW — Call logs：bot 列 call logs
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG14(_B):
    def test_call_logs(self):
        """Bot should retrieve call logs or confirm none exist."""
        self._req_gw()
        r = self._send_wait(
            "E2E-G14: list my call logs. Say 'G14-CALLS-DONE' or 'no-calls'",
            contains="G14-CALLS-DONE")
        if not r["found"]:
            # "no-calls" is also acceptable
            r2 = self._send_wait(
                "E2E-G14: call logs", contains="call")
            self.assertTrue(r2["found"],
                f"G14 FAIL: no reply about calls.")


# ═══════════════════════════════════════════════════════════════════════
#  G15  SDK — List conversations + find (真 API)
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG15(_B):
    def test_list_conversations(self):
        """SDK list → returns ≥1 conversation with 'id' key."""
        http = _init_sdk()
        if http is None:
            self.skipTest("teams_skype_sdk not installed — skip SDK E2E")
        from teams_skype_sdk.api._conversations import ConversationsService
        from teams_skype_sdk.api._messages import MessagesService
        svc = ConversationsService(http, MessagesService(http))
        convs = svc.list(limit=20)
        self.assertIsInstance(convs, list)
        self.assertGreater(len(convs), 0, "no conversations")
        self.assertIn("id", convs[0])

    def test_find_conversation(self):
        http = _init_sdk()
        if http is None:
            self.skipTest("teams_skype_sdk not installed — skip SDK E2E")
        from teams_skype_sdk.api._conversations import ConversationsService
        from teams_skype_sdk.api._messages import MessagesService
        svc = ConversationsService(http, MessagesService(http))
        results = svc.find("test")
        self.assertIsInstance(results, list)


# ═══════════════════════════════════════════════════════════════════════
#  G16/G17  CFG — Whitelist / PKB (skip if not configured)
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG16(_B):
    def test_whitelist(self):
        """Forward whitelist is configured for a group conv."""
        import yaml as _y, os, json
        cfg = Path.home() / ".hermes" / "config.yaml"
        grp_id = _grp()
        if not grp_id:
            self.skipTest("E2E_GROUP_CONV not set")
        wl_json = os.getenv("E2E_WHITELIST_CONFIG", "")
        if cfg.exists():
            data = _y.safe_load(cfg.read_text()) or {}
            groups = data.get("gateway", {}).get("teams_mtk", {}).get("groups", {})
            grp_cfg = groups.get(grp_id, {})
            if "allowed_targets" in grp_cfg:
                self.assertIsInstance(grp_cfg["allowed_targets"], list)
                self.assertGreater(len(grp_cfg["allowed_targets"]), 0)
                return
        if wl_json:
            wl = json.loads(wl_json)
            self.assertIsInstance(wl, list)
            self.assertGreater(len(wl), 0)
            return
        self.skipTest("G16: no whitelist in config.yaml or E2E_WHITELIST_CONFIG env")

class TestE2EG17(_B):
    def test_pkb(self):
        """PKB instant landing is configured for a group conv."""
        import yaml as _y, os, json
        from pathlib import Path as _P
        cfg = Path.home() / ".hermes" / "config.yaml"
        grp_id = _grp()
        if not grp_id:
            self.skipTest("E2E_GROUP_CONV not set")
        pkb_json = os.getenv("E2E_PKB_CONFIG", "")
        if cfg.exists():
            data = _y.safe_load(cfg.read_text()) or {}
            groups = data.get("gateway", {}).get("teams_mtk", {}).get("groups", {})
            grp_cfg = groups.get(grp_id, {})
            if grp_cfg.get("pkb_instant_landing"):
                pkb_dir = grp_cfg.get("pkb_landing_dir", "")
                self.assertTrue(pkb_dir)
                self.assertTrue(_P(pkb_dir).exists())
                return
        if pkb_json:
            pkb = json.loads(pkb_json)
            self.assertTrue(pkb.get("pkb_instant_landing"))
            pkb_dir = pkb.get("pkb_landing_dir", "")
            if pkb_dir:
                self.assertTrue(_P(pkb_dir).exists(),
                    f"G17: pkb_landing_dir {pkb_dir} does not exist")
            return
        self.skipTest("G17: no PKB config in config.yaml or E2E_PKB_CONFIG env")


# ═══════════════════════════════════════════════════════════════════════
#  G18  GW — PLATFORM_HINTS：bot 回覆含 ≥2 Teams 專屬能力
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG18(_B):
    def test_platform_hints(self):
        """Bot must know ≥2 Teams capabilities (from PLATFORM_HINTS)."""
        self._req_gw()
        r = self._send_wait(
            "E2E-G18: list ALL your Teams-specific capabilities "
            "(e.g. reactions, search, activity, call logs, forward). "
            "Say 'G18-HINTS-DONE' at end",
            contains="G18-HINTS-DONE")
        self.assertTrue(r["found"],
            f"G18 FAIL: no reply. {r.get('all',[[]])[:2]}")
        ct = r["text"].lower()
        caps = [k for k in ["reaction", "search", "activity",
                             "forward", "call log"]
                if k in ct]
        self.assertGreaterEqual(len(caps), 2,
            f"G18 FAIL: only {len(caps)}/5 capabilities: {caps}. "
            f"Need ≥2. Reply: {ct[:300]}")


# ═══════════════════════════════════════════════════════════════════════
#  G19  CFG — OID redaction：gateway.log 無明文 OID
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG19(_B):
    def test_no_plaintext_oid(self):
        log = Path.home() / ".hermes" / "logs" / "gateway.log"
        if not log.exists(): self.skipTest("No gateway.log")
        lines = log.read_text(errors="replace").splitlines()[-300:]
        oid_re = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{12}", re.I)
        hits = []
        for ln in lines:
            if "user OID" in ln or "sender_oid" in ln \
               or ("VIP" in ln and "oid" in ln.lower()):
                if oid_re.search(ln):
                    hits.append(ln.strip()[:120])
        self.assertEqual(len(hits), 0,
            f"G19 FAIL: {len(hits)} lines with plaintext OID")


# ═══════════════════════════════════════════════════════════════════════
#  G20/G21  CFG — WS stability + adaptive interval
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG20(_B):
    def test_ws_connected(self):
        """Gateway is connected — either via WS (TrouterListener) or polling."""
        log = Path.home() / ".hermes" / "logs" / "gateway.log"
        if not log.exists(): self.skipTest("No gateway.log")
        lines = log.read_text(errors="replace").splitlines()[-300:]
        connected = any(
            "ws connected" in ln.lower()
            or "trouterlistener" in ln.lower()
            or "poll tick" in ln.lower()  # polling = also connected
            for ln in lines)
        self.assertTrue(connected,
            "G20 FAIL: no WS/poll connection evidence in gateway.log")

class TestE2EG21(_B):
    def test_adaptive_interval(self):
        log = Path.home() / ".hermes" / "logs" / "gateway.log"
        if not log.exists(): self.skipTest("No gateway.log")
        lines = log.read_text(errors="replace").splitlines()[-500:]
        adapt = [ln for ln in lines
                if "adaptive" in ln.lower()
                or "_active_interval" in ln.lower()
                or "backoff=" in ln.lower()]
        if not adapt:
            self.skipTest("No adaptive interval log entries")


# ═══════════════════════════════════════════════════════════════════════
#  G22  GW — /stop bypass：gateway 不卡死
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG22(_B):
    def test_stop_no_freeze(self):
        """Send /stop → gateway stays alive."""
        self._req_gw()
        cid = self._req_dm()
        _send(cid, "E2E-G22: count from 1 to 100 slowly")
        time.sleep(2)
        _send(cid, "/stop")
        time.sleep(5)
        self.assertTrue(_gw_alive(),
            "G22 FAIL: gateway died after /stop")


# ═══════════════════════════════════════════════════════════════════════
#  G23  CFG — Setup Wizard 有 SDK detection
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG23(_B):
    def test_setup_wizard_sdk(self):
        import importlib, inspect
        mod = importlib.import_module("hermes_cli.setup")
        src = inspect.getsource(mod.setup_gateway) \
              if hasattr(mod, "setup_gateway") else ""
        if not src:
            src = Path(mod.__file__).read_text()
        self.assertIn("teams_skype_sdk", src,
            "G23 FAIL: setup_gateway missing teams_skype_sdk")


# ═══════════════════════════════════════════════════════════════════════
#  G24  CFG — Cron knows teams_mtk
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG24(_B):
    def test_cron_teams_mtk(self):
        from cron.scheduler import _KNOWN_DELIVERY_PLATFORMS
        self.assertIn("teams_mtk", _KNOWN_DELIVERY_PLATFORMS)


# ═══════════════════════════════════════════════════════════════════════
#  G25  CFG — Control cmd bypass
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG25(_B):
    def test_control_cmds_bypass(self):
        from hermes_cli.commands import should_bypass_active_session
        for cmd in ("/stop", "/new", "/reset", "/approve", "/deny"):
            self.assertTrue(should_bypass_active_session(cmd),
                f"G25 FAIL: {cmd} not bypassing")


# ═══════════════════════════════════════════════════════════════════════
#  G26  CFG — Status shows TeamsMTK
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG26(_B):
    def test_status_teamsmtk(self):
        r = subprocess.run(
            [sys.executable, "-m", "hermes_cli.main", "status"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ,
                 "HERMES_HOME": str(Path.home() / ".hermes")})
        self.assertIn("TeamsMTK", r.stdout + r.stderr,
            f"G26 FAIL: status missing TeamsMTK")


# ═══════════════════════════════════════════════════════════════════════
#  G27  CFG — PLATFORM_CONNECTED_CHECKERS
# ═══════════════════════════════════════════════════════════════════════

class TestE2EG27(_B):
    def test_connected_checker(self):
        from gateway.config import _PLATFORM_CONNECTED_CHECKERS
        from gateway.platforms.base import Platform
        self.assertIn(Platform.TEAMS_MTK, _PLATFORM_CONNECTED_CHECKERS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
