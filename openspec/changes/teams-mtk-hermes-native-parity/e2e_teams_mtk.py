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
import asyncio
from collections import Counter
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import uuid

import requests
from bs4 import BeautifulSoup

# --- SSL / Proxy setup ---
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

# --- SDK imports ---
from teams_skype_sdk.api._http import strip_teams_html
from teams_skype_sdk.graph import GraphToken

# Gateway log now redacts message/conv IDs through _log_ref() (sha256:<12hex>)
# for privacy. Log-pattern assertions must match on the SAME redacted form,
# not the plaintext ID, or they never match and produce false FAILs.
from gateway.platforms.teams_mtk import (
    _SDKAuthAdapter,
    _SDKHTTPLayer,
    _TeamsAuth,
    _clean_message_content,
    _log_ref,
)


# ── Configuration ──────────────────────────────────────────────────

DM_CHAT_ID = ""
GROUP_CHAT_ID = ""
GATEWAY_LOG_DEFAULT = os.path.expanduser("~/.hermes/logs/gateway.log")


def _load_configured_chat_ids() -> None:
    """Resolve E2E targets from the active profile without storing IDs here."""
    from hermes_cli.config import get_env_value

    configured = [
        value.strip()
        for value in (get_env_value("MTK_TEAMS_CONVERSATION_ID") or "").split(",")
        if value.strip()
    ]
    # Match TeamsMTKAdapter's runtime chat classification. The legacy
    # no-mention list is not a chat-type registry: per-group config can
    # override it, so using it here can silently swap the two E2E targets.
    dm_candidates = [chat_id for chat_id in configured if "@thread" not in chat_id]
    group_candidates = [chat_id for chat_id in configured if "@thread" in chat_id]
    if not dm_candidates or not group_candidates:
        raise RuntimeError(
            "E2E requires one configured non-thread chat and one @thread group "
            "in MTK_TEAMS_CONVERSATION_ID "
            f"(configured={len(configured)}, dm={len(dm_candidates)}, "
            f"group={len(group_candidates)})"
        )

    global DM_CHAT_ID, GROUP_CHAT_ID
    DM_CHAT_ID = dm_candidates[0]
    GROUP_CHAT_ID = group_candidates[0]


# ── Helpers ───────────────────────────────────────────────────────

_gateway_auth = None
_graph_token = None
_graph_token_manager = None
_readback_http_layer = None


def _get_gateway_auth():
    """Share the gateway's atomic token cache implementation across E2E I/O."""
    global _gateway_auth
    if _gateway_auth is None:
        _gateway_auth = _TeamsAuth()
    return _gateway_auth


def get_graph_token(*, force_refresh: bool = False) -> str:
    global _graph_token, _graph_token_manager
    if _graph_token_manager is None:
        _graph_token_manager = GraphToken(_get_gateway_auth())
    _graph_token = (
        _graph_token_manager.refresh()
        if force_refresh
        else _graph_token_manager.get_token()
    )
    if not _graph_token:
        raise RuntimeError("Failed to acquire Graph token")
    return _graph_token


def send_chat_message(chat_id: str, content: str) -> str:
    """Send a message via Graph API and return the message ID."""
    url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
    body = {"body": {"content": content}}
    for attempt in range(2):
        token = get_graph_token(force_refresh=attempt == 1)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        r = requests.post(url, headers=headers, json=body)
        if r.status_code != 401:
            break
    if r.status_code != 201:
        raise RuntimeError(
            f"Graph API POST failed: status={r.status_code}, "
            f"body_length={len(r.text or '')}"
        )
    return r.json()["id"]


def delete_graph_message(chat_id: str, message_id: str) -> None:
    """Delete a controlled Graph-user E2E message."""
    url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages/{message_id}"
    for attempt in range(2):
        token = get_graph_token(force_refresh=attempt == 1)
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.delete(url, headers=headers)
        if response.status_code != 401:
            break
    if response.status_code not in (204, 404):
        raise RuntimeError(
            f"Graph API DELETE failed: status={response.status_code}, "
            f"body_length={len(response.text or '')}"
        )


def tail_log(path: str, after_line: int = 0) -> str:
    """Read gateway log after a line baseline, including after rollover."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    if after_line > len(lines):
        after_line = 0
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
    return _get_gateway_auth().skype_token()


def _close_sdk_http_layer(http_layer) -> None:
    session = getattr(http_layer, "_session", None)
    if session is not None:
        try:
            session.close()
        except Exception:
            pass


def _get_readback_http_layer(auth):
    global _readback_http_layer
    if _readback_http_layer is None:
        _readback_http_layer = _SDKHTTPLayer(
            _SDKAuthAdapter(auth), verify_ssl=True
        )
    return _readback_http_layer


def _discard_readback_http_layer(http_layer) -> None:
    global _readback_http_layer
    if _readback_http_layer is http_layer:
        _readback_http_layer = None
    _close_sdk_http_layer(http_layer)


def get_messages_raw(chat_id: str, page_size: int = 15) -> list[dict]:
    """Read back real messages via the Skype MSG API (content verification tier).

    Unlike gateway.log pattern matching, this fetches the ACTUAL rendered
    message content the user would see in Teams — required for any test
    that verifies output *quality* (formatting, residual markdown, echo
    duplication) rather than just "did some code path execute". Successful
    requests retain one shared SDK transport just like the gateway poll loop;
    a failed corporate-proxy TLS pool is discarded before the next retry.
    """
    from teams_skype_sdk.api._messages import MessagesService

    auth = _get_gateway_auth()
    auth._inject_truststore()
    last_error = "unknown"
    attempts = 4
    for attempt in range(attempts):
        http_layer = None
        try:
            http_layer = _get_readback_http_layer(auth)
            return MessagesService(http_layer).get_page(
                chat_id,
                page_size=page_size,
                msg_base=auth.msg_base,
            )
        except Exception as exc:
            # Do not leak the full exception: requests errors include the URL,
            # whose path embeds the private conversation ID.
            last_error = type(exc).__name__
            _discard_readback_http_layer(http_layer)
        if attempt + 1 < attempts:
            time.sleep(min(2**attempt, 4))
    raise RuntimeError(
        f"get_messages_raw failed after {attempts} attempts ({last_error})"
    )


def get_message_raw_exact(chat_id: str, message_id: str) -> dict:
    """Read one exact raw MSG resource without logging private identities."""
    auth = _get_gateway_auth()
    auth._inject_truststore()
    encoded_chat = urllib.parse.quote(chat_id, safe="")
    encoded_message = urllib.parse.quote(str(message_id), safe="")
    url = (
        f"{auth.msg_base}/conversations/{encoded_chat}"
        f"/messages/{encoded_message}"
    )
    last_error = "unknown"
    for attempt in range(4):
        http_layer = None
        try:
            http_layer = _get_readback_http_layer(auth)
            raw_message = http_layer._request("GET", url).json()
            if (
                isinstance(raw_message, dict)
                and str(raw_message.get("id") or "") == str(message_id)
            ):
                return raw_message
            last_error = "identity-mismatch"
        except Exception as exc:
            last_error = type(exc).__name__
            _discard_readback_http_layer(http_layer)
        if attempt + 1 < 4:
            time.sleep(min(2**attempt, 4))
    raise RuntimeError(
        f"get_message_raw_exact failed after 4 attempts ({last_error})"
    )


def _reaction_user_count(chat_id: str, message_id: str, reaction: str) -> int:
    """Return only the count from exact raw reaction state, never identities."""
    message = get_message_raw_exact(chat_id, message_id)
    properties = _raw_message_properties(message)
    for emotion in properties.get("emotions") or []:
        if isinstance(emotion, dict) and emotion.get("key") == reaction:
            users = emotion.get("users") or []
            return len(users) if isinstance(users, list) else 0
    return 0


def _exact_tombstone_state(
    chat_id: str,
    message_id: str,
) -> tuple[bool, int, bool]:
    """Read exact delete state without returning source content or identity."""
    try:
        message = get_message_raw_exact(chat_id, message_id)
    except RuntimeError:
        return False, 0, False
    properties = _raw_message_properties(message)
    return (
        True,
        len(str(message.get("content") or "")),
        bool(properties.get("deletetime")),
    )


def _exact_message_has_html_tag(
    chat_id: str,
    message_id: str,
    tag: str,
) -> bool:
    """Verify one structural HTML tag from exact raw content."""
    message = get_message_raw_exact(chat_id, message_id)
    content = str(message.get("content") or "")
    return BeautifulSoup(content, "html.parser").find(tag.lower()) is not None


def _raw_message_properties(message: dict) -> dict:
    properties = message.get("properties") or {}
    if isinstance(properties, str):
        properties = json.loads(properties)
    return properties if isinstance(properties, dict) else {}


def _native_reply_relation_ids(message: dict) -> set[str]:
    """Extract only structural reply-target identities from canonical read-back."""
    properties = _raw_message_properties(message)
    relation_ids = {
        str(properties.get("replyChainMessageId") or ""),
    }

    quoted_messages = properties.get("qtdMsgs") or []
    if isinstance(quoted_messages, str):
        try:
            quoted_messages = json.loads(quoted_messages)
        except (json.JSONDecodeError, TypeError):
            quoted_messages = []
    if isinstance(quoted_messages, list):
        relation_ids.update(
            str(item.get("messageId") or item.get("id") or "")
            for item in quoted_messages
            if isinstance(item, dict)
        )

    soup = BeautifulSoup(str(message.get("content") or ""), "html.parser")
    reply_quote = soup.find(
        "blockquote",
        attrs={"itemtype": "http://schema.skype.com/Reply"},
    )
    if reply_quote is not None:
        relation_ids.add(str(reply_quote.get("itemid") or ""))
        relation_ids.update(
            str(node.get("itemid") or "")
            for node in reply_quote.find_all(True, attrs={"itemprop": "time"})
        )
    return {relation_id for relation_id in relation_ids if relation_id}


def _exact_document_has_share_link(chat_id: str, message_id: str) -> bool:
    """Verify a raw HTML link or the SDK files share schema."""
    message = get_message_raw_exact(chat_id, message_id)
    content = str(message.get("content") or "")
    anchor = BeautifulSoup(content, "html.parser").find("a", href=True)
    if anchor is not None:
        return True

    files = _raw_message_properties(message).get("files") or []
    if isinstance(files, str):
        files = json.loads(files)
    if not isinstance(files, list):
        return False
    for file_entry in files:
        if not isinstance(file_entry, dict):
            continue
        file_info = file_entry.get("fileInfo") or {}
        if isinstance(file_info, dict) and any(
            file_info.get(key) for key in ("shareUrl", "fileUrl")
        ):
            return True
        if file_entry.get("objectUrl"):
            return True
    return False


def _exact_message_contains_marker(
    chat_id: str,
    message_id: str,
    marker: str,
    *,
    property_key: Optional[str] = None,
) -> bool:
    """Check one controlled marker in exact content or a named property."""
    message = get_message_raw_exact(chat_id, message_id)
    if property_key is None:
        return marker in str(message.get("content") or "")
    value = _raw_message_properties(message).get(property_key)
    return marker in json.dumps(value, ensure_ascii=False)


def send_native_user_reply(
    chat_id: str,
    source_message_id: str,
    content: str,
) -> str:
    """Create one service-user native reply without a Hermes ownership marker."""
    auth = _get_gateway_auth()
    auth._inject_truststore()
    source = get_message_raw_exact(chat_id, source_message_id)
    source_html = str(source.get("content") or "")
    source_text, _ = strip_teams_html(source_html)
    preview = html.escape(source_text[:160], quote=True)
    http_layer = _get_readback_http_layer(auth)
    sender_mri = http_layer._extract_mri_from_url(
        str(source.get("from") or "")
    )
    sender_name = html.escape(
        str(source.get("imdisplayname") or "Service User"),
        quote=True,
    )
    escaped_source_id = html.escape(str(source_message_id), quote=True)
    reply_html = (
        '<blockquote itemscope="" itemtype="http://schema.skype.com/Reply" '
        f'itemid="{escaped_source_id}">'
        f'<strong itemprop="mri" itemid="{html.escape(sender_mri, quote=True)}">'
        f"{sender_name}</strong>"
        f'<span itemprop="time" itemid="{escaped_source_id}"></span>'
        f'<p itemprop="preview">{preview}</p>'
        "</blockquote>"
        f"<p>{html.escape(content)}</p>"
    )
    quoted_messages = json.dumps(
        [
            {
                "messageId": str(source_message_id),
                "sender": sender_mri,
                "time": (
                    int(source_message_id)
                    if str(source_message_id).isdigit()
                    else 0
                ),
            }
        ]
    )
    payload = {
        "content": reply_html,
        "messagetype": "RichText/Html",
        "contenttype": "text",
        "properties": {
            "replyChainMessageId": str(source_message_id),
            "qtdMsgs": quoted_messages,
        },
    }
    encoded_chat = urllib.parse.quote(chat_id, safe="")
    url = f"{auth.msg_base}/conversations/{encoded_chat}/messages"
    try:
        result = http_layer._request("POST", url, json=payload).json()
    except Exception as exc:
        _discard_readback_http_layer(http_layer)
        raise RuntimeError(
            f"send_native_user_reply failed ({type(exc).__name__})"
        ) from None
    message_id = str(
        result.get("id") or result.get("OriginalArrivalTime") or ""
    )
    if not message_id:
        raise RuntimeError("send_native_user_reply returned no canonical identity")
    return message_id


def _visible_model_body(message: dict) -> str:
    """Return only the rendered model body from a normalized Teams message."""
    raw_content = str(message.get("_raw_content") or "")
    source = raw_content or str(message.get("content") or "")

    if raw_content:
        # The MSG API preserves the gateway's branded card in _raw_content.
        # Remove only the known header/footer nodes; arbitrary text elsewhere
        # remains part of the body and therefore makes an exact-marker check fail.
        soup = BeautifulSoup(raw_content, "html.parser")
        for candidate in soup.find_all("div"):
            style = str(candidate.get("style") or "").replace(" ", "").lower()
            if "border-left:" not in style:
                continue
            header = next(
                (
                    node
                    for node in candidate.find_all("b")
                    if node.get_text(" ", strip=True) == "🤖 Hermes"
                ),
                None,
            )
            footer = next(
                (
                    node
                    for node in candidate.find_all("span")
                    if "font-size:0.85em"
                    in str(node.get("style") or "").replace(" ", "").lower()
                    and node.get_text(" ", strip=True).startswith("— Hermes · ")
                ),
                None,
            )
            if header is not None and footer is not None:
                header.decompose()
                footer.decompose()
                source = str(candidate)
                break

    visible_text, _ = strip_teams_html(source)
    visible_text = html.unescape(visible_text)
    # Unicode format controls are not rendered. Ignoring them prevents a Teams
    # zero-width formatting artifact from making an otherwise exact body fail.
    visible_text = "".join(
        character
        for character in visible_text
        if unicodedata.category(character) != "Cf"
    )
    return visible_text.strip()


def _has_exact_visible_marker(message: dict, marker: str) -> bool:
    return _visible_model_body(message) == marker


_CUA_DRIVER_CALL_TIMEOUT_SECONDS = 120


def _run_cua_driver(tool: str, arguments: dict) -> dict:
    """Run one read-only cua-driver call without leaking private output."""
    executable = shutil.which("cua-driver")
    if not executable:
        raise RuntimeError("cua-driver is unavailable for Teams UI read-back")
    try:
        completed = subprocess.run(
            [executable, "call", tool, json.dumps(arguments)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            # Busy Windows desktops can take more than 30 seconds to walk the
            # process/window table before UIA starts returning elements.
            timeout=_CUA_DRIVER_CALL_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        raise RuntimeError(
            f"cua-driver {tool} failed ({type(exc).__name__})"
        ) from None
    if completed.returncode != 0:
        raise RuntimeError(
            f"cua-driver {tool} failed (exit={completed.returncode})"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"cua-driver {tool} returned invalid JSON") from None


def get_teams_ui_bot_card_labels(chat_id: str) -> list[str]:
    """Return rendered Hermes bot-card labels from the requested Teams chat."""
    windows_payload = _run_cua_driver("list_windows", {})
    windows = (
        windows_payload.get("windows")
        or windows_payload.get("_legacy_windows")
        or []
    )
    candidates = [
        window
        for window in windows
        if str(window.get("app_name") or "").lower() == "ms-teams.exe"
    ]
    candidates.sort(
        key=lambda window: (
            bool(window.get("is_on_screen", True)),
            int((window.get("bounds") or {}).get("width", window.get("width", 0)))
            * int((window.get("bounds") or {}).get("height", window.get("height", 0))),
        ),
        reverse=True,
    )

    expected_header = f"chat-header-{chat_id}"
    bot_card_pattern = re.compile(r"(?:^|\s)🤖 Hermes(?:\s|$)")
    for window in candidates:
        try:
            state = _run_cua_driver(
                "get_window_state",
                {
                    "pid": int(window["pid"]),
                    "window_id": int(window["window_id"]),
                    "include_screenshot": False,
                    "max_elements": 600,
                },
            )
        except RuntimeError:
            continue
        elements = state.get("elements") or []
        if not any(element.get("label") == expected_header for element in elements):
            continue
        labels = [
            str(element.get("label") or "").replace(r"\_", "_")
            for element in elements
        ]
        return [
            label
            for label in labels
            if bot_card_pattern.search(label) and "— Hermes ·" in label
        ]
    raise RuntimeError(
        "matching Teams chat window was not available for UI read-back"
    )


def _count_teams_ui_bot_markers(labels: list[str], marker: str) -> int:
    exact_marker_pattern = re.compile(
        rf"(?:^|\s)🤖 Hermes\s+{re.escape(marker)}\s+— Hermes ·"
    )
    return sum(1 for label in labels if exact_marker_pattern.search(label))


def get_teams_ui_bot_marker_count(chat_id: str, marker: str) -> int:
    """Count rendered Teams bot cards whose visible body is exactly the marker."""
    return _count_teams_ui_bot_markers(
        get_teams_ui_bot_card_labels(chat_id),
        marker,
    )


def _test_streaming_no_echo_duplication_via_ui(
    marker: str,
    graph_message_ids: list[str],
    *,
    send_query: bool = True,
    reply_timeout: float,
    poll_interval: float,
    settle_seconds: float,
) -> tuple[bool, str]:
    """Exercise the marker contract against the actual Teams UIA tree."""

    if not send_query:
        return (
            False,
            "Teams UIA fallback has no pre-query bot-card baseline; cannot "
            "exclude unexpected bot replies",
        )
    try:
        baseline_bot_labels = get_teams_ui_bot_card_labels(DM_CHAT_ID)
    except RuntimeError as exc:
        return (
            False,
            f"Teams UIA pre-query baseline failed ({type(exc).__name__})",
        )

    def wait_for_marker(expected: str, timeout: float) -> tuple[int, str | None]:
        deadline = time.monotonic() + timeout
        last_error = None
        while True:
            try:
                count = get_teams_ui_bot_marker_count(DM_CHAT_ID, expected)
                if count:
                    return count, None
            except RuntimeError as exc:
                last_error = str(exc)
            if time.monotonic() >= deadline:
                return 0, last_error
            time.sleep(poll_interval)

    graph_message_ids.append(
        send_chat_message(
            DM_CHAT_ID,
            f"Reply with exactly {marker}. Do not add other text and do not use tools.",
        )
    )
    reply_count, reply_error = wait_for_marker(marker, reply_timeout)
    if not reply_count:
        suffix = f" ({reply_error})" if reply_error else ""
        return False, f"No marker-matched model reply found via Teams UIA{suffix}"

    time.sleep(settle_seconds)
    try:
        settled_bot_labels = get_teams_ui_bot_card_labels(DM_CHAT_ID)
    except RuntimeError as exc:
        return False, f"Teams UIA final read-back failed ({type(exc).__name__})"
    settled_count = _count_teams_ui_bot_markers(settled_bot_labels, marker)
    if settled_count != 1:
        return (
            False,
            "Duplicate marker-matched model replies detected via Teams UIA "
            f"(marker replies={settled_count})",
        )
    new_bot_labels = list(
        (Counter(settled_bot_labels) - Counter(baseline_bot_labels)).elements()
    )
    new_marker_count = _count_teams_ui_bot_markers(new_bot_labels, marker)
    if len(new_bot_labels) != 1 or new_marker_count != 1:
        return (
            False,
            "Unexpected bot cards emitted after exact-marker query via Teams UIA "
            f"(new bot cards={len(new_bot_labels)}, "
            f"marker cards={new_marker_count})",
        )
    return (
        True,
        "Marker-matched model reply read back from Teams UIA with exactly one "
        "rendered bot message",
    )


def delete_msg_message(chat_id: str, message_id: str) -> None:
    """Delete one controlled bot message through the Teams MSG API."""
    from teams_skype_sdk.api._messages import MessagesService

    auth = _get_gateway_auth()
    auth._inject_truststore()
    last_error = "unknown"
    attempts = 3
    for attempt in range(attempts):
        http_layer = None
        try:
            http_layer = _get_readback_http_layer(auth)
            MessagesService(http_layer).delete(chat_id, message_id)
            return
        except requests.HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 404:
                return
            last_error = type(exc).__name__
            _discard_readback_http_layer(http_layer)
        except Exception as exc:
            last_error = type(exc).__name__
            _discard_readback_http_layer(http_layer)
        if attempt + 1 < attempts:
            time.sleep(min(2**attempt, 4))
    raise RuntimeError(
        f"delete_msg_message failed after {attempts} attempts ({last_error})"
    )


def send_via_sdk(chat_id: str, content: str) -> str:
    """Send through the bot-token SDK path and return its canonical identity."""
    from teams_skype_sdk.api import _messages as messages_module  # type: ignore
    from teams_skype_sdk.api._messages import MessagesService

    auth = _get_gateway_auth()
    auth._inject_truststore()
    last_error = "unknown"
    attempts = 4
    for attempt in range(attempts):
        http_layer = None
        try:
            http_layer = _get_readback_http_layer(auth)
            previous_msg_base = messages_module.MSG_BASE
            try:
                messages_module.MSG_BASE = auth.msg_base
                result = MessagesService(http_layer).send(
                    conversation_id=chat_id,
                    content=content,
                )
            finally:
                messages_module.MSG_BASE = previous_msg_base
            message_id = (
                str(result.get("id") or result.get("OriginalArrivalTime") or "")
                if isinstance(result, dict)
                else ""
            )
            if not message_id:
                raise RuntimeError("MSG send returned no canonical message identity")
            return message_id
        except Exception as exc:
            last_error = type(exc).__name__
            if http_layer is not None:
                _discard_readback_http_layer(http_layer)
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 4))
    raise RuntimeError(
        f"send_via_sdk failed after {attempts} attempts ({last_error})"
    )


def edit_msg_message(chat_id: str, message_id: str, content: str) -> str:
    """Edit a user-originated message in place through the canonical MSG API."""
    from teams_skype_sdk.api._messages import MessagesService

    auth = _get_gateway_auth()
    auth._inject_truststore()
    last_error = "unknown"
    attempts = 4
    for attempt in range(attempts):
        http_layer = None
        try:
            http_layer = _get_readback_http_layer(auth)
            result = MessagesService(http_layer).edit(chat_id, message_id, content)
            result_id = str(result.get("id") or "") if isinstance(result, dict) else ""
            result_status = result.get("status") if isinstance(result, dict) else None
            if result_status != "edited" or result_id != str(message_id):
                raise RuntimeError("MSG edit returned a malformed structural result")
            return message_id
        except Exception as exc:
            last_error = type(exc).__name__
            if http_layer is not None:
                _discard_readback_http_layer(http_layer)
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 4))
    raise RuntimeError(
        f"edit_msg_message failed after {attempts} attempts ({last_error})"
    )


def test_streaming_no_echo_duplication(
    log_path: str,
    baseline: int,
    *,
    ack_timeout: float = 300,
    reply_timeout: float = 240,
    poll_interval: float = 5,
    settle_seconds: float = 10,
) -> tuple[bool, str]:
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
    def _message_id(message: dict) -> str:
        return str(
            message.get("id")
            or message.get("OriginalArrivalTime")
            or message.get("originalarrivaltime")
            or ""
        )

    def _is_bot_message(message: dict) -> bool:
        content = str(message.get("content") or "")
        raw_content = str(message.get("_raw_content") or "")
        properties = (
            message.get("_raw_properties")
            or message.get("properties")
            or {}
        )
        if not isinstance(properties, dict):
            properties = {}
        return (
            properties.get("hermes_sender") in {"agent", "bot"}
            or "🤖" in content
            or "border-left" in raw_content
        )

    def _new_bot_messages(messages: list[dict], known_ids: set[str]) -> list[dict]:
        return [
            message
            for message in messages
            if _message_id(message)
            and _message_id(message) not in known_ids
            and _is_bot_message(message)
        ]

    graph_message_ids: list[str] = []
    cleanup_msg_ids: set[str] = set()
    query_sent = False
    reset_sent = False
    reset_cleanup_tracked = False
    ui_fallback_used = False
    functional_passed = False
    marker = ""
    reset_marker = ""
    try:
        run_marker = uuid.uuid4().hex[:12].upper()
        reset_marker = f"E2ERESET{run_marker}"
        marker = f"E2E{run_marker}"
        baseline_msgs = get_messages_raw(DM_CHAT_ID, page_size=50)
        baseline_ids = {_message_id(m) for m in baseline_msgs if _message_id(m)}

        # Establish a second baseline only after /new has produced its own
        # acknowledgment. Give the new session a unique title: the gateway's
        # formal reset handler includes that title in its localized reply, so
        # this gate is correlated without hard-coding an English UI string.
        # An unrelated delayed bot message therefore cannot satisfy the gate.
        graph_message_ids.append(
            send_chat_message(DM_CHAT_ID, f"/new {reset_marker}")
        )
        reset_sent = True
        ack_deadline = time.monotonic() + ack_timeout
        current_msgs: list[dict] = []
        while True:
            current_msgs = get_messages_raw(DM_CHAT_ID, page_size=50)
            ack_messages = [
                message
                for message in _new_bot_messages(current_msgs, baseline_ids)
                if reset_marker in (message.get("content") or "")
            ]
            if ack_messages:
                ack_ids = {
                    _message_id(message)
                    for message in ack_messages
                    if _message_id(message)
                }
                cleanup_msg_ids.update(ack_ids)
                reset_cleanup_tracked = bool(ack_ids)
                break
            if time.monotonic() >= ack_deadline:
                return (
                    False,
                    "No marker-correlated /new acknowledgment found via Teams "
                    f"MSG API within {ack_timeout:g}s",
                )
            time.sleep(poll_interval)

        query_baseline_ids = baseline_ids | {
            _message_id(m) for m in current_msgs if _message_id(m)
        }
        graph_message_ids.append(
            send_chat_message(
                DM_CHAT_ID,
                f"Reply with exactly {marker}. Do not add other text and do not use tools.",
            )
        )
        query_sent = True

        reply_deadline = time.monotonic() + reply_timeout
        query_bot_msgs: list[dict] = []
        marker_msgs: list[dict] = []
        while True:
            current_msgs = get_messages_raw(DM_CHAT_ID, page_size=50)
            query_bot_msgs = _new_bot_messages(current_msgs, query_baseline_ids)
            marker_msgs = [
                message
                for message in query_bot_msgs
                if _has_exact_visible_marker(message, marker)
            ]
            cleanup_msg_ids.update(
                _message_id(message)
                for message in query_bot_msgs
                if _message_id(message)
                and marker
                in (
                    str(message.get("content") or "")
                    + str(message.get("_raw_content") or "")
                )
            )
            if marker_msgs:
                break
            if time.monotonic() >= reply_deadline:
                return (
                    False,
                    "No marker-matched model reply found via Teams MSG API "
                    f"within {reply_timeout:g}s (new bot messages={len(query_bot_msgs)})",
                )
            time.sleep(poll_interval)

        # Let any late streaming edit/echo settle, then read the actual Teams
        # conversation again. The exact-marker query should produce one logical
        # bot message ID; two IDs prove an edit was echoed as a new message.
        time.sleep(settle_seconds)
        current_msgs = get_messages_raw(DM_CHAT_ID, page_size=50)
        query_bot_msgs = _new_bot_messages(current_msgs, query_baseline_ids)
        marker_msgs = [
            message
            for message in query_bot_msgs
            if _has_exact_visible_marker(message, marker)
        ]
        cleanup_msg_ids.update(
            _message_id(message)
            for message in query_bot_msgs
            if _message_id(message)
            and marker
            in (
                str(message.get("content") or "")
                + str(message.get("_raw_content") or "")
            )
        )
        distinct_marker_ids = {
            _message_id(message) for message in marker_msgs if _message_id(message)
        }

        if not marker_msgs:
            return False, "Marker-matched reply disappeared during Teams read-back"
        if len(distinct_marker_ids) != 1:
            return (
                False,
                "Duplicate marker-matched model replies detected after marker query "
                f"(distinct marker message IDs={len(distinct_marker_ids)}, "
                f"marker replies={len(marker_msgs)}, "
                f"other bot messages={len(query_bot_msgs) - len(marker_msgs)})",
            )
        unexpected_bot_ids = {
            _message_id(message)
            for message in query_bot_msgs
            if _message_id(message) not in distinct_marker_ids
        }
        if unexpected_bot_ids:
            return (
                False,
                "Unexpected bot message IDs emitted after exact-marker query "
                f"(unexpected bot message IDs={len(unexpected_bot_ids)})",
            )
        functional_passed = True
        return (
            True,
            "Marker-matched model reply read back from Teams with exactly one "
            "distinct bot message ID",
        )
    except RuntimeError:
        ui_fallback_used = True
        result = _test_streaming_no_echo_duplication_via_ui(
            marker,
            graph_message_ids,
            send_query=not query_sent,
            reply_timeout=reply_timeout,
            poll_interval=poll_interval,
            settle_seconds=settle_seconds,
        )
        functional_passed = result[0]
        return result
    finally:
        graph_deleted = 0
        msg_deleted = 0
        cleanup_failures: list[str] = []
        if ui_fallback_used:
            recovered_cleanup_ids = False
            recovery_detail = "MSG read-back unavailable"
            for attempt in range(3):
                try:
                    recovered_messages = get_messages_raw(DM_CHAT_ID, page_size=50)
                    marker_ids = {
                        _message_id(message)
                        for message in recovered_messages
                        if _message_id(message)
                        and _is_bot_message(message)
                        and _has_exact_visible_marker(message, marker)
                    }
                    reset_ids = {
                        _message_id(message)
                        for message in recovered_messages
                        if _message_id(message)
                        and _is_bot_message(message)
                        and reset_marker
                        in (
                            str(message.get("content") or "")
                            + str(message.get("_raw_content") or "")
                        )
                    }
                    reset_recovered = (
                        not reset_sent or reset_cleanup_tracked or bool(reset_ids)
                    )
                    if marker_ids and reset_recovered:
                        cleanup_msg_ids.update(marker_ids)
                        cleanup_msg_ids.update(reset_ids)
                        recovered_cleanup_ids = True
                        break
                    recovery_detail = (
                        f"marker={len(marker_ids)} reset={len(reset_ids)}"
                    )
                except Exception as exc:
                    recovery_detail = type(exc).__name__
                if attempt < 2:
                    time.sleep(min(2**attempt, 4))
            if not recovered_cleanup_ids:
                cleanup_failures.append(
                    f"msg:cleanup message IDs unavailable ({recovery_detail})"
                )
        for message_id in graph_message_ids:
            try:
                delete_graph_message(DM_CHAT_ID, message_id)
                graph_deleted += 1
            except Exception as exc:
                cleanup_failures.append(f"graph:{type(exc).__name__}")
        for message_id in cleanup_msg_ids:
            try:
                delete_msg_message(DM_CHAT_ID, message_id)
                msg_deleted += 1
            except Exception as exc:
                cleanup_failures.append(f"msg:{type(exc).__name__}")
        print(
            f"cleanup graph={graph_deleted}/{len(graph_message_ids)} "
            f"msg={msg_deleted}/{len(cleanup_msg_ids)} "
            f"failures={','.join(cleanup_failures) if cleanup_failures else 'none'}"
        )
        if cleanup_failures and functional_passed:
            raise RuntimeError(
                "streaming E2E cleanup failed after a successful result: "
                + ",".join(cleanup_failures)
            )


def _residual_markdown_labels(raw_html: str) -> list[str]:
    """Return literal markdown constructs left in rendered Teams HTML."""
    rendered_text = BeautifulSoup(str(raw_html or ""), "html.parser").get_text("\n")
    residuals = []
    if re.search(r"\*\*[^*]+\*\*", rendered_text):
        residuals.append("**bold**")
    if re.search(r"`[^`\n]+`", rendered_text):
        residuals.append("`code`")
    if re.search(r"\[[^\]]+\]\(https?://[^\s)]+\)", rendered_text):
        residuals.append("[text](url)")
    if re.search(r"^\s*[-*]\s+", rendered_text, re.MULTILINE):
        residuals.append("- bullet")
    if re.search(r"^\s*\|.+\|\s*$", rendered_text, re.MULTILINE):
        residuals.append("| pipe table |")
    return residuals


def test_no_residual_markdown_in_reply(
    log_path: str,
    baseline: int,
    *,
    reply_timeout: float = 300,
    poll_interval: float = 3,
) -> tuple[bool, str]:
    """CONTENT TIER: read back the actual rendered reply and assert no
    literal markdown syntax (**bold**, `code`, [text](url), leading '- ')
    leaked through to the Teams HTML the user sees.

    This is the exact class of bug the log-pattern tier cannot catch —
    'Turn ended: success' says nothing about whether the model's markdown
    output was actually converted to HTML before being sent.
    """
    del log_path, baseline
    token = uuid.uuid4().hex[:12].upper()
    marker = f"E2ERENDER{token}"
    prompt = (
        "用一個 table 列出 3 個測試項目的狀態，並用粗體標註結論。"
        f"回覆中必須原樣包含 {marker}。"
    )
    graph_message_ids: list[str] = []
    cleanup_message_ids: set[str] = set()
    baseline_ids: set[str] = set()
    functional_passed = False
    try:
        baseline_messages = get_messages_raw(DM_CHAT_ID, page_size=50)
        baseline_ids = {
            str(message.get("id") or "")
            for message in baseline_messages
            if message.get("id")
        }
        graph_message_ids.append(send_chat_message(DM_CHAT_ID, "/new"))
        time.sleep(3)
        graph_message_ids.append(send_chat_message(DM_CHAT_ID, prompt))

        raw_html = ""
        deadline = time.monotonic() + reply_timeout
        while time.monotonic() < deadline:
            messages = get_messages_raw(DM_CHAT_ID, page_size=50)
            candidates = [
                message
                for message in messages
                if str(message.get("id") or "") not in baseline_ids
                and _is_hermes_bot_message(message)
                and marker in _visible_model_body(message)
            ]
            cleanup_message_ids.update(
                str(message.get("id") or "")
                for message in messages
                if str(message.get("id") or "") not in baseline_ids
                and message.get("id")
                and _is_hermes_bot_message(message)
            )
            if candidates:
                raw_html = str(
                    candidates[0].get("_raw_content")
                    or candidates[0].get("content")
                    or ""
                )
                break
            time.sleep(poll_interval)

        if not raw_html:
            return False, "No marker-correlated bot reply found within wait window"
        residuals = _residual_markdown_labels(raw_html)
        if residuals:
            return False, f"Residual markdown found: {residuals}"
        functional_passed = True
        return True, f"No residual markdown in marker-correlated reply (len={len(raw_html)})"
    finally:
        cleanup_errors = []
        try:
            for message in get_messages_raw(DM_CHAT_ID, page_size=60):
                message_id = str(message.get("id") or "")
                if (
                    message_id
                    and message_id not in baseline_ids
                    and _is_hermes_bot_message(message)
                ):
                    cleanup_message_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        for message_id in dict.fromkeys(graph_message_ids):
            if not message_id:
                continue
            try:
                delete_graph_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
        for message_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        if cleanup_errors and functional_passed:
            raise RuntimeError(
                "residual markdown E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + ")"
            )


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

    skype_token = _get_gateway_auth().skype_token()

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
    from agent.garbage_detector import is_garbage, _garbage_score
    import html as _html

    marker = f"E2EGARBAGE{uuid.uuid4().hex[:12].upper()}"
    baseline_msgs = get_messages_raw(DM_CHAT_ID, page_size=120)
    baseline_ids = {
        str(message.get("id") or "")
        for message in baseline_msgs
        if message.get("id")
    }
    graph_message_ids: list[str] = []
    cleanup_message_ids: set[str] = set()

    try:
        reset_graph_id = send_chat_message(DM_CHAT_ID, f"/new {marker}RESET")
        graph_message_ids.append(str(reset_graph_id))
        reset_deadline = time.monotonic() + 300
        reset_reply_id = ""
        while time.monotonic() < reset_deadline:
            reset_replies = [
                message
                for message in get_messages_raw(DM_CHAT_ID, page_size=120)
                if str(message.get("id") or "") not in baseline_ids
                and _is_hermes_bot_message(message)
                and f"{marker}RESET" in _visible_model_body(message)
            ]
            cleanup_message_ids.update(
                str(message.get("id") or "") for message in reset_replies
            )
            if len(reset_replies) > 1:
                return False, f"reset_ack={len(reset_replies)}; duplicate_ack=True"
            if reset_replies:
                reset_reply_id = str(reset_replies[0].get("id") or "")
                break
            time.sleep(3)
        if not reset_reply_id:
            return False, "reset_ack=0"

        query_graph_id = send_chat_message(
            DM_CHAT_ID,
            f"{marker}QUERY 不用使用工具。第一行務必原樣輸出 {marker}DONE；"
            "接著用繁體中文寫四點條列，說明軟體測試的重要性；"
            "每點至少二十五個中文字，總長必須超過一百五十字。",
        )
        graph_message_ids.append(str(query_graph_id))
        reply_deadline = time.monotonic() + 300
        delivered_reply = None
        while time.monotonic() < reply_deadline:
            replies = [
                message
                for message in get_messages_raw(DM_CHAT_ID, page_size=120)
                if str(message.get("id") or "") not in baseline_ids
                and str(message.get("id") or "") != reset_reply_id
                and _is_hermes_bot_message(message)
                and f"{marker}DONE" in _visible_model_body(message)
            ]
            cleanup_message_ids.update(
                str(message.get("id") or "") for message in replies
            )
            reply_ids = {
                str(message.get("id") or "") for message in replies
            }
            if len(reply_ids) > 1:
                return False, f"terminal_replies={len(reply_ids)}; duplicate_reply=True"
            if replies:
                delivered_reply = replies[0]
                break
            time.sleep(3)
        if delivered_reply is None:
            return False, "No marker-correlated bot reply received within 300s"

        raw = _visible_model_body(delivered_reply)
        text = _html.unescape(re.sub(r"<[^>]+>", " ", raw))
        text = text.replace(f"{marker}DONE", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 80:
            return False, (
                "Marker-correlated reply was not long enough to exercise the "
                "production detector's 80-character threshold"
            )
        if "\ufffd" in text:
            return False, "Delivered reply contains U+FFFD replacement characters"
        repeated = re.search(r"([^\s])\1{11,}", text)
        if repeated:
            return False, (
                "Delivered reply contains a repeated-character run: "
                f"{repeated.group(0)!r}"
            )
        if is_garbage(text):
            return False, (
                "Production detector flags the delivered clean reply as garbage "
                f"(score={_garbage_score(text):.2f})"
            )

        new_log = tail_log(log_path, baseline)
        discard_count = len(
            re.findall(
                r"(?:Garbage output detected|Corrupt final model output detected)",
                new_log,
            )
        )
        if discard_count:
            return False, (
                f"Clean-output turn triggered {discard_count} garbage discard(s); "
                "this is a false positive even though a retry eventually replied"
            )
        return True, (
            "1 marker-correlated substantial reply delivered; detector score="
            f"{_garbage_score(text)}; 0 false-positive discards"
        )
    finally:
        cleanup_errors: list[str] = []
        try:
            for message in get_messages_raw(DM_CHAT_ID, page_size=120):
                if marker not in _visible_model_body(message):
                    continue
                message_id = str(message.get("id") or "")
                if message_id:
                    cleanup_message_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        for graph_message_id in graph_message_ids:
            try:
                delete_graph_message(DM_CHAT_ID, graph_message_id)
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
            cleanup_message_ids.add(graph_message_id)
        for message_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        remaining = []
        for attempt in range(12):
            try:
                remaining = [
                    message
                    for message in get_messages_raw(DM_CHAT_ID, page_size=120)
                    if marker in _visible_model_body(message)
                ]
            except Exception as exc:
                cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
                break
            if not remaining:
                break
            if attempt < 11:
                time.sleep(2)
        if remaining:
            cleanup_errors.append(f"msg-remain:{len(remaining)}")
        if cleanup_errors:
            raise RuntimeError(
                "garbage-detector E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + ")"
            )


# ── Named test cases ──────────────────────────────────────────────

def test_dm_echo_guard(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: bot's own sent messages are skipped by echo guard."""
    marker = f"E2EECHO{uuid.uuid4().hex[:12].upper()}"
    baseline_messages = get_messages_raw(DM_CHAT_ID, page_size=40)
    baseline_ids = {
        str(message.get("id") or "")
        for message in baseline_messages
        if message.get("id")
    }
    graph_message_id = ""
    cleanup_message_ids: set[str] = set()
    try:
        graph_message_id = send_chat_message(DM_CHAT_ID, f"/new {marker}")
        deadline = time.monotonic() + 120
        reply_id = ""
        while not reply_id:
            messages = get_messages_raw(DM_CHAT_ID, page_size=50)
            replies = [
                message
                for message in messages
                if str(message.get("id") or "") not in baseline_ids
                and _is_hermes_bot_message(message)
                and marker in _visible_model_body(message)
            ]
            if len(replies) > 1:
                cleanup_message_ids.update(
                    str(message.get("id") or "") for message in replies
                )
                return False, f"echo_ack={len(replies)}; duplicate_ack={len(replies) - 1}"
            if replies:
                reply_id = str(replies[0].get("id") or "")
                cleanup_message_ids.add(reply_id)
                break
            if time.monotonic() >= deadline:
                return False, "echo_ack=0; duplicate_ack=0"
            time.sleep(3)

        found, evidence = wait_and_check_log(
            log_path, baseline,
            [rf"skipping own sent message id={re.escape(_log_ref(reply_id))}(?:\s|$)"],
            wait_seconds=45,  # adaptive poll may be 30s while WS is healthy
        )
        return found, evidence
    finally:
        cleanup_errors: list[str] = []
        try:
            for message in get_messages_raw(DM_CHAT_ID, page_size=60):
                if marker not in _visible_model_body(message):
                    continue
                message_id = str(message.get("id") or "")
                if message_id:
                    cleanup_message_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        if graph_message_id:
            try:
                delete_graph_message(DM_CHAT_ID, str(graph_message_id))
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
        for message_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        try:
            remaining = [
                message
                for message in get_messages_raw(DM_CHAT_ID, page_size=60)
                if marker in _visible_model_body(message)
            ]
            if remaining:
                cleanup_errors.append(f"msg-remain:{len(remaining)}")
        except Exception as exc:
            cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError(
                "echo-guard E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + ")"
            )


def test_mention_gating_ignore(log_path: str, baseline: int) -> tuple[bool, str]:
    """Group: a non-mentioned message is inspected but produces no bot reply."""
    idle_ok, idle_evidence, _ = _busy_burst_group_idle_preflight()
    if not idle_ok:
        return False, idle_evidence
    marker = f"E2EIGNORE{uuid.uuid4().hex[:12].upper()}"
    graph_message_id = ""
    cleanup_message_ids: set[str] = set()
    try:
        content = f"Reply with exactly {marker}. Do not add other text or use tools."
        graph_message_id = send_chat_message(GROUP_CHAT_ID, content)
        inspected, evidence = wait_and_check_log(
            log_path,
            baseline,
            [
                rf"inspecting msg id="
                rf"{re.escape(_log_ref(str(graph_message_id)))}(?:\s|$)"
            ],
            wait_seconds=45,
        )
        if not inspected:
            return False, f"inspected=False; evidence_chars={len(evidence)}"

        # Mention gating runs synchronously after inspection. A unique marker
        # prevents delayed messages from earlier full-suite attempts from
        # contaminating this run's verdict.
        time.sleep(5)
        post_inspection_log = tail_log(log_path, baseline)
        if any(
            marker in line and "inbound message:" in line
            for line in post_inspection_log.splitlines()
        ):
            return False, "mention_ignored=False; dispatch_count=1"

        replies = [
            message
            for message in get_messages_raw(GROUP_CHAT_ID, page_size=50)
            if _is_hermes_bot_message(message)
            and _has_exact_visible_marker(message, marker)
        ]
        cleanup_message_ids.update(
            str(message.get("id") or "") for message in replies
        )
        if replies:
            return False, f"mention_ignored=False; reply_count={len(replies)}"
        return True, "mention_ignored=True; dispatch_count=0; reply_count=0"
    finally:
        cleanup_errors: list[str] = []
        try:
            for message in get_messages_raw(GROUP_CHAT_ID, page_size=60):
                if marker not in _visible_model_body(message):
                    continue
                message_id = str(message.get("id") or "")
                if message_id:
                    cleanup_message_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        if graph_message_id:
            try:
                delete_graph_message(GROUP_CHAT_ID, str(graph_message_id))
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
        for message_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(GROUP_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        try:
            remaining = [
                message
                for message in get_messages_raw(GROUP_CHAT_ID, page_size=60)
                if marker in _visible_model_body(message)
            ]
            if remaining:
                cleanup_errors.append(f"msg-remain:{len(remaining)}")
        except Exception as exc:
            cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError(
                "mention-ignore E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + ")"
            )


def test_mention_gating_process(log_path: str, baseline: int) -> tuple[bool, str]:
    """Group: message with @hermes is processed when require_mention=true.

    Real behavioral test: the old version only checked that the inbound
    message was logged ("new message from...") — that log line fires for
    EVERY inbound message regardless of mention gating, so it never
    actually proved the agent was triggered.  This reads back the real
    conversation and asserts a genuine bot reply (border-left signature)
    landed after our @mention message.
    """
    del log_path, baseline
    idle_ok, idle_evidence, _ = _busy_burst_group_idle_preflight()
    if not idle_ok:
        return False, idle_evidence
    marker = f"E2EMENTION{uuid.uuid4().hex[:12].upper()}"
    baseline_msgs = get_messages_raw(GROUP_CHAT_ID, page_size=40)
    baseline_ids = {
        str(message.get("id") or "")
        for message in baseline_msgs
        if message.get("id")
    }
    graph_message_id = ""
    cleanup_message_ids: set[str] = set()
    try:
        content = (
            '<at id="0">Hermes</at>&nbsp;'
            f"Reply with exactly {marker}. Do not add other text or use tools."
        )
        graph_message_id = send_chat_message(GROUP_CHAT_ID, content)
        deadline = time.monotonic() + 240
        while True:
            messages = get_messages_raw(GROUP_CHAT_ID, page_size=50)
            reply_ids = {
                str(message.get("id") or "")
                for message in messages
                if message.get("id")
                and str(message.get("id")) not in baseline_ids
                and _is_hermes_bot_message(message)
                and _has_exact_visible_marker(message, marker)
            }
            if len(reply_ids) == 1:
                cleanup_message_ids.update(reply_ids)
                return True, "mention_dispatch=1; duplicate_dispatch=0"
            if len(reply_ids) > 1:
                cleanup_message_ids.update(reply_ids)
                return False, (
                    f"mention_dispatch={len(reply_ids)}; "
                    f"duplicate_dispatch={len(reply_ids) - 1}"
                )
            if time.monotonic() >= deadline:
                return False, "mention_dispatch=0; duplicate_dispatch=0"
            time.sleep(3)
    finally:
        cleanup_errors: list[str] = []
        try:
            for message in get_messages_raw(GROUP_CHAT_ID, page_size=60):
                if marker not in _visible_model_body(message):
                    continue
                message_id = str(message.get("id") or "")
                if message_id:
                    cleanup_message_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        if graph_message_id:
            try:
                delete_graph_message(GROUP_CHAT_ID, str(graph_message_id))
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
        for message_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(GROUP_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        try:
            remaining = [
                message
                for message in get_messages_raw(GROUP_CHAT_ID, page_size=60)
                if marker in _visible_model_body(message)
            ]
            if remaining:
                cleanup_errors.append(f"msg-remain:{len(remaining)}")
        except Exception as exc:
            cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError(
                "mention-gating E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + ")"
            )


def _picker_current_model(content: str) -> str:
    """Parse the active model from either raw HTML or SDK-normalized text."""
    for pattern in (
        r"Current:\s*<b>(.*?)</b>",
        r"Current:\s*\*\*(.*?)\*\*",
        r"Current:\s*(.*?)\s+via\b",
    ):
        match = re.search(pattern, content, flags=re.DOTALL)
        if match:
            return re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return ""


def _picker_numbered_choice(content: str, marker: str) -> Optional[int]:
    """Parse a numbered picker row from raw HTML or normalized plain text."""
    for block in re.findall(
        r'<div style="margin:1px 0">(.*?)</div>',
        content,
        flags=re.DOTALL,
    ):
        if marker not in block:
            continue
        match = re.search(r">(\d+)</span>", block)
        if match:
            return int(match.group(1))

    plain_marker = re.sub(r"<[^>]+>", "", marker).lstrip(">").strip()
    for marker_match in re.finditer(re.escape(plain_marker), content):
        choices = re.findall(
            r"(\d+)(?=[^\d]{0,160}$)", content[: marker_match.start()]
        )
        if choices:
            return int(choices[-1])
    return None


def test_model_picker(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM /model picker: provider list -> provider choice -> model list."""
    def _read_picker(
        marker: str, exclude_ids: set[str], wait_seconds: int = 60
    ) -> Optional[dict]:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            for message in get_messages_raw(DM_CHAT_ID, page_size=30):
                message_id = str(message.get("id") or "")
                if not message_id or message_id in exclude_ids:
                    continue
                content = str(message.get("content") or "")
                if marker in content:
                    return message
            time.sleep(2)
        return None

    provider_baseline = {
        str(message.get("id") or "")
        for message in get_messages_raw(DM_CHAT_ID, page_size=30)
    }
    send_chat_message(DM_CHAT_ID, "/model")

    # Allow the stable-WS poll interval (up to 30s), plus cold provider
    # discovery in a freshly restarted gateway (observed as high as 96s).
    # Keep polling for stage evidence instead of sleeping once for the bound.
    for attempt in range(30):
        time.sleep(4)
        step1_log = tail_log(log_path, baseline)
        if "model picker step 1 (providers) sent" in step1_log:
            break
    else:
        return False, step1_log[-500:]

    provider_message = _read_picker("Select Provider", provider_baseline)
    if not provider_message:
        return False, "New provider picker was not readable from Teams"
    picker_id = str(provider_message.get("id") or "")

    # A successful send is not enough: the next poll must classify the
    # outbound picker as Hermes-owned.  This catches the SDK-normalization
    # regression where ``content`` lost its HTML fingerprint and the picker
    # was dispatched back into the agent as if the user had typed it.
    skipped, skip_evidence = wait_and_check_log(
        log_path,
        baseline,
        [rf"skipping own sent message id={re.escape(_log_ref(picker_id))}(?:\s|$)"],
        wait_seconds=50,
    )
    if not skipped:
        return False, (
            f"Outbound picker id={picker_id} was not echo-guarded; "
            f"evidence={skip_evidence}"
        )

    provider_html = str(provider_message.get("content") or "")
    current_model = _picker_current_model(provider_html)
    provider_choice = _picker_numbered_choice(provider_html, "←")
    if not current_model or provider_choice is None:
        return False, (
            "Could not identify the current provider/model from the real picker; "
            f"current_model={current_model!r}, provider_choice={provider_choice!r}, "
            f"html={provider_html[:800]!r}"
        )

    # Select the current provider so the E2E never mutates the user's model.
    model_baseline = {
        str(message.get("id") or "")
        for message in get_messages_raw(DM_CHAT_ID, page_size=30)
    }
    baseline2 = sum(1 for _ in open(log_path, encoding="utf-8", errors="replace"))
    send_chat_message(DM_CHAT_ID, str(provider_choice))

    found, evidence = wait_and_check_log(
        log_path, baseline2,
        [r"model picker step 2.*sent"],
        wait_seconds=45,
    )
    if not found:
        return False, evidence

    model_message = _read_picker("Select Model", model_baseline)
    if not model_message:
        return False, "New model picker was not readable from Teams"
    sub_picker_id = str(model_message.get("id") or "")
    model_html = str(model_message.get("content") or "")

    model_choice = _picker_numbered_choice(model_html, current_model)
    if model_choice is None:
        model_choice = _picker_numbered_choice(model_html, "✓")
    if model_choice is None:
        return False, (
            f"Current model {current_model!r} was not selectable in the real sub-picker"
        )

    # Complete the flow. The adapter clears picker state before invoking the
    # callback, so a successful confirmation proves the stale-state regression
    # cannot poison the next E2E run.
    confirmation_baseline = {
        str(message.get("id") or "")
        for message in get_messages_raw(DM_CHAT_ID, page_size=20)
    }
    baseline3 = sum(1 for _ in open(log_path, encoding="utf-8", errors="replace"))
    send_chat_message(DM_CHAT_ID, str(model_choice))
    selected, selection_evidence = wait_and_check_log(
        log_path,
        baseline3,
        [r"model picker model selection:"],
        wait_seconds=45,
    )
    if not selected:
        return False, selection_evidence

    deadline = time.time() + 30
    while time.time() < deadline:
        confirmations = [
            message for message in get_messages_raw(DM_CHAT_ID, page_size=30)
            if str(message.get("id") or "") not in confirmation_baseline
            and current_model in str(message.get("content") or "")
            and "Select Model" not in str(message.get("content") or "")
        ]
        if confirmations:
            return True, (
                f"provider={provider_choice}, model={model_choice} ({current_model}); "
                f"confirmation_id={confirmations[0].get('id')}"
            )
        time.sleep(2)
    return False, (
        f"Model selection executed but no real confirmation containing "
        f"{current_model!r} was readable from Teams"
    )


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
    # Use the bot-token path. A Graph user message would correctly start a
    # live agent turn and poison the next sequential E2E test; the restart
    # watermark contract only requires a real persisted message ID.
    marker_id = send_via_sdk(DM_CHAT_ID, marker)
    if not marker_id:
        return False, "SDK restart marker send returned no message ID"
    skipped, skip_evidence = wait_and_check_log(
        log_path,
        baseline,
        [rf"skipping own sent message id={re.escape(_log_ref(marker_id))}(?:\s|$)"],
        wait_seconds=45,
    )
    if not skipped:
        return False, (
            f"Restart marker id={marker_id} was not echo-guarded; "
            f"evidence={skip_evidence}"
        )
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
    import tempfile, os, asyncio
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
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(png_data)
        temp_path = f.name

    adapter = TeamsMTKAdapter(None)
    sent_message_id = ""
    try:
        async def _call():
            return await adapter.send_image_file(DM_CHAT_ID, temp_path, caption="E2E_AUTO image test")

        result = asyncio.run(_call())

        if not result.success:
            return False, f"send_image_file returned success=False error={result.error!r}"
        if not result.message_id:
            return False, f"send_image_file succeeded but returned no message_id: {result!r}"
        sent_message_id = str(result.message_id)

        # Verify the returned canonical identity against exact raw HTML. The
        # SDK-normalized page content converts <img> to Markdown and cannot
        # prove the wire-level inline image contract.
        deadline = time.time() + 20
        has_image = False
        while time.time() < deadline:
            try:
                has_image = _exact_message_has_html_tag(
                    DM_CHAT_ID,
                    sent_message_id,
                    "img",
                )
            except RuntimeError:
                has_image = False
            if has_image:
                break
            time.sleep(1)
        if not has_image:
            return False, (
                "send_image_file returned success=True but exact read-back "
                "found no <img> message"
            )
        return True, "send_image_file succeeded and exact <img> read-back verified"
    finally:
        if sent_message_id:
            cleanup = asyncio.run(adapter.delete_message(DM_CHAT_ID, sent_message_id))
            if cleanup.get("status") != "deleted":
                raise RuntimeError(
                    "send-image E2E cleanup failed: "
                    f"status={cleanup.get('status')}"
                )
        os.unlink(temp_path)


def test_send_document(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: send_document() actually uploads to OneDrive and shares a link (G-MEDIA-2).

    Real behavioral test: writes a temp text file, calls send_document()
    against the real DM chat, and asserts SendResult.success with a real
    message_id — then reads back the conversation for a share link.
    """
    import tempfile, os, asyncio
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write("E2E_AUTO send_document test content\n")
        temp_path = f.name

    adapter = TeamsMTKAdapter(None)
    sent_message_id = ""
    try:
        async def _call():
            return await adapter.send_document(DM_CHAT_ID, temp_path, caption="E2E_AUTO doc test")

        result = asyncio.run(_call())

        if not result.success:
            return False, f"send_document returned success=False error={result.error!r}"
        if not result.message_id:
            return False, f"send_document succeeded but returned no message_id: {result!r}"
        sent_message_id = str(result.message_id)

        deadline = time.time() + 20
        has_link = False
        while time.time() < deadline:
            try:
                has_link = _exact_document_has_share_link(
                    DM_CHAT_ID,
                    sent_message_id,
                )
            except (RuntimeError, json.JSONDecodeError):
                has_link = False
            if has_link:
                break
            time.sleep(1)
        if not has_link:
            return False, (
                "send_document returned success=True but exact read-back "
                "found neither an HTML link nor a files share schema"
            )
        return True, "send_document succeeded and exact share contract verified"
    finally:
        if sent_message_id:
            cleanup = asyncio.run(adapter.delete_message(DM_CHAT_ID, sent_message_id))
            if cleanup.get("status") != "deleted":
                raise RuntimeError(
                    "send-document E2E cleanup failed: "
                    f"status={cleanup.get('status')}"
                )
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

    fallback_marker = f"E2E_AUTO adaptive-card-fallback {int(time.time())}"
    card_marker = f"E2E_AUTO_CARD_{int(time.time())}"
    adapter = TeamsMTKAdapter(None)
    sent_message_id = ""

    async def _call():
        return await adapter.send_adaptive_card(
            DM_CHAT_ID,
            card={"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": card_marker}]},
            fallback_text=fallback_marker,
        )

    try:
        result = asyncio.run(_call())

        if not result.success:
            return False, (
                "send_adaptive_card returned success=False: "
                f"enabled={enabled}, error_type={type(result.error).__name__}"
            )
        if not result.message_id:
            return False, "send_adaptive_card succeeded but returned no message ID"
        sent_message_id = str(result.message_id)

        marker = card_marker if enabled else fallback_marker
        property_key = "cards" if enabled else None
        deadline = time.time() + 20
        marker_found = False
        while time.time() < deadline:
            try:
                marker_found = _exact_message_contains_marker(
                    DM_CHAT_ID,
                    sent_message_id,
                    marker,
                    property_key=property_key,
                )
            except (RuntimeError, json.JSONDecodeError):
                marker_found = False
            if marker_found:
                break
            time.sleep(1)
        if not marker_found:
            expected = "properties.cards" if enabled else "fallback content"
            return False, (
                "send_adaptive_card exact read-back missing expected "
                f"{expected}; enabled={enabled}"
            )
        if enabled:
            return True, "Enabled path verified via exact properties.cards"
        return True, "Disabled path verified via exact fallback content"
    finally:
        if sent_message_id:
            cleanup = asyncio.run(adapter.delete_message(DM_CHAT_ID, sent_message_id))
            if cleanup.get("status") != "deleted":
                raise RuntimeError(
                    "adaptive-card E2E cleanup failed: "
                    f"status={cleanup.get('status')}"
                )


def test_send_text(log_path: str, baseline: int) -> tuple[bool, str]:
    """DM: send a message via Graph API, gateway replies, check log for sent message."""
    marker = f"E2ESEND{uuid.uuid4().hex[:12].upper()}"
    baseline_messages = get_messages_raw(DM_CHAT_ID, page_size=40)
    baseline_ids = {
        str(message.get("id") or "")
        for message in baseline_messages
        if message.get("id")
    }
    graph_message_id = ""
    cleanup_message_ids: set[str] = set()
    try:
        graph_message_id = send_chat_message(
            DM_CHAT_ID,
            f"{marker} send test — hello",
        )

        # Stable WS polling may take 30s before the inbound message is seen;
        # use the same bounded model-turn budget as the P0 query tests.
        return wait_and_check_log(
            log_path,
            baseline,
            [r"TeamsMTK: sent message id="],
            wait_seconds=300,
        )
    finally:
        cleanup_errors: list[str] = []
        try:
            for message in get_messages_raw(DM_CHAT_ID, page_size=60):
                message_id = str(message.get("id") or "")
                if (
                    message_id
                    and message_id not in baseline_ids
                    and _is_hermes_bot_message(message)
                ):
                    cleanup_message_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        if graph_message_id:
            try:
                delete_graph_message(DM_CHAT_ID, str(graph_message_id))
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
            cleanup_message_ids.add(str(graph_message_id))
        for message_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        try:
            remaining = [
                message
                for message in get_messages_raw(DM_CHAT_ID, page_size=60)
                if marker in _visible_model_body(message)
            ]
            if remaining:
                cleanup_errors.append(f"msg-remain:{len(remaining)}")
        except Exception as exc:
            cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError(
                "send-text E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + ")"
            )


def test_reaction_roundtrip(log_path: str, baseline: int) -> tuple[bool, str]:
    """S7: add and remove a real reaction, verified through MSG read-back."""
    del log_path, baseline
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    marker = f"E2E_AUTO reaction roundtrip {time.time_ns()}"
    message_id = send_via_sdk(DM_CHAT_ID, marker)
    if not message_id:
        return False, "SDK reaction target send returned no message ID"

    adapter = TeamsMTKAdapter(None)

    try:
        sent = asyncio.run(adapter.send_reaction(DM_CHAT_ID, message_id, "like"))
        if sent.get("status") != "reacted":
            return False, f"send_reaction failed: {sent!r}"

        deadline = time.time() + 20
        added_count = 0
        while time.time() < deadline:
            added_count = _reaction_user_count(DM_CHAT_ID, message_id, "like")
            if added_count > 0:
                break
            time.sleep(1)
        if added_count <= 0:
            return False, "Reaction was not visible in exact MSG read-back: user_count=0"

        removed = asyncio.run(adapter.remove_reaction(DM_CHAT_ID, message_id, "like"))
        if removed.get("status") != "removed":
            return False, f"remove_reaction failed: {removed!r}"

        deadline = time.time() + 20
        remaining_count = added_count
        while time.time() < deadline:
            remaining_count = _reaction_user_count(DM_CHAT_ID, message_id, "like")
            if remaining_count == 0:
                break
            time.sleep(1)
        if remaining_count != 0:
            return False, (
                "Reaction remained after remove: "
                f"user_count={remaining_count}"
            )

        return True, "Reaction add/remove exact read-back verified"
    finally:
        asyncio.run(adapter.delete_message(DM_CHAT_ID, message_id))


def test_delete_message_safety(log_path: str, baseline: int) -> tuple[bool, str]:
    """S9: delete an own message and refuse a processed foreign message."""
    del log_path, baseline
    import hashlib
    from unittest.mock import AsyncMock

    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    adapter = TeamsMTKAdapter(None)
    own_marker = f"E2E_AUTO delete own {time.time_ns()}"
    sent = asyncio.run(adapter.send(DM_CHAT_ID, own_marker))
    own_id = str(sent.message_id or "")
    if not sent.success or not own_id:
        return False, f"Own delete target send failed: success={sent.success}"

    own_deleted = False
    foreign_id = ""
    try:
        deleted = asyncio.run(adapter.delete_message_safe(DM_CHAT_ID, own_id))
        if deleted.get("status") != "deleted":
            return False, f"delete_message_safe rejected own message: status={deleted.get('status')}"
        own_deleted = True

        deadline = time.time() + 20
        tombstone_found = False
        tombstone_content_length = 0
        tombstone_has_deletetime = False
        while time.time() < deadline:
            (
                tombstone_found,
                tombstone_content_length,
                tombstone_has_deletetime,
            ) = _exact_tombstone_state(
                DM_CHAT_ID,
                own_id,
            )
            if (
                tombstone_found
                and tombstone_content_length == 0
                and tombstone_has_deletetime
            ):
                break
            time.sleep(1)
        else:
            return False, (
                f"Own tombstone missing: found={tombstone_found}, "
                f"content_length={tombstone_content_length}, "
                f"has_deletetime={tombstone_has_deletetime}"
            )

        foreign_marker = f"E2E_AUTO foreign delete guard {time.time_ns()}"
        foreign_id = send_chat_message(GROUP_CHAT_ID, foreign_marker)
        foreign = None
        deadline = time.time() + 20
        while time.time() < deadline:
            foreign = next(
                (
                    item
                    for item in get_messages_raw(GROUP_CHAT_ID, page_size=30)
                    if str(item.get("id")) == foreign_id
                ),
                None,
            )
            foreign_raw = str((foreign or {}).get("_raw_content") or "")
            if foreign and foreign_marker in foreign_raw:
                break
            time.sleep(1)
        foreign_content = str((foreign or {}).get("content") or "")
        foreign_raw = str((foreign or {}).get("_raw_content") or "")
        if not foreign or foreign_marker not in foreign_raw:
            return False, (
                "Controlled foreign message was not ready from MSG API: "
                f"found={bool(foreign)}, raw_length={len(foreign_raw)}"
            )

        # Reproduce the live-adapter state: process this exact inbound message
        # before asking the same adapter to enforce safe deletion.
        adapter._last_message_ids[GROUP_CHAT_ID] = None
        adapter._message_handler = AsyncMock()
        asyncio.run(adapter._process_new_messages(GROUP_CHAT_ID, [foreign]))

        foreign_hash = hashlib.sha256(foreign_content.encode("utf-8")).hexdigest()[:10]
        refused = asyncio.run(adapter.delete_message_safe(GROUP_CHAT_ID, foreign_id))
        if (
            refused.get("status") != "error"
            or "not your message" not in refused.get("error", "")
        ):
            return False, (
                f"Foreign delete was not refused: status={refused.get('status')}, "
                f"error_type={type(refused.get('error')).__name__}"
            )

        after = next(
            (
                item
                for item in get_messages_raw(GROUP_CHAT_ID, page_size=30)
                if str(item.get("id")) == foreign_id
            ),
            None,
        )
        after_content = str((after or {}).get("content") or "")
        after_hash = hashlib.sha256(after_content.encode("utf-8")).hexdigest()[:10]
        if not after or after_hash != foreign_hash:
            return False, (
                f"Foreign message changed after refusal: found={bool(after)}, "
                f"before_length={len(foreign_content)}, after_length={len(after_content)}, "
                f"hash_equal={after_hash == foreign_hash}"
            )

        own_hash = hashlib.sha256(own_id.encode("utf-8")).hexdigest()[:10]
        foreign_id_hash = hashlib.sha256(foreign_id.encode("utf-8")).hexdigest()[:10]
        return True, (
            f"Own tombstone hash={own_hash}; processed foreign message "
            f"hash={foreign_id_hash} refused and unchanged"
        )
    finally:
        if not own_deleted:
            cleanup = asyncio.run(adapter.delete_message(DM_CHAT_ID, own_id))
            if cleanup.get("status") != "deleted":
                raise RuntimeError(
                    f"own delete-target cleanup failed: status={cleanup.get('status')}"
                )
        if foreign_id:
            delete_graph_message(GROUP_CHAT_ID, foreign_id)


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
        wait_seconds=45,  # adaptive poll may be 30s while WS is healthy
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
        wait_seconds=45,  # adaptive poll may be 30s while WS is healthy
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


def test_contact_routing(log_path: str, baseline: int) -> tuple[bool, str]:
    """G13-A.4: resolve a dynamic contact target and deliver via the real API."""
    del log_path, baseline
    import asyncio
    import hashlib
    import json as _json
    from types import SimpleNamespace
    from unittest.mock import patch

    from gateway.config import Platform
    from gateway.platforms.teams_mtk import TeamsMTKAdapter
    from tools.send_message_tool import send_message_tool

    adapter = TeamsMTKAdapter(None)
    matches = [
        c for c in adapter.list_conversations(limit=200)
        if str(c.get("id") or "") == DM_CHAT_ID
    ]
    title = next(
        (
            str(c.get("title") or "").strip()
            for c in matches
            if len(str(c.get("title") or "").strip()) >= 4
        ),
        "",
    )
    if not title:
        return False, "control DM has no usable dynamic title for contact routing"

    resolved = adapter._find_conv_by_display_name(title)
    if resolved != DM_CHAT_ID:
        return False, "display-name resolver did not resolve the control DM"

    marker = f"E2E_AUTO contact routing {int(time.time())}"
    runner = SimpleNamespace(adapters={Platform.TEAMS_MTK: adapter})
    result = None
    try:
        with patch("gateway.run._gateway_runner_ref", return_value=runner):
            raw_result = send_message_tool({
                "action": "send",
                "target": f"teams_mtk:contact:{title}",
                "message": marker,
            })
        result = _json.loads(raw_result)
        if not result.get("success"):
            return False, f"contact route send failed: {result!r}"
        message_id = str(result.get("message_id") or "")
        if not message_id:
            return False, f"contact route returned no message id: {result!r}"

        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                marker_visible = _exact_message_contains_marker(
                    DM_CHAT_ID,
                    message_id,
                    marker,
                )
            except RuntimeError:
                marker_visible = False
            if marker_visible:
                title_hash = hashlib.sha256(title.encode("utf-8")).hexdigest()[:10]
                return True, (
                    f"contact title hash={title_hash} resolved to control DM; "
                    "exact sent identity and marker read back"
                )
            time.sleep(2)
        return False, "contact route exact identity/marker not found in MSG read-back"
    finally:
        message_id = str((result or {}).get("message_id") or "")
        if message_id:
            try:
                asyncio.run(adapter.delete_message_safe(DM_CHAT_ID, message_id))
            except Exception:
                pass


def test_contact_directory_fallback(log_path: str, baseline: int) -> tuple[bool, str]:
    """G13-B.2/B.4: real directory lookup enriches a safe no-chat error.

    Select a directory contact dynamically so no person's identity is stored in
    the repository. The candidate must exist in the live M365 People API but
    not in the account's existing Teams conversations. The contact route must
    then return the canonical directory name and manual-open guidance without
    invoking any sender or attempting to create a chat.
    """
    del log_path, baseline
    import hashlib
    import json as _json
    from types import SimpleNamespace
    from unittest.mock import patch

    from gateway.config import Platform
    from gateway.platforms.teams_mtk import TeamsMTKAdapter
    from tools.send_message_tool import send_message_tool

    adapter = TeamsMTKAdapter(None)
    conversations = adapter.list_conversations(limit=200)
    if not conversations:
        return False, "list_conversations returned [] — cannot prove directory fallback boundary"

    directory_people = []
    seen_people = set()
    for prefix in ("A", "M", "L", "C", "S", "J", "W", "H"):
        for person in adapter._search_users(prefix):
            if not isinstance(person, dict):
                continue
            stable_ref = str(person.get("oid") or person.get("email") or "").strip()
            if not stable_ref or stable_ref in seen_people:
                continue
            seen_people.add(stable_ref)
            directory_people.append(person)
        if len(directory_people) >= 40:
            break
    if not directory_people:
        return False, "live Teams Graph directory search returned no candidates"

    def _matches_existing_conversation(name: str) -> bool:
        needle = name.lower()
        return any(
            needle in str(conv.get("title") or "").lower()
            or needle in str(conv.get("member_names") or "").lower()
            for conv in conversations
        )

    candidate = ""
    canonical_name = ""
    for person in directory_people:
        name = str(person.get("display_name") or "").strip()
        if len(name) < 4 or _matches_existing_conversation(name):
            continue
        matches = adapter._search_users(name)
        if not matches:
            continue
        canonical = str(matches[0].get("display_name") or "").strip()
        if canonical:
            candidate = name
            canonical_name = canonical
            break

    if not candidate:
        return False, (
            "no dynamic directory contact outside existing conversations; "
            f"conversations={len(conversations)} candidates={len(directory_people)}"
        )

    runner = SimpleNamespace(adapters={Platform.TEAMS_MTK: adapter})
    with patch("gateway.run._gateway_runner_ref", return_value=runner), patch(
        "tools.send_message_tool._send_via_adapter",
        side_effect=AssertionError("directory-only fallback attempted to send"),
    ) as send_mock:
        raw_result = send_message_tool({
            "action": "send",
            "target": f"teams_mtk:contact:{candidate}",
            "message": f"E2E_AUTO contact directory fallback {time.time_ns()}",
        })

    result = _json.loads(raw_result)
    error = str(result.get("error") or "")
    if not error:
        return False, "directory-only contact unexpectedly returned success"
    if "found in directory as" not in error or canonical_name not in error:
        return False, "contact error was not enriched with the live canonical directory name"
    if "Open a 1:1 chat" not in error:
        return False, "contact error omitted the manual-open guidance required without Chat.Create"
    if send_mock.call_count:
        return False, f"directory-only fallback invoked sender {send_mock.call_count} time(s)"

    candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:10]
    canonical_hash = hashlib.sha256(canonical_name.encode("utf-8")).hexdigest()[:10]
    return True, (
        f"directory candidate={candidate_hash} canonical={canonical_hash}; "
        f"conversations={len(conversations)}; enriched error; sender calls=0"
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
    result = None
    message_id = ""
    try:
        result = asyncio.run(fn(None, DM_CHAT_ID, marker))
        if isinstance(result, dict):
            message_id = str(result.get("message_id") or "")
        if not isinstance(result, dict) or not result.get("success"):
            return False, (
                f"standalone sender returned failure: type={type(result).__name__}, "
                f"success={result.get('success') if isinstance(result, dict) else None}"
            )
        if not message_id:
            return False, "standalone sender returned success without a canonical message ID"

        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                marker_present = _exact_message_contains_marker(
                    DM_CHAT_ID,
                    message_id,
                    marker,
                )
            except RuntimeError:
                marker_present = False
            if marker_present:
                import hashlib
                id_hash = hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:10]
                return True, (
                    f"standalone sender delivered and read back marker; "
                    f"message_hash={id_hash}; {checks}"
                )
            time.sleep(2)
        return False, (
            "standalone sender returned success but marker was not present in "
            f"real Teams read-back; has_message_id={bool(message_id)}"
        )
    finally:
        if not message_id:
            # A malformed/failure result can still have sent the marker. Find
            # the side effect before cleanup without leaking message content.
            cleanup_deadline = time.time() + 10
            while time.time() < cleanup_deadline and not message_id:
                try:
                    messages = get_messages_raw(DM_CHAT_ID, page_size=30)
                except Exception:
                    messages = []
                marker_msg = next(
                    (
                        msg for msg in messages
                        if marker in str(
                            msg.get("_raw_content")
                            or msg.get("content")
                            or msg.get("body")
                            or ""
                        )
                    ),
                    None,
                )
                message_id = str((marker_msg or {}).get("id") or "")
                if not message_id:
                    time.sleep(1)
        if message_id:
            from gateway.platforms.teams_mtk import TeamsMTKAdapter
            cleanup = asyncio.run(TeamsMTKAdapter(None).delete_message(DM_CHAT_ID, message_id))
            if cleanup.get("status") != "deleted":
                raise RuntimeError(
                    f"standalone sender cleanup failed: status={cleanup.get('status')}"
                )


def _busy_burst_requires_mention() -> bool:
    """Return the effective mention policy for the live control group."""
    from hermes_cli.config import load_config

    config = load_config()
    teams_config = config.get("gateway", {}).get("teams_mtk", {})
    groups = teams_config.get("groups", {})
    group_config = groups.get(GROUP_CHAT_ID, {}) if isinstance(groups, dict) else {}
    return bool(
        group_config.get("require_mention", teams_config.get("require_mention", True))
    )


def _address_busy_burst_prompt(content: str, *, require_mention: bool) -> str:
    """Address a control-group prompt when the live policy requires it."""
    if not require_mention:
        return content
    return f'<at id="0">Hermes</at>&nbsp;{content}'


def _busy_burst_preconditions() -> tuple[bool, str]:
    """Verify this runner and the live gateway use the intended checkout/config."""
    import psutil

    from hermes_cli.config import load_config
    from hermes_constants import get_hermes_home

    config = load_config()
    busy_mode = str(config.get("display", {}).get("busy_input_mode") or "")
    require_mention = _busy_burst_requires_mention()
    if busy_mode != "interrupt":
        return False, f"display.busy_input_mode={busy_mode!r}, expected 'interrupt'"

    pid_path = get_hermes_home() / "gateway.pid"
    if not pid_path.is_file():
        return False, "gateway.pid is missing"
    try:
        raw_pid = pid_path.read_text(encoding="utf-8").strip()
        try:
            pid_metadata = json.loads(raw_pid)
            pid = int(pid_metadata.get("pid", 0))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            pid_metadata = {}
            pid = int(raw_pid)
        process = psutil.Process(pid)
        gateway_cwd = os.path.normcase(os.path.realpath(process.cwd()))
        gateway_executable = os.path.normcase(os.path.realpath(process.exe()))
        gateway_environment = process.environ()
    except (OSError, ValueError, psutil.Error) as exc:
        return False, f"gateway process check failed ({type(exc).__name__})"

    repo_root = os.path.normcase(
        os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    )
    runner_executable = os.path.normcase(os.path.realpath(sys.executable))
    expected_entry = os.path.join(repo_root, "hermes_cli", "gateway_runtime_entry.py")
    recorded_argv = pid_metadata.get("argv") or []
    recorded_entry = os.path.normcase(
        os.path.realpath(str(recorded_argv[0]))
    ) if recorded_argv else ""
    pythonpath_entries = {
        os.path.normcase(os.path.realpath(entry))
        for entry in str(gateway_environment.get("PYTHONPATH") or "").split(os.pathsep)
        if entry
    }
    configured_venv = os.path.normcase(
        os.path.realpath(str(gateway_environment.get("VIRTUAL_ENV") or ""))
    )
    runner_venv = os.path.dirname(os.path.dirname(runner_executable))
    source_matches = recorded_entry == expected_entry and (
        gateway_cwd == repo_root or repo_root in pythonpath_entries
    )
    interpreter_matches = (
        os.path.dirname(gateway_executable) == os.path.dirname(runner_executable)
        or configured_venv == runner_venv
    )
    if not source_matches:
        return False, "live gateway source does not match this checkout"
    if not interpreter_matches:
        return False, "live gateway does not use this runner's venv"
    return (
        True,
        f"gateway pid={pid}; source=gateway_runtime_entry.py; checkout=current; "
        f"interpreter={os.path.basename(gateway_executable)}; venv=current; "
        "config=interrupt/"
        + ("mention-required" if require_mention else "implicit-addressing"),
    )


def _wait_for_process_marker(
    marker: str,
    *,
    timeout: float,
    poll_interval: float,
) -> bool:
    """Wait until the model's requested long terminal command is truly running."""
    import psutil

    deadline = time.monotonic() + timeout
    while True:
        for process in psutil.process_iter(["cmdline"]):
            try:
                command_line = " ".join(process.info.get("cmdline") or [])
            except (OSError, psutil.Error):
                continue
            if marker in command_line:
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval)


def _is_hermes_bot_message(message: dict) -> bool:
    rendered = str(message.get("_raw_content") or message.get("content") or "")
    sender_marker = ""
    for candidate in (
        message.get("properties"),
        message.get("_raw_properties"),
    ):
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                candidate = {}
        if isinstance(candidate, dict):
            sender_marker = str(candidate.get("hermes_sender") or "")
        if sender_marker:
            break
    return (
        ("🤖 Hermes" in rendered and "— Hermes ·" in rendered)
        or sender_marker in {"agent", "bot"}
    )


def test_same_id_edit_reopens_exactly_one_revised_query(
    log_path: str,
    baseline: int,
    *,
    reply_timeout: float = 300,
    poll_interval: float = 3,
    settle_seconds: float = 12,
) -> tuple[bool, str]:
    """Edit one Graph query in place and prove one complete revised turn."""
    del log_path, baseline
    token = uuid.uuid4().hex[:12].upper()
    prefix = f"E2EEDIT{token}"
    reset_marker = f"{prefix}RESET"
    original_marker = f"{prefix}ORIGINAL"
    revised_body = f"{prefix}REVISEDA|{prefix}REVISEDB"
    initial_prompt = (
        f"Reply with exactly {original_marker}. Do not add other text or use tools."
    )
    revised_prompt = (
        f"Reply with exactly {revised_body}. Do not add other text or use tools."
    )

    graph_message_ids: list[str] = []
    cleanup_message_ids: set[str] = set()
    try:
        baseline_messages = get_messages_raw(DM_CHAT_ID, page_size=50)
        baseline_ids = {
            str(message.get("id") or "")
            for message in baseline_messages
            if message.get("id")
        }

        reset_id = send_chat_message(DM_CHAT_ID, f"/new {reset_marker}")
        if reset_id:
            graph_message_ids.append(str(reset_id))
        deadline = time.monotonic() + reply_timeout
        while True:
            latest = get_messages_raw(DM_CHAT_ID, page_size=50)
            reset_replies = [
                message
                for message in latest
                if str(message.get("id") or "") not in baseline_ids
                and _is_hermes_bot_message(message)
                and reset_marker in _visible_model_body(message)
            ]
            if reset_replies:
                cleanup_message_ids.update(
                    str(message.get("id") or "") for message in reset_replies
                )
                break
            if time.monotonic() >= deadline:
                return False, "reset_ack=False; revised_dispatch=0"
            time.sleep(poll_interval)

        pre_query_messages = get_messages_raw(DM_CHAT_ID, page_size=50)
        pre_query_ids = {
            str(message.get("id") or "")
            for message in pre_query_messages
            if message.get("id")
        }
        query_graph_id = send_chat_message(DM_CHAT_ID, initial_prompt)
        if query_graph_id:
            graph_message_ids.append(str(query_graph_id))

        deadline = time.monotonic() + reply_timeout
        while True:
            latest = get_messages_raw(DM_CHAT_ID, page_size=50)
            original_replies = [
                message
                for message in latest
                if str(message.get("id") or "") not in pre_query_ids
                and _is_hermes_bot_message(message)
                and _has_exact_visible_marker(message, original_marker)
            ]
            if len(original_replies) == 1:
                cleanup_message_ids.add(str(original_replies[0].get("id") or ""))
                break
            if time.monotonic() >= deadline:
                return (
                    False,
                    f"initial_dispatch={len(original_replies)}; revised_dispatch=0",
                )
            time.sleep(poll_interval)

        pre_edit_messages = get_messages_raw(DM_CHAT_ID, page_size=50)
        pre_edit_ids = {
            str(message.get("id") or "")
            for message in pre_edit_messages
            if message.get("id")
        }
        original_queries = [
            message
            for message in pre_edit_messages
            if not _is_hermes_bot_message(message)
            and original_marker in _visible_model_body(message)
            and message.get("id")
        ]
        if len(original_queries) != 1:
            return False, f"canonical_original_count={len(original_queries)}"
        canonical_query_id = str(original_queries[0]["id"])

        edit_msg_message(DM_CHAT_ID, canonical_query_id, revised_prompt)
        deadline = time.monotonic() + reply_timeout
        while True:
            latest = get_messages_raw(DM_CHAT_ID, page_size=50)
            revised_queries = [
                message
                for message in latest
                if str(message.get("id") or "") == canonical_query_id
                and _visible_model_body(message) == revised_prompt
            ]
            revised_replies = [
                message
                for message in latest
                if str(message.get("id") or "") not in pre_edit_ids
                and _is_hermes_bot_message(message)
                and _has_exact_visible_marker(message, revised_body)
            ]
            if revised_queries and revised_replies:
                cleanup_message_ids.update(
                    str(message.get("id") or "") for message in revised_replies
                )
                break
            if time.monotonic() >= deadline:
                return (
                    False,
                    "same_identity="
                    f"{bool(revised_queries)}; revised_dispatch={len(revised_replies)}",
                )
            time.sleep(poll_interval)

        time.sleep(settle_seconds)
        final_messages = get_messages_raw(DM_CHAT_ID, page_size=50)
        canonical_matches = [
            message
            for message in final_messages
            if str(message.get("id") or "") == canonical_query_id
            and _visible_model_body(message) == revised_prompt
        ]
        new_bot_messages = [
            message
            for message in final_messages
            if str(message.get("id") or "") not in pre_edit_ids
            and _is_hermes_bot_message(message)
        ]
        revised_replies = [
            message
            for message in new_bot_messages
            if _has_exact_visible_marker(message, revised_body)
        ]
        original_replays = [
            message
            for message in new_bot_messages
            if original_marker in _visible_model_body(message)
        ]
        cleanup_message_ids.update(
            str(message.get("id") or "")
            for message in new_bot_messages
            if message.get("id")
        )

        revised_dispatches = len(revised_replies)
        duplicate_dispatches = max(0, revised_dispatches - 1)
        complete_body_match = len(canonical_matches) == 1
        if (
            not complete_body_match
            or revised_dispatches != 1
            or original_replays
        ):
            return (
                False,
                f"same_identity={complete_body_match}; complete_body={complete_body_match}; "
                f"revised_dispatch={revised_dispatches}; "
                f"duplicate_dispatch={duplicate_dispatches}; "
                f"original_replay={len(original_replays)}",
            )
        return (
            True,
            "same_identity=True; complete_body=True; revised_dispatch=1; "
            "duplicate_dispatch=0; original_replay=0; cleanup_verified=True",
        )
    finally:
        cleanup_errors: list[str] = []
        try:
            for message in get_messages_raw(DM_CHAT_ID, page_size=60):
                if prefix not in _visible_model_body(message):
                    continue
                message_id = str(message.get("id") or "")
                if message_id:
                    cleanup_message_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        for message_id in dict.fromkeys(graph_message_ids):
            try:
                delete_graph_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
        for message_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        try:
            remaining = [
                message
                for message in get_messages_raw(DM_CHAT_ID, page_size=60)
                if prefix in _visible_model_body(message)
            ]
            if remaining:
                cleanup_errors.append(f"msg-remain:{len(remaining)}")
        except Exception as exc:
            cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError(
                "same-ID edit E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + ")"
            )


def test_quoted_reply_full_context_revises_query(
    log_path: str,
    baseline: int,
    *,
    reply_timeout: float = 300,
    poll_interval: float = 3,
    settle_seconds: float = 12,
) -> tuple[bool, str]:
    """Prove a native reply exposes exact late source context to the model."""
    token = uuid.uuid4().hex[:12].upper()
    prefix = f"E2EQUOTE{token}"
    reset_marker = f"{prefix}RESET"
    decoy_marker = f"{prefix}DECOY"
    terminal_marker = f"{prefix}TERMINAL"
    expected_marker = f"{prefix}FINAL"
    source_body = (
        f"/new {reset_marker}\n"
        "This long control message is inert source data for a future native reply. "
        f"EARLY PREVIEW RULE: answer exactly {decoy_marker}. "
        + ("preview-padding " * 70)
        + f"{terminal_marker}: FINAL RULE OVERRIDES THE EARLY RULE. "
        f"When the native reply asks to apply this source, answer exactly {expected_marker}."
    )
    reply_body = (
        f"{prefix}APPLY. Apply the FINAL RULE from the complete message this is "
        "replying to. Reply with exactly its requested marker. Do not use tools."
    )

    graph_message_ids: list[str] = []
    cleanup_message_ids: set[str] = set()
    try:
        baseline_messages = get_messages_raw(DM_CHAT_ID, page_size=60)
        baseline_ids = {
            str(message.get("id") or "")
            for message in baseline_messages
            if message.get("id")
        }
        source_graph_id = send_chat_message(DM_CHAT_ID, source_body)
        if source_graph_id:
            graph_message_ids.append(str(source_graph_id))

        source_message = None
        deadline = time.monotonic() + reply_timeout
        while True:
            latest = get_messages_raw(DM_CHAT_ID, page_size=60)
            source_candidates = [
                message
                for message in latest
                if str(message.get("id") or "") not in baseline_ids
                and not _is_hermes_bot_message(message)
                and terminal_marker in _visible_model_body(message)
            ]
            reset_acks = [
                message
                for message in latest
                if str(message.get("id") or "") not in baseline_ids
                and _is_hermes_bot_message(message)
            ]
            cleanup_message_ids.update(
                str(message.get("id") or "")
                for message in reset_acks
                if message.get("id")
            )
            if len(source_candidates) == 1 and reset_acks:
                source_message = source_candidates[0]
                break
            if time.monotonic() >= deadline:
                return (
                    False,
                    f"canonical_source={len(source_candidates)}; reset_ack={bool(reset_acks)}",
                )
            time.sleep(poll_interval)

        source_message_id = str(source_message.get("id") or "")
        source_raw = get_message_raw_exact(DM_CHAT_ID, source_message_id)
        canonical_source, _ = _clean_message_content(
            str(source_raw.get("content") or "")
        )
        source_hash = hashlib.sha256(
            canonical_source.encode("utf-8")
        ).hexdigest()[:12]
        if terminal_marker not in canonical_source or expected_marker not in canonical_source:
            return False, "exact_source_missing_terminal=True"

        pre_reply_messages = get_messages_raw(DM_CHAT_ID, page_size=60)
        pre_reply_ids = {
            str(message.get("id") or "")
            for message in pre_reply_messages
            if message.get("id")
        }
        native_reply_id = send_native_user_reply(
            DM_CHAT_ID,
            source_message_id,
            reply_body,
        )
        cleanup_message_ids.add(native_reply_id)

        deadline = time.monotonic() + reply_timeout
        while True:
            latest = get_messages_raw(DM_CHAT_ID, page_size=60)
            final_replies = [
                message
                for message in latest
                if str(message.get("id") or "") not in pre_reply_ids
                and _is_hermes_bot_message(message)
                and _has_exact_visible_marker(message, expected_marker)
            ]
            cleanup_message_ids.update(
                str(message.get("id") or "")
                for message in final_replies
                if message.get("id")
            )
            if final_replies:
                break
            if time.monotonic() >= deadline:
                decoy_replies = [
                    message
                    for message in latest
                    if str(message.get("id") or "") not in pre_reply_ids
                    and _is_hermes_bot_message(message)
                    and decoy_marker in _visible_model_body(message)
                ]
                return (
                    False,
                    f"terminal_reply=0; preview_decoy_reply={len(decoy_replies)}",
                )
            time.sleep(poll_interval)

        time.sleep(settle_seconds)
        final_messages = get_messages_raw(DM_CHAT_ID, page_size=60)
        new_bot_messages = [
            message
            for message in final_messages
            if str(message.get("id") or "") not in pre_reply_ids
            and _is_hermes_bot_message(message)
        ]
        terminal_replies = [
            message
            for message in new_bot_messages
            if _has_exact_visible_marker(message, expected_marker)
        ]
        decoy_replies = [
            message
            for message in new_bot_messages
            if decoy_marker in _visible_model_body(message)
        ]
        cleanup_message_ids.update(
            str(message.get("id") or "")
            for message in new_bot_messages
            if message.get("id")
        )

        reply_raw = get_message_raw_exact(DM_CHAT_ID, native_reply_id)
        raw_properties = reply_raw.get("properties") or {}
        if isinstance(raw_properties, str):
            try:
                raw_properties = json.loads(raw_properties)
            except (json.JSONDecodeError, TypeError):
                raw_properties = {}
        quoted_messages = raw_properties.get("qtdMsgs") or []
        if isinstance(quoted_messages, str):
            try:
                quoted_messages = json.loads(quoted_messages)
            except (json.JSONDecodeError, TypeError):
                quoted_messages = []
        quoted_ids = {
            str(item.get("messageId") or item.get("id") or "")
            for item in quoted_messages
            if isinstance(item, dict)
        }
        reply_soup = BeautifulSoup(
            str(reply_raw.get("content") or ""),
            "html.parser",
        )
        reply_quote = reply_soup.find(
            "blockquote",
            attrs={"itemtype": "http://schema.skype.com/Reply"},
        )
        blockquote_id = str(reply_quote.get("itemid") or "") if reply_quote else ""
        preview_node = (
            reply_quote.find(True, attrs={"itemprop": "preview"})
            if reply_quote is not None
            else None
        )
        preview_text = preview_node.get_text(" ", strip=True) if preview_node else ""
        relation_match = (
            str(raw_properties.get("replyChainMessageId") or "")
            == source_message_id
            and quoted_ids == {source_message_id}
            and blockquote_id == source_message_id
        )
        preview_only = terminal_marker in preview_text or expected_marker in preview_text

        source_raw_again = get_message_raw_exact(DM_CHAT_ID, source_message_id)
        canonical_source_again, _ = _clean_message_content(
            str(source_raw_again.get("content") or "")
        )
        full_source_hash_match = (
            hashlib.sha256(canonical_source_again.encode("utf-8")).hexdigest()[:12]
            == source_hash
        )
        new_log = tail_log(log_path, baseline)
        fetch_log_match = (
            "reply source fetch succeeded" in new_log
            and f"hash={source_hash}" in new_log
        )

        if (
            not relation_match
            or not full_source_hash_match
            or preview_only
            or not fetch_log_match
            or len(terminal_replies) != 1
            or decoy_replies
        ):
            return (
                False,
                f"relation_match={relation_match}; "
                f"full_source_hash_match={full_source_hash_match}; "
                f"preview_only={preview_only}; fetch_log_match={fetch_log_match}; "
                f"terminal_reply={len(terminal_replies)}; "
                f"preview_decoy_reply={len(decoy_replies)}",
            )
        return (
            True,
            "relation_match=True; full_source_hash_match=True; "
            "preview_only=False; fetch_log_match=True; terminal_reply=1; "
            "cleanup_verified=True",
        )
    finally:
        cleanup_errors: list[str] = []
        try:
            for message in get_messages_raw(DM_CHAT_ID, page_size=70):
                if prefix not in _visible_model_body(message):
                    continue
                message_id = str(message.get("id") or "")
                if message_id:
                    cleanup_message_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        for message_id in dict.fromkeys(graph_message_ids):
            try:
                delete_graph_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
        for message_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(DM_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        try:
            remaining = [
                message
                for message in get_messages_raw(DM_CHAT_ID, page_size=70)
                if prefix in _visible_model_body(message)
            ]
            if remaining:
                cleanup_errors.append(f"msg-remain:{len(remaining)}")
        except Exception as exc:
            cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError(
                "quoted reply E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + ")"
            )


def _busy_burst_group_idle_preflight(
    *,
    timeout: float = 45,
    poll_interval: float = 3,
) -> tuple[bool, str, set[str]]:
    """Fail fast without disturbing an unrelated active turn in the test group."""
    from agent.i18n import t

    baseline_messages = get_messages_raw(GROUP_CHAT_ID, page_size=40)
    baseline_ids = {
        str(message.get("id") or "")
        for message in baseline_messages
        if message.get("id")
    }
    graph_message_id = ""
    status_message_ids: set[str] = set()
    try:
        graph_message_id = send_chat_message(GROUP_CHAT_ID, "/status")
        status_header = t("gateway.status.header")
        idle_line = t(
            "gateway.status.agent_running",
            state=t("gateway.status.state_no"),
        )
        running_line = t(
            "gateway.status.agent_running",
            state=t("gateway.status.state_yes"),
        )
        deadline = time.monotonic() + timeout
        while True:
            latest_messages = get_messages_raw(GROUP_CHAT_ID, page_size=40)
            for message in latest_messages:
                message_id = str(message.get("id") or "")
                if (
                    not message_id
                    or message_id in baseline_ids
                    or not _is_hermes_bot_message(message)
                ):
                    continue
                body = _visible_model_body(message)
                if status_header not in body:
                    continue
                status_message_ids.add(message_id)
                if running_line in body:
                    return (
                        False,
                        "control group already has an active agent turn",
                        set(status_message_ids),
                    )
                if idle_line in body:
                    return True, "control group idle", set(status_message_ids)
            if time.monotonic() >= deadline:
                return (
                    False,
                    "timed out reading the control group's /status response",
                    set(status_message_ids),
                )
            time.sleep(poll_interval)
    finally:
        cleanup_errors = []
        if graph_message_id:
            try:
                delete_graph_message(GROUP_CHAT_ID, graph_message_id)
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
        for message_id in sorted(status_message_ids):
            try:
                delete_msg_message(GROUP_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError(
                "busy burst status cleanup failed (" + ", ".join(cleanup_errors) + ")"
            )


def test_busy_group_burst_redirect(
    log_path: str,
    baseline: int,
    *,
    tool_start_timeout: float = 240,
    reply_timeout: float = 300,
    poll_interval: float = 3,
    settle_seconds: float = 12,
) -> tuple[bool, str]:
    """Group burst: one redirect, both corrections in one final, no stale output.

    The initial turn must enter a real long-running terminal process before two
    same-sender Graph messages are released together. MSG read-back then proves
    that Teams rendered exactly one redirect acknowledgement and one final card,
    that both correction markers survived, and that the stale marker did not.
    """
    del log_path, baseline
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    preconditions_ok, runtime_evidence = _busy_burst_preconditions()
    if not preconditions_ok:
        return False, runtime_evidence
    idle_ok, idle_evidence, preflight_message_ids = _busy_burst_group_idle_preflight(
        timeout=min(45, tool_start_timeout),
        poll_interval=poll_interval,
    )
    if not idle_ok:
        return False, idle_evidence

    # Keep markers strictly alphanumeric. ``strip_teams_html`` escapes
    # underscores as Markdown, so an underscore would create a false mismatch.
    token = uuid.uuid4().hex[:12].upper()
    prefix = f"E2EBURST{token}"
    tool_marker = f"{prefix}TOOL"
    old_marker = f"{prefix}OLD"
    marker_a = f"{prefix}A"
    marker_b = f"{prefix}B"
    initial_prompt = (
        "E2E busy burst verification. Use the terminal tool exactly once to run "
        f"venv/Scripts/python.exe -c \"import time; print('{tool_marker}', "
        f"flush=True); time.sleep(45); print('{old_marker}', flush=True)\". "
        f"Do not use another tool. After it finishes, reply with exactly {old_marker}."
    )
    corrections = (
        f"Correction A: include exactly {marker_a} in the final reply and do not output {old_marker}.",
        f"Correction B: include exactly {marker_b} in the final reply and do not output {old_marker}.",
    )
    require_mention = _busy_burst_requires_mention()
    initial_prompt = _address_busy_burst_prompt(
        initial_prompt,
        require_mention=require_mention,
    )
    corrections = tuple(
        _address_busy_burst_prompt(content, require_mention=require_mention)
        for content in corrections
    )

    graph_message_ids: list[str] = []
    bot_message_ids: set[str] = set()
    try:
        baseline_messages = get_messages_raw(GROUP_CHAT_ID, page_size=40)
        baseline_ids = {
            str(message.get("id") or "")
            for message in baseline_messages
            if message.get("id")
        }
        # MSG read-back is eventually consistent after deletion.  Keep the
        # preflight /status card excluded even if it briefly disappears from
        # the baseline page and reappears while the live assertion is polling.
        baseline_ids.update(preflight_message_ids)
        graph_message_ids.append(send_chat_message(GROUP_CHAT_ID, initial_prompt))
        if not _wait_for_process_marker(
            tool_marker,
            timeout=tool_start_timeout,
            poll_interval=poll_interval,
        ):
            return False, "long terminal process marker was never observed"

        release = threading.Barrier(len(corrections) + 1)

        def send_correction(content: str) -> str:
            release.wait()
            return send_chat_message(GROUP_CHAT_ID, content)

        with ThreadPoolExecutor(max_workers=len(corrections)) as executor:
            futures = [executor.submit(send_correction, content) for content in corrections]
            release.wait()
            for future in as_completed(futures):
                graph_message_ids.append(future.result())

        latest_messages: list[dict] = []
        deadline = time.monotonic() + reply_timeout
        while True:
            latest_messages = get_messages_raw(GROUP_CHAT_ID, page_size=40)
            new_bot_messages = [
                message
                for message in latest_messages
                if str(message.get("id") or "") not in baseline_ids
                and _is_hermes_bot_message(message)
            ]
            bot_message_ids.update(
                str(message.get("id") or "")
                for message in new_bot_messages
                if message.get("id")
            )
            visible_bodies = [_visible_model_body(message) for message in new_bot_messages]
            if any(marker_a in body and marker_b in body for body in visible_bodies):
                break
            if time.monotonic() >= deadline:
                return (
                    False,
                    "no final Teams bot card contained both burst correction markers "
                    f"(new bot cards={len(new_bot_messages)})",
                )
            time.sleep(poll_interval)

        time.sleep(settle_seconds)
        latest_messages = get_messages_raw(GROUP_CHAT_ID, page_size=40)
        new_bot_by_id = {
            str(message.get("id") or ""): message
            for message in latest_messages
            if str(message.get("id") or "") not in baseline_ids
            and message.get("id")
            and _is_hermes_bot_message(message)
        }
        bot_message_ids.update(new_bot_by_id)
        visible_by_id = {
            message_id: _visible_model_body(message)
            for message_id, message in new_bot_by_id.items()
        }
        acknowledgements = [
            message_id
            for message_id, body in visible_by_id.items()
            if "redirected current run" in body.lower()
        ]
        finals = [
            message_id
            for message_id, body in visible_by_id.items()
            if marker_a in body and marker_b in body
        ]
        if len(acknowledgements) != 1:
            return False, f"expected one redirect acknowledgement, got {len(acknowledgements)}"
        if len(finals) != 1:
            return False, f"expected one final card with A+B, got {len(finals)}"
        expected_ids = {acknowledgements[0], finals[0]}
        extra_ids = set(new_bot_by_id) - expected_ids
        progress_ids = {
            message_id
            for message_id in extra_ids
            if "running" in visible_by_id[message_id].lower()
            and prefix not in visible_by_id[message_id]
        }
        if len(extra_ids) > 1 or progress_ids != extra_ids:
            diagnostics = [
                {
                    "chars": len(body),
                    "ack": "redirected current run" in body.lower(),
                    "final": marker_a in body and marker_b in body,
                    "old": old_marker in body,
                    "marker": prefix in body,
                    "terminal": "terminal" in body.lower(),
                    "tool": "tool" in body.lower(),
                    "running": "running" in body.lower(),
                    "completed": "completed" in body.lower(),
                    "thinking": "thinking" in body.lower(),
                }
                for body in visible_by_id.values()
            ]
            return (
                False,
                "expected ack+final and at most one standard running progress "
                f"card, got {len(new_bot_by_id)} bot cards; "
                f"classes={json.dumps(diagnostics, ensure_ascii=True)}",
            )
        if old_marker in visible_by_id[finals[0]]:
            return False, "stale OLD marker leaked into the final reply"

        final_runtime_ok, final_runtime_evidence = _busy_burst_preconditions()
        if not final_runtime_ok:
            return False, f"post-test runtime check failed: {final_runtime_evidence}"
        return (
            True,
            "one redirect acknowledgement + one final Teams card; "
            f"progress cards={len(progress_ids)}; A+B present; OLD absent; "
            f"{idle_evidence}; {runtime_evidence}; "
            f"post={final_runtime_evidence}",
        )
    finally:
        cleanup_errors = []
        for message_id in graph_message_ids:
            try:
                delete_graph_message(GROUP_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"graph:{type(exc).__name__}")
        msg_cleanup_ids = set(bot_message_ids)
        try:
            for message in get_messages_raw(GROUP_CHAT_ID, page_size=60):
                rendered = str(
                    message.get("_raw_content")
                    or message.get("content")
                    or ""
                )
                message_id = str(message.get("id") or "")
                if message_id and prefix in rendered:
                    msg_cleanup_ids.add(message_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-read:{type(exc).__name__}")
        for message_id in sorted(msg_cleanup_ids):
            try:
                delete_msg_message(GROUP_CHAT_ID, message_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")
        try:
            remaining = [
                message
                for message in get_messages_raw(GROUP_CHAT_ID, page_size=60)
                if prefix
                in str(
                    message.get("_raw_content")
                    or message.get("content")
                    or ""
                )
            ]
            if remaining:
                cleanup_errors.append(f"msg-remain:{len(remaining)}")
        except Exception as exc:
            cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
        if cleanup_errors:
            raise RuntimeError(
                "busy burst E2E cleanup failed (" + ", ".join(cleanup_errors) + ")"
            )


def test_reply_to_native_thread_roundtrip(
    log_path: str,
    baseline: int,
    *,
    reply_timeout: float = 90,
    poll_interval: float = 2,
    settle_seconds: float = 5,
) -> tuple[bool, str]:
    """Prove outbound reply relation, permitted flat degradation, and no duplicate."""
    del log_path, baseline
    import io
    import logging
    from unittest.mock import patch

    import gateway.platforms.teams_mtk as teams_mtk_module
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    token = uuid.uuid4().hex[:12].upper()
    prefix = f"E2EOUTREPLY{token}"
    target_marker = f"{prefix}TARGET"
    native_marker = f"{prefix}NATIVE"
    flat_marker = f"{prefix}FLAT"
    uncertain_marker = f"{prefix}UNCERTAIN"
    target_body = (
        f"{target_marker} Controlled source message with enough visible text "
        "to verify the native quoted-message relation."
    )
    native_body = (
        f"{native_marker} Controlled Hermes reply that must preserve the "
        "native relation."
    )
    adapter = TeamsMTKAdapter(None)
    adapter._auth = _get_gateway_auth()
    cleanup_message_ids: set[str] = set()
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    teams_mtk_module.logger.addHandler(log_handler)

    def message_id(message: dict) -> str:
        return str(
            message.get("id")
            or message.get("OriginalArrivalTime")
            or message.get("originalarrivaltime")
            or ""
        )

    def rendered(message: dict) -> str:
        return str(message.get("_raw_content") or message.get("content") or "")

    def marker_messages(
        messages: list[dict],
        marker: str,
        *,
        exclude_ids: set[str],
    ) -> list[dict]:
        return [
            message
            for message in messages
            if message_id(message)
            and message_id(message) not in exclude_ids
            and marker in rendered(message)
        ]

    def wait_for_marker(marker: str, exclude_ids: set[str]) -> list[dict]:
        deadline = time.monotonic() + reply_timeout
        latest: list[dict] = []
        while True:
            latest = marker_messages(
                get_messages_raw(DM_CHAT_ID, page_size=70),
                marker,
                exclude_ids=exclude_ids,
            )
            if latest or time.monotonic() >= deadline:
                return latest
            time.sleep(poll_interval)

    def run_scenarios() -> tuple[bool, str]:
        baseline_messages = get_messages_raw(DM_CHAT_ID, page_size=70)
        baseline_ids = {message_id(message) for message in baseline_messages}

        target_result_id = send_via_sdk(DM_CHAT_ID, target_body)
        if target_result_id:
            cleanup_message_ids.add(target_result_id)
        target_messages = wait_for_marker(target_marker, baseline_ids)
        if len(target_messages) != 1:
            return False, f"controlled_target={len(target_messages)}"
        target_message_id = message_id(target_messages[0])
        cleanup_message_ids.add(target_message_id)
        if target_result_id and target_result_id != target_message_id:
            return False, "controlled_target_identity_match=False"

        before_native = {
            message_id(message)
            for message in get_messages_raw(DM_CHAT_ID, page_size=70)
        }
        native_transport: dict[str, object] = {}
        original_sdk_request = teams_mtk_module._SDKHTTPLayer._request
        original_proxy_init = teams_mtk_module._PinnedReplySourceHTTP.__init__

        def recording_proxy_init(proxy, delegate, page_url, source):
            source_content = str(source.get("content") or "")
            source_soup = BeautifulSoup(source_content, "html.parser")
            native_transport.update(
                {
                    "source_content_chars": len(source_content),
                    "source_contains_marker": target_marker in source_content,
                    "source_tag_names": sorted(
                        {tag.name for tag in source_soup.find_all()}
                    ),
                    "source_visible_chars": len(
                        source_soup.get_text(" ", strip=True)
                    ),
                    "source_sdk_text_chars": len(
                        delegate._extract_text_content(source_content)
                    ),
                }
            )
            original_proxy_init(proxy, delegate, page_url, source)

        def recording_sdk_request(http_layer, method: str, url: str, **kwargs):
            payload = kwargs.get("json")
            is_native_post = (
                method.upper() == "POST"
                and isinstance(payload, dict)
                and native_marker in str(payload.get("content") or "")
            )
            if is_native_post:
                payload_dict = payload if isinstance(payload, dict) else {}
                properties = payload_dict.get("properties") or {}
                quoted_messages = properties.get("qtdMsgs") or []
                if isinstance(quoted_messages, str):
                    try:
                        quoted_messages = json.loads(quoted_messages)
                    except (json.JSONDecodeError, TypeError):
                        quoted_messages = []
                quoted = (
                    quoted_messages[0]
                    if isinstance(quoted_messages, list)
                    and quoted_messages
                    and isinstance(quoted_messages[0], dict)
                    else {}
                )
                transport_content = str(payload_dict.get("content") or "")
                reply_body = transport_content.rsplit("</blockquote>", 1)[-1].strip()
                native_transport.update(
                    {
                        "payload_property_keys": sorted(properties),
                        "chain_matches_target": isinstance(properties, dict)
                        and str(properties.get("replyChainMessageId") or "")
                        == target_message_id,
                        "qtd_has_target": target_message_id
                        in str(properties.get("qtdMsgs") or ""),
                        "content_has_reply_blockquote": (
                            "schema.skype.com/Reply"
                            in transport_content
                        ),
                        "qtd_sender_nonempty": bool(quoted.get("sender")),
                        "qtd_message_nonempty": bool(quoted.get("message")),
                        "reply_body_is_paragraph": reply_body.startswith("<p>"),
                        "regional_post": str(url).startswith(
                            adapter._auth.msg_base.rstrip("/") + "/"
                        ),
                    }
                )
            response = original_sdk_request(http_layer, method, url, **kwargs)
            if is_native_post:
                try:
                    response_keys = (
                        sorted(str(key) for key in response.json())
                        if response is not None
                        else []
                    )
                except Exception:
                    response_keys = []
                native_transport.update(
                    {
                        "response_status": getattr(response, "status_code", None),
                        "response_keys": response_keys,
                    }
                )
            return response

        with (
            patch.object(
                teams_mtk_module._PinnedReplySourceHTTP,
                "__init__",
                recording_proxy_init,
            ),
            patch.object(
                teams_mtk_module._SDKHTTPLayer,
                "_request",
                recording_sdk_request,
            ),
        ):
            native_result = asyncio.run(
                adapter.send(DM_CHAT_ID, native_body, reply_to=target_message_id)
            )
        if native_result.message_id:
            cleanup_message_ids.add(str(native_result.message_id))
        native_messages = wait_for_marker(native_marker, before_native)
        cleanup_message_ids.update(
            message_id(message) for message in native_messages if message_id(message)
        )
        if not native_result.success or len(native_messages) != 1:
            return (
                False,
                f"native_success={native_result.success}; native_count={len(native_messages)}",
            )
        native_reply = native_messages[0]
        if str(native_result.message_id or "") != message_id(native_reply):
            return False, "native_identity_match=False"
        exact_native_reply = get_message_raw_exact(
            DM_CHAT_ID,
            str(native_result.message_id),
        )
        relation_deadline = time.time() + 30
        while (
            target_message_id not in _native_reply_relation_ids(exact_native_reply)
            and time.time() < relation_deadline
        ):
            time.sleep(2)
            exact_native_reply = get_message_raw_exact(
                DM_CHAT_ID,
                str(native_result.message_id),
            )
        native_meta = (
            native_result.raw_response.get("native_reply", {})
            if isinstance(native_result.raw_response, dict)
            else {}
        )
        if (
            target_message_id not in _native_reply_relation_ids(exact_native_reply)
            or native_meta.get("status") != "preserved"
            or native_meta.get("relation_preserved") is not True
        ):
            properties = _raw_message_properties(exact_native_reply)
            property_shapes = {
                str(key): type(value).__name__
                for key, value in properties.items()
                if any(
                    token in str(key).lower()
                    for token in ("reply", "quote", "qtd")
                )
            }
            return (
                False,
                "native_relation=False; "
                f"relation_candidates={len(_native_reply_relation_ids(exact_native_reply))}; "
                f"relation_property_shapes={property_shapes}; "
                f"transport={native_transport}",
            )

        before_flat = {
            message_id(message)
            for message in get_messages_raw(DM_CHAT_ID, page_size=70)
        }
        with patch.object(teams_mtk_module, "_SDK_AVAILABLE", False):
            flat_result = asyncio.run(
                adapter.send(DM_CHAT_ID, flat_marker, reply_to=target_message_id)
            )
        if flat_result.message_id:
            cleanup_message_ids.add(str(flat_result.message_id))
        flat_messages = wait_for_marker(flat_marker, before_flat)
        cleanup_message_ids.update(
            message_id(message) for message in flat_messages if message_id(message)
        )
        flat_meta = (
            flat_result.raw_response.get("native_reply", {})
            if isinstance(flat_result.raw_response, dict)
            else {}
        )
        sanitized_log = log_stream.getvalue()
        leaked_values = (
            DM_CHAT_ID,
            target_message_id,
            target_marker,
            native_marker,
            flat_marker,
        )
        if (
            not flat_result.success
            or len(flat_messages) != 1
            or flat_meta.get("status") != "degraded"
            or flat_meta.get("relation_preserved") is not False
            or target_message_id in _native_reply_relation_ids(flat_messages[0])
            or "native reply unavailable before send" not in sanitized_log
            or any(value and value in sanitized_log for value in leaked_values)
        ):
            return False, f"flat_count={len(flat_messages)}; degraded=False"

        before_uncertain = {
            message_id(message)
            for message in get_messages_raw(DM_CHAT_ID, page_size=70)
        }
        with (
            patch.object(
                adapter,
                "_call_sdk_messages",
                side_effect=TimeoutError("simulated response loss"),
            ) as native_call,
            patch.object(
                requests.Session,
                "post",
                autospec=True,
            ) as flat_post,
        ):
            uncertain_result = asyncio.run(
                adapter.send(
                    DM_CHAT_ID,
                    uncertain_marker,
                    reply_to=target_message_id,
                )
            )
        time.sleep(settle_seconds)
        uncertain_messages = marker_messages(
            get_messages_raw(DM_CHAT_ID, page_size=70),
            uncertain_marker,
            exclude_ids=before_uncertain,
        )
        cleanup_message_ids.update(
            message_id(message)
            for message in uncertain_messages
            if message_id(message)
        )
        uncertain_meta = (
            uncertain_result.raw_response.get("native_reply", {})
            if isinstance(uncertain_result.raw_response, dict)
            else {}
        )
        if (
            uncertain_result.success
            or uncertain_result.retryable
            or native_call.call_count != 1
            or flat_post.call_count != 0
            or uncertain_messages
            or uncertain_meta.get("status") != "uncertain"
            or uncertain_meta.get("relation_preserved", "missing") is not None
        ):
            return (
                False,
                "uncertain_signal=False; "
                f"duplicate={len(uncertain_messages)}; flat_attempts={flat_post.call_count}",
            )
        return (
            True,
            "native_relation=1; flat_count=1; degraded=True; "
            "uncertain=True; duplicate=0",
        )

    functional_result = (False, "scenario_not_started=True")
    cleanup_errors: list[str] = []
    try:
        functional_result = run_scenarios()
    finally:
        teams_mtk_module.logger.removeHandler(log_handler)
        log_handler.close()
        try:
            for message in get_messages_raw(DM_CHAT_ID, page_size=90):
                current_id = message_id(message)
                if (
                    current_id
                    and prefix in rendered(message)
                    and _is_hermes_bot_message(message)
                ):
                    cleanup_message_ids.add(current_id)
        except Exception as exc:
            cleanup_errors.append(f"msg-discovery:{type(exc).__name__}")
        try:
            asyncio.run(adapter.disconnect())
        except Exception as exc:
            cleanup_errors.append(f"adapter:{type(exc).__name__}")
        for current_id in sorted(cleanup_message_ids):
            try:
                delete_msg_message(DM_CHAT_ID, current_id)
            except Exception as exc:
                cleanup_errors.append(f"msg:{type(exc).__name__}")

        remaining: list[dict] = []
        # MSG DELETE can return before the read replica stops exposing the
        # bot-owned target/reply. Retry that eventual-consistency window while
        # retaining residue=0 as the only passing cleanup verdict.
        for attempt in range(25):
            try:
                remaining = [
                    message
                    for message in get_messages_raw(DM_CHAT_ID, page_size=90)
                    if prefix in rendered(message)
                ]
            except Exception as exc:
                cleanup_errors.append(f"msg-verify:{type(exc).__name__}")
                break
            if not remaining:
                break
            if attempt < 24:
                time.sleep(min(2**attempt, 4))
        if remaining:
            bot_remaining = sum(
                1 for message in remaining if _is_hermes_bot_message(message)
            )
            cleanup_errors.append(
                f"msg-remain:{len(remaining)}"
                f"/bot:{bot_remaining}/human:{len(remaining) - bot_remaining}"
            )
        if cleanup_errors:
            raise RuntimeError(
                "outbound native reply E2E cleanup failed ("
                + ", ".join(cleanup_errors)
                + f"); functional={functional_result[0]}:"
                + functional_result[1]
            )

    return (
        functional_result[0],
        functional_result[1] + "; cleanup_residue=0",
    )


# ── Runner ────────────────────────────────────────────────────────

NAMED_TESTS = {
    "dm-echo-guard": test_dm_echo_guard,
    "mention-gating-ignore": test_mention_gating_ignore,
    "mention-gating-process": test_mention_gating_process,
    "model-picker": test_model_picker,
    "restart-no-replay": test_restart_no_replay,
    "send-text": test_send_text,
    "reaction-roundtrip": test_reaction_roundtrip,
    "delete-message-safety": test_delete_message_safety,
    "edit-message": test_edit_message,
    "download-attachment": test_download_attachment,
    "send-image-file": test_send_image_file,
    "send-document": test_send_document,
    "send-adaptive-card": test_send_adaptive_card,
    # ── 新增測項（G4 / G13-A / standalone_sender_fn）────────────
    "send-typing": test_send_typing,
    "list-conversations": test_list_conversations,
    "find-conv-by-display-name": test_find_conv_by_display_name,
    "contact-routing": test_contact_routing,
    "contact-directory-fallback": test_contact_directory_fallback,
    "find-conversation": test_find_conversation,
    "standalone-sender-fn": test_standalone_sender_fn,
    "busy-group-burst-redirect": test_busy_group_burst_redirect,
    "inbound-edit-revision-reopens-query": test_same_id_edit_reopens_exactly_one_revised_query,
    "quoted-reply-full-context-revises-query": test_quoted_reply_full_context_revises_query,
    "reply-to-native-thread-roundtrip": test_reply_to_native_thread_roundtrip,
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

    try:
        _load_configured_chat_ids()
    except RuntimeError as exc:
        print(f"FATAL: {exc}")
        sys.exit(1)

    log_path = args.gateway_log
    if not os.path.isfile(log_path):
        print(f"FATAL: gateway.log not found at {log_path}")
        sys.exit(1)

    # Baseline = current log line count (skip history)
    with open(log_path, encoding="utf-8", errors="replace") as f:
        baseline = sum(1 for _ in f)

    to_run = list(NAMED_TESTS.keys())
    if args.only:
        unknown = sorted(set(args.only) - set(NAMED_TESTS))
        if unknown:
            print(f"FATAL: unknown --only test name(s): {unknown}")
            sys.exit(2)
        to_run = [t for t in to_run if t in args.only]
    to_run = [t for t in to_run if t not in args.skip]
    if not to_run:
        print("FATAL: no E2E tests selected")
        sys.exit(2)

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
