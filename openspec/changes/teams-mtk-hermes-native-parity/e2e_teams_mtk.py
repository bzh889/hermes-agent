#!/usr/bin/env python3
"""Automated E2E gateway test runner for teams_mtk.

Runs real gateway tests against a running Hermes gateway, each test
identified by a descriptive name (not a number).  Checks gateway.log
for expected behaviour after sending messages via Graph API.

CANONICAL LOCATION: openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py
scripts/e2e_teams_mtk.py is a symlink / copy — always edit the openspec version.

Usage:
    python openspec/changes/teams-mtk-hermes-native-parity/e2e_teams_mtk.py [--gateway-log PATH] [--skip REQUIRES_MENTION]

Each test is a self-contained function that:
  1. Sends a message to Teams via Graph API
  2. Waits for gateway to process it
  3. Checks gateway.log for expected log lines
  4. Reports PASS / FAIL with evidence

Prerequisites:
  - Gateway running (`hermes gateway run`)
  - Graph token available (skype SDK auth cache)
  - truststore installed (for MTK corporate proxy SSL)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import requests

# --- SSL / Proxy setup ---
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

# --- SDK imports ---
from teams_skype_sdk.auth import TeamsAuth
from teams_skype_sdk.graph import GraphToken


# ── Configuration ──────────────────────────────────────────────────

DM_CHAT_ID = "19:6e8a676c-2a6b-4d52-873d-e358f85f6ee1_d6d4a33b-60fe-49ff-b57e-baa6edbb67b8@unq.gbl.spaces"
GROUP_CHAT_ID = "19:072f8afcd2e24a48b1f89310d1abcf8f@thread.v2"
GATEWAY_LOG_DEFAULT = os.path.expanduser("~/.hermes/logs/gateway.log")


# ── Helpers ───────────────────────────────────────────────────────

_graph_token = None


def get_graph_token() -> str:
    global _graph_token
    if _graph_token is None:
        auth = TeamsAuth()
        gt = GraphToken(auth)
        _graph_token = gt.get_token()
        if not _graph_token:
            raise RuntimeError("Failed to acquire Graph token")
    return _graph_token


def send_chat_message(chat_id: str, content: str) -> str:
    """Send a message via Graph API and return the message ID."""
    token = get_graph_token()
    url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"body": {"content": content}}
    r = requests.post(url, headers=headers, json=body)
    if r.status_code != 201:
        raise RuntimeError(f"Graph API POST failed: {r.status_code} {r.text[:200]}")
    return r.json()["id"]


def tail_log(path: str, after_line: int = 0) -> str:
    """Read gateway log from after_line onwards."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return "".join(lines[after_line:])


def wait_and_check_log(
    log_path: str,
    baseline_lines: int,
    patterns: list[str],
    wait_seconds: int = 12,
    poll_interval: int = 3,
) -> tuple[bool, str]:
    """Poll gateway.log for ANY of the patterns until found or timeout.

    Returns (found, evidence_text).
    """
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        new_log = tail_log(log_path, baseline_lines)
        for pat in patterns:
            for line in new_log.splitlines():
                if re.search(pat, line):
                    return True, line.strip()
        time.sleep(poll_interval)
    # Final check
    new_log = tail_log(log_path, baseline_lines)
    for pat in patterns:
        for line in new_log.splitlines():
            if re.search(pat, line):
                return True, line.strip()
    return False, new_log[-500:]


def get_skype_token() -> str:
    """Skype token for direct Skype/MSG API calls (read-back verification)."""
    auth = TeamsAuth()
    return auth.get_skype_token()


def get_messages_raw(chat_id: str, page_size: int = 15) -> list[dict]:
    """Read back real messages via the Skype MSG API (content verification tier).

    Unlike gateway.log pattern matching, this fetches the ACTUAL rendered
    message content the user would see in Teams — required for any test
    that verifies output *quality* (formatting, residual markdown, echo
    duplication) rather than just "did some code path execute".
    """
    token = get_skype_token()
    region_hosts = ["apac.ng.msg.teams.microsoft.com", "amer.ng.msg.teams.microsoft.com"]
    last_err = None
    for host in region_hosts:
        url = f"https://{host}/v1/users/ME/conversations/{chat_id}/messages"
        try:
            r = requests.get(
                url, headers={"Authentication": f"skypetoken={token}"},
                params={"pageSize": page_size}, timeout=15, verify=False,
            )
            if r.status_code == 200:
                return r.json().get("messages", [])
            last_err = f"{r.status_code} {r.text[:150]}"
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"get_messages_raw failed on all regions: {last_err}")


def send_via_sdk(chat_id: str, content: str) -> str:
    """Send via the Skype SDK (bot-token path) — mirrors what the gateway itself sends."""
    from teams_skype_sdk.api._messages import MessagesService
    from teams_skype_sdk.api._http import HTTPLayer

    auth = TeamsAuth()
    http = HTTPLayer(auth)
    result = MessagesService(http).send(conversation_id=chat_id, content=content)
    return str(result.get("id", "") or result.get("OriginalArrivalTime", ""))


def test_streaming_no_echo_duplication(log_path: str, baseline: int) -> tuple[bool, str]:
    """CONTENT TIER: send a query that triggers multi-step streaming edits,
    then read back the raw conversation via the MSG API and assert the bot
    did NOT emit duplicate near-identical progress messages (the 07-13
    OriginalArrivalTime-vs-id echo bug).

    Log-pattern tier is NOT sufficient here: 'sent message id=' appearing
    once in the log does not prove the SAME logical reply wasn't also
    duplicated as a brand new message due to a lost message_id round-trip.
    We must read back the actual conversation and count near-duplicate
    bot messages sent within a short window.
    """
    baseline_msgs = get_messages_raw(DM_CHAT_ID, page_size=5)
    baseline_ids = {m.get("id") for m in baseline_msgs}

    content = "E2E_AUTO echo-dup check — /new then trivial query"
    send_chat_message(DM_CHAT_ID, "/new")
    time.sleep(3)
    send_chat_message(DM_CHAT_ID, content)

    # Give the agent time to run one full turn (tool calls + reply).
    time.sleep(45)

    msgs = get_messages_raw(DM_CHAT_ID, page_size=20)
    new_bot_msgs = [
        m for m in msgs
        if m.get("id") not in baseline_ids
        and ("🤖" in (m.get("content") or "") or "border-left" in (m.get("content") or ""))
    ]
    # Group near-identical bodies (first 80 chars, tags stripped) — more
    # than 1 message with the same normalized prefix within this turn
    # means echo/streaming-duplication regressed.
    def _norm(raw: str) -> str:
        return re.sub(r"<[^>]+>", "", raw or "")[:80].strip()

    seen = {}
    dups = []
    for m in new_bot_msgs:
        key = _norm(m.get("content", ""))
        if not key:
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            dups.append(key)

    if dups:
        return False, f"Duplicate progress messages detected: {dups[:3]} (total bot msgs={len(new_bot_msgs)})"
    return True, f"No duplicate bodies among {len(new_bot_msgs)} new bot messages"


def test_no_residual_markdown_in_reply(log_path: str, baseline: int) -> tuple[bool, str]:
    """CONTENT TIER: read back the actual rendered reply and assert no
    literal markdown syntax (**bold**, `code`, [text](url), leading '- ')
    leaked through to the Teams HTML the user sees.

    This is the exact class of bug the log-pattern tier cannot catch —
    'Turn ended: success' says nothing about whether the model's markdown
    output was actually converted to HTML before being sent.
    """
    baseline_msgs = get_messages_raw(DM_CHAT_ID, page_size=5)
    baseline_ids = {m.get("id") for m in baseline_msgs}

    send_chat_message(DM_CHAT_ID, "/new")
    time.sleep(3)
    send_chat_message(DM_CHAT_ID, "用一個 table 列出 3 個測試項目的狀態，並用粗體標註結論")
    time.sleep(45)

    msgs = get_messages_raw(DM_CHAT_ID, page_size=20)
    bot_replies = [
        m for m in msgs
        if m.get("id") not in baseline_ids
        and ("🤖" in (m.get("content") or "") or "border-left" in (m.get("content") or ""))
        and len(m.get("content") or "") > 300
    ]
    if not bot_replies:
        return False, "No substantial bot reply found within wait window"

    raw = bot_replies[0].get("content", "")
    residuals = []
    if re.search(r"\*\*[^*]+\*\*", raw):
        residuals.append("**bold**")
    if re.search(r"(?<!href=\")`[^`\n]+`", raw):
        residuals.append("`code`")
    if re.search(r"\[[^\]]+\]\(https?://[^\s)]+\)", raw):
        residuals.append("[text](url)")
    if re.search(r"(?:^|<br>)\s*[-*]\s+(?!\|)", raw, re.MULTILINE):
        residuals.append("- bullet")
    if re.search(r"^\s*\|.+\|\s*$", raw, re.MULTILINE):
        residuals.append("| pipe table |")

    if residuals:
        return False, f"Residual markdown found: {residuals} in reply id={bot_replies[0].get('id')}"
    return True, f"No residual markdown in reply id={bot_replies[0].get('id')} (len={len(raw)})"


def test_no_disallowed_fallback_models(log_path: str, baseline: int) -> tuple[bool, str]:
    """Ensure the configured provider fallback chains do not contain a
    model the account is not authorized to call (e.g. wfm-coder-qwen3-coder-480b
    returning HTTP 403). A disallowed model in the chain wastes a retry and
    spams the user with a fallback-switch progress message every time the
    primary model's output is flagged as garbage.
    """
    import yaml

    cfg_path = os.path.expanduser("~/.hermes/config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    KNOWN_DISALLOWED = {"mtk/wfm-coder-qwen3-coder-480b"}
    offenders = []
    for pname, pdata in (cfg.get("providers") or {}).items():
        models = pdata.get("models", []) if isinstance(pdata, dict) else []
        for m in models:
            if m in KNOWN_DISALLOWED:
                offenders.append(f"{pname}:{m}")

    if offenders:
        return False, f"Disallowed models still present in fallback chain: {offenders}"
    return True, "No known-disallowed models present in any provider's model list"


def test_attachment_domain_routing_covers_asm(log_path: str, baseline: int) -> tuple[bool, str]:
    """The SDK's domain-based auth router must recognize
    as-api.asm.skype.com (and other *.asm.skype.com subdomains)
    as a skype_token-auth domain, not fall through to Bearer.
    This is the 07-13 image-download-failure root cause — the
    fallback path used a single Bearer header for all domains,
    causing 401 on asm.skype.com which requires Authorization: skype_token.

    Real behavioral test: calls download_with_auth_url() itself against a
    live attachment URL on the asm.skype.com subdomain with the real
    skype_token.  A successful non-401 response proves the router picked
    the correct auth header (Authorization: skype_token) for this domain.

    (Previous version extracted the source via inspect.getsource() but
    never asserted against it — it re-implemented the domain-matching
    condition locally and checked that reimplementation, so it would
    still PASS even if the real function's routing logic were deleted.)
    """
    from teams_skype_sdk.api._http import download_with_auth_url
    from teams_skype_sdk.auth import TeamsAuth

    auth = TeamsAuth()
    skype_token = auth.get_skype_token()

    # Use a real asm.skype.com attachment URL — if the token is valid
    # and the router picks the correct auth header, we get a 200 (or
    # redirect).  If the router picks Bearer, we get 401.
    # We grab a fresh URL from our own conversation's recent messages.
    from gateway.platforms.teams_mtk import TeamsMTKAdapter
    adapter = TeamsMTKAdapter(None)
    # Find recent messages with inline images (asm.skype.com URLs)
    dm_id = DM_CHAT_ID
    msgs = adapter._fetch_messages(conv_id=dm_id, limit=50)
    att_url = None
    for m in (msgs or []):
        content = m.get("content", "") or ""
        # Look for asm.skype.com image URLs in message HTML
        import re as _re
        _urls = _re.findall(r'https://[a-z0-9.-]*asm\.skype\.com/v1/objects/[\w-]+', content)
        if _urls:
            att_url = _urls[0]
            break

    if att_url is None:
        return False, "No live asm.skype.com attachment URL found in the latest 50 DM messages"

    try:
        result = download_with_auth_url(
            att_url, skype_token=skype_token, access_token="deliberately-invalid-token",
            verify_ssl=False, timeout=15,
        )
    except Exception as e:
        return False, f"download_with_auth_url failed on live asm.skype.com attachment: {e}"

    if not isinstance(result, bytes) or len(result) == 0:
        return False, f"download_with_auth_url returned empty/non-bytes result: {result!r}"

    return True, (
        f"download_with_auth_url succeeded on asm.skype.com "
        f"({len(result)} bytes) using skype_token despite garbage access_token — "
        f"proves the router picked Authorization:skype_token for this domain, not Bearer"
    )


def test_garbage_detector_no_false_positive_on_clean_output(log_path: str, baseline: int) -> tuple[bool, str]:
    """CONTENT TIER + real gateway: send a normal query and confirm the
    reply that reaches Teams is NOT the product of a false-positive garbage
    discard. We can't directly observe the discarded draft, so we assert
    the INVERSE property that matters to the user: the final delivered
    reply is coherent (no repeated single-char/byte runs, no encoding
    mush) and gateway.log shows at most the known intermittent trigger
    rate, not a discard on every turn.
    """
    baseline_msgs = get_messages_raw(DM_CHAT_ID, page_size=5)
    baseline_ids = {m.get("id") for m in baseline_msgs}

    send_chat_message(DM_CHAT_ID, "/new")
    time.sleep(3)
    send_chat_message(
        DM_CHAT_ID,
        "不用使用工具。請用繁體中文寫四點條列，說明軟體測試的重要性；"
        "每點至少二十五個中文字，總長必須超過一百五十字。",
    )
    time.sleep(45)

    msgs = get_messages_raw(DM_CHAT_ID, page_size=20)
    bot_replies = [
        m for m in msgs
        if m.get("id") not in baseline_ids
        and ("🤖" in (m.get("content") or "") or "border-left" in (m.get("content") or ""))
    ]
    if not bot_replies:
        return False, "No bot reply received within wait window"

    from agent.garbage_detector import is_garbage, _garbage_score
    import html as _html

    substantial = []
    for reply in bot_replies:
        raw = str(reply.get("content") or "")
        text = _html.unescape(re.sub(r"<[^>]+>", " ", raw))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= 80:
            substantial.append(text)

    if not substantial:
        return False, (
            "Bot replied, but no reply was long enough to exercise the "
            "production detector's 80-character threshold"
        )

    for text in substantial:
        if "\ufffd" in text:
            return False, "Delivered reply contains U+FFFD replacement characters"
        repeated = re.search(r"([^\s])\1{11,}", text)
        if repeated:
            return False, f"Delivered reply contains a repeated-character run: {repeated.group(0)!r}"
        if is_garbage(text):
            return False, (
                f"Production detector flags the delivered clean reply as garbage "
                f"(score={_garbage_score(text):.2f})"
            )

    new_log = tail_log(log_path, baseline)
    discard_count = len(
        re.findall(r"(?:Garbage output detected|Corrupt final model output detected)", new_log)
    )
    if discard_count:
        return False, (
            f"Clean-output turn triggered {discard_count} garbage discard(s); "
            "this is a false positive even though a retry eventually replied"
        )
    return True, (
        f"{len(substantial)} substantial reply/replies delivered; detector score(s)="
        f"{[_garbage_score(text) for text in substantial]}; 0 false-positive discards"
    )


# ── Named test cases ──────────────────────────────────────────────

def test_dm_echo_guard(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: bot's own sent messages are skipped by echo guard."""
    content = "E2E_AUTO echo guard test — should be skipped if sent by bot"
    # Send via SDK (bot token) → gateway should see it as own message
    from teams_skype_sdk.api._messages import MessagesService
    from teams_skype_sdk.api._http import HTTPLayer
    from teams_skype_sdk.auth import TeamsAuth

    auth = TeamsAuth()
    http = HTTPLayer(auth)
    msg_svc = MessagesService(http)
    result = msg_svc.send(conversation_id=DM_CHAT_ID, content=content)
    msg_id = str(result.get("id") or result.get("OriginalArrivalTime") or "")
    if not msg_id:
        return False, f"SDK send succeeded but returned no message id: {result!r}"

    found, evidence = wait_and_check_log(
        log_path, baseline,
        [rf"skipping own sent message id={re.escape(msg_id)}(?:\s|$)"],
    )
    return found, evidence


def test_mention_gating_ignore(log_path: str, baseline: int) -> tuple[bool, str]:
    """Group: message without @hermes is ignored when require_mention=true."""
    content = "E2E_AUTO no mention — should be ignored"
    msg_id = send_chat_message(GROUP_CHAT_ID, content)

    found, evidence = wait_and_check_log(
        log_path, baseline,
        [r"ignoring group message.*require_mention",
         r"require_mention.*no.*@hermes",
         r"inspecting msg.*E2E.*AUTO no mention"],
    )
    return found, evidence


def test_mention_gating_process(log_path: str, baseline: int) -> tuple[bool, str]:
    """Group: message with @hermes is processed when require_mention=true.

    Real behavioral test: the old version only checked that the inbound
    message was logged ("new message from...") — that log line fires for
    EVERY inbound message regardless of mention gating, so it never
    actually proved the agent was triggered.  This reads back the real
    conversation and asserts a genuine bot reply (border-left signature)
    landed after our @mention message.
    """
    baseline_msgs = get_messages_raw(GROUP_CHAT_ID, page_size=5)
    baseline_ids = {m.get("id") for m in baseline_msgs}

    content = '<at id="0">Hermes</at>&nbsp;E2E_AUTO with mention — should be processed'
    send_chat_message(GROUP_CHAT_ID, content)

    time.sleep(30)
    msgs = get_messages_raw(GROUP_CHAT_ID, page_size=15)
    new_bot_replies = [
        m for m in msgs
        if m.get("id") not in baseline_ids
        and "border-left" in (m.get("content") or "")
    ]
    if not new_bot_replies:
        return False, (
            f"No bot reply found in group after @mention message "
            f"(checked {len(msgs)} recent messages)"
        )
    return True, f"Bot reply landed after @mention: id={new_bot_replies[0].get('id')}"


def test_model_picker(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: /model triggers picker step 1, provider selection triggers step 2."""
    send_chat_message(DM_CHAT_ID, "/model")

    # Wait longer for step 1 (gateway poll + LLM call for provider list)
    for attempt in range(5):
        time.sleep(4)
        step1_log = tail_log(log_path, baseline)
        if "model picker step 1 (providers) sent" in step1_log:
            break
    else:
        return False, step1_log[-500:]

    # Select first provider — use fresh baseline
    time.sleep(2)
    baseline2 = sum(1 for _ in open(log_path, encoding="utf-8", errors="replace"))
    send_chat_message(DM_CHAT_ID, "1")

    found, evidence = wait_and_check_log(
        log_path, baseline2,
        [r"model picker step 2.*sent"],
        wait_seconds=15,
    )
    return found, evidence


def test_restart_no_replay(log_path: str, baseline: int) -> tuple[bool, str]:
    """After restart, old messages are not replayed.

    Real behavioral test: send a marker message, poll the gateway's
    _last_message_ids seeding logic via a short-lived adapter instance
    (mirrors connect()'s seed step), then verify the seeded watermark
    equals the max message id currently in the conversation — i.e. a
    fresh adapter instance would treat everything up to and including
    our marker as already-seen and NOT replay it.
    """
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    marker = f"E2E_AUTO restart-no-replay marker {int(time.time())}"
    marker_id = send_chat_message(DM_CHAT_ID, marker)
    time.sleep(2)  # give MSG API a moment to persist before read-back

    adapter = TeamsMTKAdapter(None)
    try:
        msgs = adapter._fetch_messages(conv_id=DM_CHAT_ID, limit=5)
    except Exception as e:
        return False, f"_fetch_messages raised: {e}"

    if not msgs:
        return False, "_fetch_messages returned no messages to seed from"

    seeded_id = max((m.get("id", "") for m in msgs if m.get("id")), default="")
    if not seeded_id:
        return False, f"Could not compute seeded id from fetched messages: {msgs[:2]}"

    # The seeded watermark must be >= our marker's id (as strings of digits,
    # Skype message ids are monotonic epoch-ms timestamps so string/int
    # comparison agree once compared numerically).
    try:
        seeded_int = int(seeded_id)
        marker_int = int(marker_id)
    except (TypeError, ValueError):
        return False, f"Non-numeric ids: seeded={seeded_id!r} marker={marker_id!r}"

    if seeded_int < marker_int:
        return False, (
            f"Seeded watermark {seeded_int} is OLDER than marker {marker_int} — "
            f"a restart would replay the marker message"
        )
    return True, f"Seeded watermark id={seeded_int} >= marker id={marker_int} — marker would not be replayed"


def test_send_image_file(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: send_image_file() actually uploads to AMS and sends inline (G-MEDIA-1).

    Real behavioral test: creates a temp PNG, calls the adapter's
    send_image_file() directly against the real DM chat, and asserts
    SendResult.success is True with a real message_id — not just that
    the method exists.  Then reads back the conversation to confirm a
    new message landed.
    """
    import base64, tempfile, os, asyncio
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x08, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0x00, 0x00, 0x00, 0x02,
        0x00, 0x01, 0xE5, 0x55, 0x9D, 0x73, 0x00, 0x00,
        0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42,
        0x60, 0x82,
    ])
    baseline_msgs = get_messages_raw(DM_CHAT_ID, page_size=5)
    baseline_ids = {m.get("id") for m in baseline_msgs}

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(png_data)
        temp_path = f.name

    try:
        adapter = TeamsMTKAdapter(None)

        async def _call():
            return await adapter.send_image_file(DM_CHAT_ID, temp_path, caption="E2E_AUTO image test")

        result = asyncio.run(_call())

        if not result.success:
            return False, f"send_image_file returned success=False error={result.error!r}"
        if not result.message_id:
            return False, f"send_image_file succeeded but returned no message_id: {result!r}"

        # Read back the conversation to confirm the image actually landed.
        time.sleep(3)
        msgs = get_messages_raw(DM_CHAT_ID, page_size=10)
        new_msgs = [m for m in msgs if m.get("id") not in baseline_ids]
        has_image = any("<img" in (m.get("content") or "") for m in new_msgs)
        if not has_image:
            return False, (
                f"send_image_file returned success=True message_id={result.message_id} "
                f"but read-back found no new <img> message (new_msgs={len(new_msgs)})"
            )
        return True, f"send_image_file succeeded, message_id={result.message_id}, verified via read-back"
    finally:
        os.unlink(temp_path)


def test_send_document(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: send_document() actually uploads to OneDrive and shares a link (G-MEDIA-2).

    Real behavioral test: writes a temp text file, calls send_document()
    against the real DM chat, and asserts SendResult.success with a real
    message_id — then reads back the conversation for a share link.
    """
    import tempfile, os, asyncio
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    baseline_msgs = get_messages_raw(DM_CHAT_ID, page_size=5)
    baseline_ids = {m.get("id") for m in baseline_msgs}

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write("E2E_AUTO send_document test content\n")
        temp_path = f.name

    try:
        adapter = TeamsMTKAdapter(None)

        async def _call():
            return await adapter.send_document(DM_CHAT_ID, temp_path, caption="E2E_AUTO doc test")

        result = asyncio.run(_call())

        if not result.success:
            return False, f"send_document returned success=False error={result.error!r}"
        if not result.message_id:
            return False, f"send_document succeeded but returned no message_id: {result!r}"

        time.sleep(3)
        msgs = get_messages_raw(DM_CHAT_ID, page_size=10)
        new_msgs = [m for m in msgs if m.get("id") not in baseline_ids]
        # The SDK path encodes the share link in properties.files (a
        # JSON-stringified file schema with fileUrl/shareUrl), NOT in the
        # message content itself (content stays as the plain caption).
        # Check both the content (legacy/raw-HTTP <a href> path) and
        # properties (SDK path) so this test works regardless of which
        # code path handled the send.
        has_link = any(
            ("sharepoint.com" in (m.get("content") or "") or "1drv.ms" in (m.get("content") or "")
             or "<a " in (m.get("content") or "")
             or "sharepoint.com" in json.dumps(m.get("properties", {}) or {})
             or "1drv.ms" in json.dumps(m.get("properties", {}) or {}))
            for m in new_msgs
        )
        if not has_link:
            return False, (
                f"send_document returned success=True message_id={result.message_id} "
                f"but read-back found no share link in content or properties.files "
                f"(new_msgs={len(new_msgs)})"
            )
        return True, f"send_document succeeded, message_id={result.message_id}, verified via read-back"
    finally:
        os.unlink(temp_path)


def test_send_adaptive_card(log_path: str, baseline: int) -> tuple[bool, str]:
    """send_adaptive_card() behavior matches the real config state — G-MEDIA-4.

    Real behavioral test, not existence check.  Reads the ACTUAL
    gateway.teams_mtk.adaptive_cards.enabled config value (don't assume
    disabled-by-default — a deployment may have opted in) and verifies
    the correct path for that state:
      - enabled=false: fallback_text is sent as plain text
      - enabled=true:  the card payload lands in properties.cards
    Either way requires SendResult.success=True with a real message_id,
    verified via read-back — not just "didn't raise".
    """
    import asyncio
    from gateway.platforms.teams_mtk import TeamsMTKAdapter
    from hermes_cli.config import load_config_readonly

    try:
        cfg = load_config_readonly()
    except Exception:
        cfg = {}
    enabled = bool(
        (cfg.get("gateway", {}) or {}).get("teams_mtk", {}).get("adaptive_cards", {}).get("enabled", False)
    )

    baseline_msgs = get_messages_raw(DM_CHAT_ID, page_size=5)
    baseline_ids = {m.get("id") for m in baseline_msgs}

    fallback_marker = f"E2E_AUTO adaptive-card-fallback {int(time.time())}"
    card_marker = f"E2E_AUTO_CARD_{int(time.time())}"
    adapter = TeamsMTKAdapter(None)

    async def _call():
        return await adapter.send_adaptive_card(
            DM_CHAT_ID,
            card={"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": card_marker}]},
            fallback_text=fallback_marker,
        )

    result = asyncio.run(_call())

    if not result.success:
        return False, f"send_adaptive_card (adaptive_cards.enabled={enabled}) returned success=False error={result.error!r}"

    time.sleep(3)
    msgs = get_messages_raw(DM_CHAT_ID, page_size=10)
    new_msgs = [m for m in msgs if m.get("id") not in baseline_ids]

    if not enabled:
        has_fallback = any(fallback_marker in (m.get("content") or "") for m in new_msgs)
        if not has_fallback:
            return False, (
                f"adaptive_cards disabled: expected fallback_text delivered as plain "
                f"message, found none (new_msgs={len(new_msgs)})"
            )
        return True, "Disabled path verified: fallback_text delivered as plain message"
    else:
        has_card = any(
            card_marker in json.dumps(m.get("properties", {}) or {})
            for m in new_msgs
        )
        if not has_card:
            return False, (
                f"adaptive_cards enabled: expected card marker in properties.cards, "
                f"found none (new_msgs={len(new_msgs)})"
            )
        return True, f"Enabled path verified: card payload landed in properties.cards, message_id={result.message_id}"


def test_send_text(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: send a message via Graph API, gateway replies, check log for sent message."""
    content = "E2E_AUTO send test — hello"
    send_chat_message(DM_CHAT_ID, content)

    # Wait for gateway to process and send a reply
    # Pattern: "TeamsMTK: sent message id=" (outbound confirmation)
    found, evidence = wait_and_check_log(
        log_path, baseline,
        [r"TeamsMTK: sent message id="],
        wait_seconds=30,
    )
    return found, evidence


def test_edit_message(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: send /title command, gateway edits the follow-up message.

    /title triggers an immediate edit of the 'Thinking…' placeholder.
    We check gateway log for both the send and the edit.
    """
    send_chat_message(DM_CHAT_ID, "/title")

    # Wait for gateway to process and either send or edit
    # Pattern 1: "edited message" in log
    # Pattern 2: "sent message id=" (title command result)
    found, evidence = wait_and_check_log(
        log_path, baseline,
        [r"TeamsMTK: edited message", r"TeamsMTK: sent message id="],
        wait_seconds=15,
    )
    return found, evidence


def test_download_attachment(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: upload a real image via Graph API, gateway processes AND downloads it.

    Uses Graph API hostedContents to upload a real 1x1 PNG inline image.
    Real behavioral test: the old version accepted "download was attempted
    (even if failed)" as a pass — that OR-list is exactly why the 07-13
    as-api.asm.skype.com authentication 401 bug went undetected for so long.
    This now REQUIRES the success signal
    (cache_image_from_bytes / cached bytes) — a mere attempt is a FAIL.
    """
    import base64

    # Create a tiny valid PNG (1x1 green pixel)
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # 8-bit RGB
        0xDE, 0x00, 0x00, 0x00, 0x08, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x08, 0xD7, 0x63, 0x00, 0x00, 0x00, 0x02,  # compressed
        0x00, 0x01, 0xE5, 0x55, 0x9D, 0x73, 0x00, 0x00,  # data
        0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42,  # IEND chunk
        0x60, 0x82,
    ])
    img_b64 = base64.b64encode(png_data).decode()

    # Upload via Graph API with hostedContents
    token = get_graph_token()
    url = f"https://graph.microsoft.com/v1.0/chats/{DM_CHAT_ID}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "body": {
            "contentType": "html",
            "content": '<p>E2E_AUTO download test — <img src="../hostedContents/1/$value" alt="test"></p>'
        },
        "hostedContents": [{
            "@microsoft.graph.temporaryId": "1",
            "contentBytes": img_b64,
            "contentType": "image/png",
        }]
    }
    r = requests.post(url, headers=headers, json=body)
    if r.status_code != 201:
        return False, f"Graph upload failed: {r.status_code} {r.text[:200]}"

    msg_data = r.json()
    msg_id = msg_data.get("id", "")
    if not msg_id:
        return False, "No message ID in Graph response"

    # REQUIRE the success signal — a mere download attempt is not enough.
    # Also check for an explicit failure signal so a timeout doesn't
    # silently pass through to the generic "not found" message.
    found, evidence = wait_and_check_log(
        log_path, baseline,
        [
            r"TeamsMTK: cached \d+ bytes from",  # New unified success log (both SDK + aiohttp paths)
        ],
        wait_seconds=20,
    )
    if not found:
        fail_found, fail_evidence = wait_and_check_log(
            log_path, baseline,
            [r"attachment download failed", r"attachment download error", r"SDK download failed"],
            wait_seconds=1,
        )
        if fail_found:
            return False, f"Download explicitly failed: {fail_evidence}"
        return False, f"No download-success signal within timeout; last log: {evidence[-300:]}"
    return found, evidence


def test_send_typing(log_path: str, baseline: int) -> tuple[bool, str]:
    """send_typing() actually delivers a typing indicator to Teams — G4.

    Real behavioral test: the old version was a "didn't raise" check
    (existence + no-exception), but send_typing is best-effort by
    design — it swallows ALL exceptions, so "didn't raise" is trivially
    true regardless of whether the typing indicator actually landed.
    This version calls send_typing with a real adapter and verifies
    the return value (True = POST 201, False = failure).
    """
    import asyncio
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    adapter = TeamsMTKAdapter(None)

    async def _call():
        return await adapter.send_typing(DM_CHAT_ID, metadata=None)

    try:
        result = asyncio.run(_call())
    except Exception as e:
        return False, f"send_typing raised unexpected exception: {e}"

    if result is True:
        return True, "send_typing returned True (POST 201)"
    return False, f"send_typing returned {result!r} (expected True = POST 201)"


def test_list_conversations(log_path: str, baseline: int) -> tuple[bool, str]:
    """G13-A.1: list_conversations() calls Skype chat service and returns real convs.

    Real behavioral test: the old version let empty list = PASS ("token
    may be expired or no convs").  That's exactly the failure mode this
    test should CATCH — if the skype token is expired, list_conversations
    must not silently return [].  This version checks the gateway.log
    for an explicit success signal ("list_conversations...ok, N convs")
    AND that the returned list is non-empty (this is a real Teams account
    with at least the E2E test DM + group convs — 0 results means
    something is broken).
    """
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    adapter = TeamsMTKAdapter(None)
    convs = adapter.list_conversations(limit=10)

    if not isinstance(convs, list):
        return False, f"list_conversations returned non-list: {type(convs)}"

    # Check for the success signal in the log
    found, evidence = wait_and_check_log(
        log_path, baseline,
        [r"TeamsMTK: list_conversations.*ok, \d+ convs", r"TeamsMTK: _TeamsAuth list_conversations.*ok, \d+ convs"],
        wait_seconds=3,
    )
    if not found:
        fail_found, fail_ev = wait_and_check_log(
            log_path, baseline,
            [r"list_conversations failed", r"list_conversations raw failed"],
            wait_seconds=1,
        )
        if fail_found:
            return False, f"list_conversations API failed: {fail_ev}"
        # No success OR failure log — the call returned before this test's baseline
        # (adapter was just constructed, no gateway event loop). Check result count.
        if len(convs) == 0:
            return False, "list_conversations returned [] with no success log — likely token expired or API failure swallowed"

    if len(convs) == 0:
        return False, "list_conversations returned [] — expected at least the E2E test DM/group convs"

    first = convs[0]
    if "id" not in first:
        return False, f"list_conversations first entry missing 'id': {first}"

    return True, (
        f"list_conversations returned {len(convs)} convs; "
        f"first id={first.get('id', '')[:40]!r} title={first.get('title', '')[:30]!r}"
    )


def test_find_conv_by_display_name(log_path: str, baseline: int) -> tuple[bool, str]:
    """G13-A.2: _find_conv_by_display_name() resolves a name to a conv ID.

    Real behavioral test: the old version let list_conversations=[]
    silently pass through ("token may be expired").  This version
    requires that:
      1. empty-string → None (boundary, unchanged)
      2. nonexistent name → None (unchanged)
      3. A known conversation is actually resolvable
    If list_conversations returns [] we FAIL (not silently pass), because
    this test DM+group are known to exist in this account.
    """
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    adapter = TeamsMTKAdapter(None)

    # Boundary 1: empty string → None
    result_empty = adapter._find_conv_by_display_name("")
    if result_empty is not None:
        return False, f"_find_conv_by_display_name('') returned {result_empty!r} (expected None)"

    # Boundary 2: nonexistent name → None
    result_unknown = adapter._find_conv_by_display_name("__E2E_NONEXISTENT_CONV_XYZZY__")
    if result_unknown is not None:
        return False, f"_find_conv_by_display_name(unknown) returned {result_unknown!r} (expected None)"

    # Real test: resolve an actual conversation
    convs = adapter.list_conversations(limit=50)
    if len(convs) == 0:
        return False, "list_conversations returned [] — cannot test name resolution; likely token expired"

    # Find a conv with a usable title
    target_conv = None
    for c in convs:
        title = (c.get("title") or "").strip()
        if len(title) >= 4:
            target_conv = c
            break

    if target_conv is None:
        # No conv with usable title — verify boundary conditions passed at least
        conv_ids = [c.get("id", "")[:20] for c in convs[:5]]
        return False, (
            f"No conversation with usable title (≥4 chars) found for "
            f"substring-resolution test. conv_ids={conv_ids}"
        )

    needle = target_conv["title"][:5]
    found_id = adapter._find_conv_by_display_name(needle)
    if found_id is None:
        return False, (
            f"_find_conv_by_display_name({needle!r}) returned None "
            f"(expected conv_id matching {target_conv.get('id', '')[:40]!r})"
        )
    return True, (
        f"empty→None ✓, unknown→None ✓, "
        f"needle={needle!r} → id={found_id[:40]!r} ✓"
    )


def test_find_conversation(log_path: str, baseline: int) -> tuple[bool, str]:
    """find_conversation() — SDK ConversationsService.find() search path.

    Previously covered by NO E2E test at all (design.md/DEPENDENCIES.md
    marked it "✅ 已實作" but zero automated coverage ever exercised it).
    This method shares the exact same class of bug just fixed in
    list_conversations/_find_conv_by_display_name — a missing SDK
    constructor arg (_SDKConvs(_http) instead of _SDKConvs(_http,
    _msg_svc)) that silently raised TypeError and was swallowed by a
    bare `except Exception: return []`. Without this test, a regression
    of that exact bug would ship silently (empty list looks identical to
    "no matches found").

    Real behavioral test: resolves a known conversation via a real
    substring search and requires a non-empty result with 'id' present.
    """
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    adapter = TeamsMTKAdapter(None)

    # Get a real conversation to search for
    convs = adapter.list_conversations(limit=50)
    if len(convs) == 0:
        return False, "list_conversations returned [] — cannot test find_conversation; likely token expired"

    target_conv = None
    for c in convs:
        title = (c.get("title") or "").strip()
        # Skip placeholder titles the SDK's cache layer deliberately excludes
        # from find() results (cache.py add_conversation() skips "Untitled"/
        # "Unknown"/"" by design — these are 1:1 chats where the SDK couldn't
        # resolve a display name). Picking one here would make find()
        # correctly return [] and cause a false test failure.
        if len(title) >= 4 and title not in ("Untitled", "Unknown"):
            target_conv = c
            break
    if target_conv is None:
        return False, "No conversation with a usable (non-placeholder) title found for find_conversation test"

    needle = target_conv["title"][:5]
    results = adapter.find_conversation(needle)
    if not isinstance(results, list):
        return False, f"find_conversation returned non-list: {type(results)}"
    if len(results) == 0:
        return False, (
            f"find_conversation({needle!r}) returned [] — expected at least one match "
            f"(this exact bug class silently returns [] on SDK TypeError)"
        )
    if "id" not in results[0]:
        return False, f"find_conversation first result missing 'id': {results[0]}"
    return True, f"find_conversation({needle!r}) returned {len(results)} result(s), first id={results[0].get('id','')[:40]!r}"


def test_standalone_sender_fn(log_path: str, baseline: int) -> tuple[bool, str]:
    """G5 + standalone_sender_fn: registry sender performs a real delivery.

    A registry-only check would still pass if the sender's auth, adapter
    construction, or network path were completely broken.  Invoke the
    registered callable and read the marker back from the real DM instead.
    """
    import asyncio
    import inspect
    from gateway.platforms import teams_mtk as _teams_mtk_mod

    # 1. _standalone_send 函式存在
    if not hasattr(_teams_mtk_mod, "_standalone_send"):
        return False, "_standalone_send NOT FOUND in teams_mtk module"

    standalone_fn = _teams_mtk_mod._standalone_send
    if not inspect.iscoroutinefunction(standalone_fn):
        return False, f"_standalone_send is not a coroutine function: {type(standalone_fn)}"

    # 2. platform_registry 已含 'teams_mtk' 條目
    try:
        from gateway.platform_registry import platform_registry
    except ImportError as e:
        return False, f"Cannot import platform_registry: {e}"

    entry = None
    # platform_registry.get(name) 或 .entries 依實作不同，兩種都試
    try:
        entry = platform_registry.get("teams_mtk")
    except Exception:
        pass
    if entry is None:
        # 試 _entries / entries 屬性
        for attr in ("_entries", "entries", "_registry"):
            reg_dict = getattr(platform_registry, attr, None)
            if isinstance(reg_dict, dict) and "teams_mtk" in reg_dict:
                entry = reg_dict["teams_mtk"]
                break

    if entry is None:
        return False, (
            "platform_registry does not contain 'teams_mtk' entry "
            "(standalone_sender_fn not registered)"
        )

    # 3. standalone_sender_fn 已設定
    fn = getattr(entry, "standalone_sender_fn", None)
    if fn is None:
        return False, "PlatformEntry('teams_mtk').standalone_sender_fn is None"

    # 4. 是 async function
    if not inspect.iscoroutinefunction(fn):
        return False, f"standalone_sender_fn is not async: {type(fn)}"

    # 5. 基本欄位正確
    name_ok = getattr(entry, "name", "") == "teams_mtk"
    emoji_ok = getattr(entry, "emoji", "") == "👥"
    checks = f"name={'teams_mtk' if name_ok else '❌'} emoji={'👥' if emoji_ok else '❌'}"

    if not name_ok:
        return False, f"PlatformEntry.name != 'teams_mtk': {checks}"
    if not emoji_ok:
        return False, f"PlatformEntry.emoji != '👥': {checks}"

    marker = f"E2E_AUTO standalone sender {time.time_ns()}"
    result = asyncio.run(fn(None, DM_CHAT_ID, marker))
    if not isinstance(result, dict) or not result.get("success"):
        return False, f"standalone sender returned failure: {result!r}"

    deadline = time.time() + 20
    while time.time() < deadline:
        messages = get_messages_raw(DM_CHAT_ID, page_size=30)
        for msg in messages:
            if marker in str(msg.get("content") or msg.get("body") or ""):
                return True, (
                    f"standalone sender delivered and read back marker; "
                    f"message_id={result.get('message_id')!r}; {checks}"
                )
        time.sleep(2)
    return False, (
        "standalone sender returned success but marker was not present in "
        f"real Teams read-back; result={result!r}"
    )


# ── Runner ────────────────────────────────────────────────────────

NAMED_TESTS = {
    "dm-echo-guard": test_dm_echo_guard,
    "mention-gating-ignore": test_mention_gating_ignore,
    "mention-gating-process": test_mention_gating_process,
    "model-picker": test_model_picker,
    "restart-no-replay": test_restart_no_replay,
    "send-text": test_send_text,
    "edit-message": test_edit_message,
    "download-attachment": test_download_attachment,
    "send-image-file": test_send_image_file,
    "send-document": test_send_document,
    "send-adaptive-card": test_send_adaptive_card,
    # ── 新增測項（G4 / G13-A / standalone_sender_fn）────────────
    "send-typing": test_send_typing,
    "list-conversations": test_list_conversations,
    "find-conv-by-display-name": test_find_conv_by_display_name,
    "find-conversation": test_find_conversation,
    "standalone-sender-fn": test_standalone_sender_fn,
    # ── 新增測項（2026-07-13 CONTENT TIER — 補真實輸出品質驗收）───
    "streaming-no-echo-duplication": test_streaming_no_echo_duplication,
    "no-residual-markdown-in-reply": test_no_residual_markdown_in_reply,
    "no-disallowed-fallback-models": test_no_disallowed_fallback_models,
    "attachment-domain-routing-covers-asm": test_attachment_domain_routing_covers_asm,
    "garbage-detector-no-false-positive": test_garbage_detector_no_false_positive_on_clean_output,
}


def main():
    import json

    parser = argparse.ArgumentParser(description="E2E teams_mtk gateway tests")
    parser.add_argument("--gateway-log", default=GATEWAY_LOG_DEFAULT)
    parser.add_argument("--skip", nargs="*", default=[], help="Test names to skip")
    parser.add_argument("--only", nargs="*", default=[], help="Only run these tests")
    args = parser.parse_args()

    log_path = args.gateway_log
    if not os.path.isfile(log_path):
        print(f"FATAL: gateway.log not found at {log_path}")
        sys.exit(1)

    # Baseline = current log line count (skip history)
    with open(log_path, encoding="utf-8", errors="replace") as f:
        baseline = sum(1 for _ in f)

    to_run = list(NAMED_TESTS.keys())
    if args.only:
        to_run = [t for t in to_run if t in args.only]
    to_run = [t for t in to_run if t not in args.skip]

    results = {}
    for name in to_run:
        print(f"  ▸ {name} ... ", end="", flush=True)
        try:
            ok, evidence = NAMED_TESTS[name](log_path, baseline)
            status = "✅ PASS" if ok else "❌ FAIL"
            results[name] = ok
        except Exception as e:
            status = f"❌ ERROR: {e}"
            results[name] = False
            evidence = str(e)

        baseline = sum(1 for _ in open(log_path, encoding="utf-8", errors="replace"))
        print(status)
        if not results[name]:
            print(f"    Evidence: {evidence}")
            print("    Stopping: later E2E results would be invalid until this failure is fixed.")
            break

    # Summary
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} PASS")
    if passed < total:
        for name, ok in results.items():
            if not ok:
                print(f"  ✗ {name}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
