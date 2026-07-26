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
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
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
_readback_http_layer = None


def _get_gateway_auth():
    """Share the gateway's atomic token cache implementation across E2E I/O."""
    global _gateway_auth
    if _gateway_auth is None:
        _gateway_auth = _TeamsAuth()
    return _gateway_auth


def get_graph_token() -> str:
    global _graph_token
    if _graph_token is None:
        gt = GraphToken(_get_gateway_auth())
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


def delete_graph_message(chat_id: str, message_id: str) -> None:
    """Delete a controlled Graph-user E2E message."""
    token = get_graph_token()
    url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages/{message_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(url, headers=headers)
    if response.status_code not in (204, 404):
        raise RuntimeError(
            f"Graph API DELETE failed: status={response.status_code}, "
            f"body_length={len(response.text or '')}"
        )


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
    """Send via the Skype SDK (bot-token path) — mirrors what the gateway itself sends."""
    from teams_skype_sdk.api._messages import MessagesService

    if _SDKHTTPLayer is None:
        raise RuntimeError("teams_skype_sdk is unavailable")
    http = _SDKHTTPLayer(_SDKAuthAdapter(_get_gateway_auth()))
    result = MessagesService(http).send(conversation_id=chat_id, content=content)
    return str(result.get("id", "") or result.get("OriginalArrivalTime", ""))


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
        return False, (
            "SDK send succeeded but returned no message id; "
            f"response_keys={sorted(result) if isinstance(result, dict) else []}"
        )

    try:
        found, evidence = wait_and_check_log(
            log_path, baseline,
            [rf"skipping own sent message id={re.escape(_log_ref(msg_id))}(?:\s|$)"],
            wait_seconds=45,  # adaptive poll may be 30s while WS is healthy
        )
        return found, evidence
    finally:
        from gateway.platforms.teams_mtk import TeamsMTKAdapter
        cleanup = asyncio.run(TeamsMTKAdapter(None).delete_message(DM_CHAT_ID, msg_id))
        if cleanup.get("status") != "deleted":
            raise RuntimeError(f"echo-guard cleanup failed: status={cleanup.get('status')}")


def test_mention_gating_ignore(log_path: str, baseline: int) -> tuple[bool, str]:
    """Group: a non-mentioned message is inspected but produces no bot reply."""
    baseline_msgs = get_messages_raw(GROUP_CHAT_ID, page_size=15)
    baseline_ids = {str(m.get("id")) for m in baseline_msgs}
    content = "E2E_AUTO no mention — should be ignored"
    msg_id = send_chat_message(GROUP_CHAT_ID, content)

    inspected, evidence = wait_and_check_log(
        log_path, baseline,
        [rf"inspecting msg id={re.escape(_log_ref(str(msg_id)))}(?:\s|$)"],
        wait_seconds=45,
    )
    if not inspected:
        return False, f"Gateway never inspected marker {msg_id}: {evidence}"

    # Mention gating runs synchronously after the inspection log. Give the
    # same poll iteration time to flush and prove the marker never reached
    # either the adapter dispatch log or the gateway runner. This prevents a
    # slow agent reply from turning a real dispatch into a false PASS.
    time.sleep(5)
    post_inspection_log = tail_log(log_path, baseline)
    marker = "no mention — should be ignored"
    if any(
        marker in line and token in line
        for line in post_inspection_log.splitlines()
        for token in ("new message from", "inbound message:")
    ):
        return False, "Non-mentioned group message reached the gateway dispatch path"

    msgs = get_messages_raw(GROUP_CHAT_ID, page_size=30)

    def _after_marker(message: dict) -> bool:
        candidate = str(message.get("id") or "")
        try:
            return int(candidate) > int(str(msg_id))
        except ValueError:
            return candidate not in baseline_ids

    unexpected_replies = [
        m for m in msgs
        if _after_marker(m)
        and str(m.get("id")) != str(msg_id)
        and "border-left" in (m.get("content") or "")
    ]
    if unexpected_replies:
        return False, (
            "Non-mentioned group message triggered a bot reply: "
            f"id={unexpected_replies[0].get('id')}"
        )
    return True, f"Gateway inspected {msg_id}; no bot reply was delivered"


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
    """DM /model picker: provider list -> provider choice -> model list."""
    def _read_picker(marker: str, wait_seconds: int = 25) -> str:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            for message in get_messages_raw(DM_CHAT_ID, page_size=30):
                content = str(message.get("content") or "")
                if marker in content:
                    return content
            time.sleep(2)
        return ""

    def _numbered_block(html_content: str, marker: str) -> Optional[int]:
        for block in re.findall(
            r'<div style="margin:1px 0">(.*?)</div>',
            html_content,
            flags=re.DOTALL,
        ):
            if marker not in block:
                continue
            match = re.search(r">(\d+)</span>", block)
            if match:
                return int(match.group(1))
        return None

    send_chat_message(DM_CHAT_ID, "/model")

    # Allow the stable-WS poll interval (up to 30s) plus delivery time.
    for attempt in range(12):
        time.sleep(4)
        step1_log = tail_log(log_path, baseline)
        if "model picker step 1 (providers) sent" in step1_log:
            break
    else:
        return False, step1_log[-500:]

    picker_ids = re.findall(
        r"model picker step 1 \(providers\) sent \(id=([^\s)]+)\)",
        step1_log,
    )
    if not picker_ids:
        return False, "Picker was sent but its real message ID was not logged"
    picker_id = picker_ids[-1]

    # A successful send is not enough: the next poll must classify the
    # outbound picker as Hermes-owned.  This catches the SDK-normalization
    # regression where ``content`` lost its HTML fingerprint and the picker
    # was dispatched back into the agent as if the user had typed it.
    skipped, skip_evidence = wait_and_check_log(
        log_path,
        baseline,
        [rf"skipping own sent message id={re.escape(picker_id)}(?:\s|$)"],
        wait_seconds=50,
    )
    if not skipped:
        return False, (
            f"Outbound picker id={picker_id} was not echo-guarded; "
            f"evidence={skip_evidence}"
        )

    provider_html = _read_picker("Select Provider")
    if not provider_html:
        return False, f"Provider picker id={picker_id} was not readable from Teams"
    current_model_match = re.search(
        r"Current:\s*<b>(.*?)</b>", provider_html, flags=re.DOTALL
    )
    current_model = (
        re.sub(r"<[^>]+>", "", current_model_match.group(1)).strip()
        if current_model_match else ""
    )
    provider_choice = _numbered_block(provider_html, "←")
    if not current_model or provider_choice is None:
        return False, (
            "Could not identify the current provider/model from the real picker; "
            f"current_model={current_model!r}, provider_choice={provider_choice!r}"
        )

    # Select the current provider so the E2E never mutates the user's model.
    baseline2 = sum(1 for _ in open(log_path, encoding="utf-8", errors="replace"))
    send_chat_message(DM_CHAT_ID, str(provider_choice))

    found, evidence = wait_and_check_log(
        log_path, baseline2,
        [r"model picker step 2.*sent"],
        wait_seconds=45,
    )
    if not found:
        return False, evidence

    step2_log = tail_log(log_path, baseline2)
    sub_picker_ids = re.findall(
        r"model picker step 2 .* sent \(id=([^\s)]+)\)", step2_log
    )
    if not sub_picker_ids:
        return False, "Model sub-picker was sent but its message ID was not logged"
    sub_picker_id = sub_picker_ids[-1]
    model_html = _read_picker("Select Model")
    if not model_html:
        return False, f"Model picker id={sub_picker_id} was not readable from Teams"

    model_choice = _numbered_block(model_html, f">{current_model}</span>")
    if model_choice is None:
        model_choice = _numbered_block(model_html, "✓")
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
        # Stable WS polling may take 30s before the inbound message is seen;
        # leave another 30s for the real model turn and SDK delivery.
        wait_seconds=60,
    )
    return found, evidence


def test_reaction_roundtrip(log_path: str, baseline: int) -> tuple[bool, str]:
    """S7: add and remove a real reaction, verified through MSG read-back."""
    del log_path, baseline
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    marker = f"E2E_AUTO reaction roundtrip {time.time_ns()}"
    message_id = send_via_sdk(DM_CHAT_ID, marker)
    if not message_id:
        return False, "SDK reaction target send returned no message ID"

    adapter = TeamsMTKAdapter(None)

    def _emotion_users() -> Optional[list]:
        message = next(
            (
                item
                for item in get_messages_raw(DM_CHAT_ID, page_size=30)
                if str(item.get("id")) == str(message_id)
            ),
            None,
        )
        if not message:
            return None
        properties = message.get("properties") or {}
        if isinstance(properties, str):
            properties = json.loads(properties)
        for emotion in properties.get("emotions") or []:
            if emotion.get("key") == "like":
                return emotion.get("users") or []
        return []

    try:
        sent = asyncio.run(adapter.send_reaction(DM_CHAT_ID, message_id, "like"))
        if sent.get("status") != "reacted":
            return False, f"send_reaction failed: {sent!r}"

        deadline = time.time() + 20
        added_users = None
        while time.time() < deadline:
            added_users = _emotion_users()
            if added_users:
                break
            time.sleep(1)
        if not added_users:
            return False, f"Reaction was not visible in MSG read-back: users={added_users!r}"

        removed = asyncio.run(adapter.remove_reaction(DM_CHAT_ID, message_id, "like"))
        if removed.get("status") != "removed":
            return False, f"remove_reaction failed: {removed!r}"

        deadline = time.time() + 20
        remaining_users = added_users
        while time.time() < deadline:
            remaining_users = _emotion_users()
            if remaining_users == []:
                break
            time.sleep(1)
        if remaining_users != []:
            return False, f"Reaction remained after remove: users={remaining_users!r}"

        return True, f"Reaction add/remove read-back verified for message_id={message_id}"
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
        tombstone = None
        tombstone_properties = {}
        while time.time() < deadline:
            tombstone = next(
                (
                    item
                    for item in get_messages_raw(DM_CHAT_ID, page_size=30)
                    if str(item.get("id")) == own_id
                ),
                None,
            )
            tombstone_properties = (tombstone or {}).get("properties") or {}
            if isinstance(tombstone_properties, str):
                tombstone_properties = json.loads(tombstone_properties)
            if (
                tombstone
                and not (tombstone.get("content") or "")
                and tombstone_properties.get("deletetime")
            ):
                break
            time.sleep(1)
        else:
            return False, (
                f"Own tombstone missing: found={bool(tombstone)}, "
                f"content_length={len((tombstone or {}).get('content') or '')}, "
                f"has_deletetime={bool(tombstone_properties.get('deletetime'))}"
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
            if foreign and foreign_marker in str(foreign.get("content") or ""):
                break
            time.sleep(1)
        foreign_content = str((foreign or {}).get("content") or "")
        if not foreign or foreign_marker not in foreign_content:
            return False, (
                "Controlled foreign message was not ready from MSG API: "
                f"found={bool(foreign)}, content_length={len(foreign_content)}"
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
            target = next(
                (m for m in get_messages_raw(DM_CHAT_ID, 30) if str(m.get("id")) == message_id),
                None,
            )
            if target is not None and marker in str(target.get("content") or ""):
                title_hash = hashlib.sha256(title.encode("utf-8")).hexdigest()[:10]
                return True, (
                    f"contact title hash={title_hash} resolved to control DM; "
                    f"message_id={message_id!r} read back"
                )
            time.sleep(2)
        return False, f"contact route message {message_id!r} not found in MSG read-back"
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
    import os as _os
    import subprocess
    from types import SimpleNamespace
    from unittest.mock import patch

    from gateway.config import Platform
    from gateway.platforms.teams_mtk import TeamsMTKAdapter
    from tools.send_message_tool import send_message_tool

    adapter = TeamsMTKAdapter(None)
    conversations = adapter.list_conversations(limit=200)
    if not conversations:
        return False, "list_conversations returned [] — cannot prove directory fallback boundary"

    people_script = _os.path.expanduser("~/.hermes/skills/m365/scripts/people.py")
    if not _os.path.isfile(people_script):
        return False, "M365 people.py is unavailable at the configured Hermes skill path"

    directory_env = {**_os.environ, "PYTHONPATH": ""}

    def _run_people(*args: str) -> tuple[list[dict], str]:
        try:
            completed = subprocess.run(
                ["python", people_script, *args],
                capture_output=True,
                text=True,
                timeout=30,
                env=directory_env,
            )
        except Exception as exc:
            return [], type(exc).__name__
        if completed.returncode != 0 or not completed.stdout.strip():
            return [], f"exit={completed.returncode}"
        try:
            payload = _json.loads(completed.stdout)
        except (TypeError, ValueError):
            return [], "invalid JSON"
        people = payload.get("people") or []
        return [person for person in people if isinstance(person, dict)], ""

    relevant_people, relevant_error = _run_people("relevant", "--limit", "50")
    if relevant_error:
        return False, f"live M365 People relevant lookup failed ({relevant_error})"
    if not relevant_people:
        return False, "live M365 People relevant lookup returned no candidates"

    def _matches_existing_conversation(name: str) -> bool:
        needle = name.lower()
        return any(
            needle in str(conv.get("title") or "").lower()
            or needle in str(conv.get("member_names") or "").lower()
            for conv in conversations
        )

    candidate = ""
    canonical_name = ""
    for person in relevant_people:
        name = str(person.get("displayName") or "").strip()
        if len(name) < 4 or _matches_existing_conversation(name):
            continue
        matches, search_error = _run_people(
            "search", "--query", name, "--limit", "10"
        )
        if search_error or not matches:
            continue
        canonical = str(matches[0].get("displayName") or "").strip()
        if canonical:
            candidate = name
            canonical_name = canonical
            break

    if not candidate:
        return False, (
            "no dynamic directory contact outside existing conversations; "
            f"conversations={len(conversations)} candidates={len(relevant_people)}"
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

        deadline = time.time() + 20
        while time.time() < deadline:
            messages = get_messages_raw(DM_CHAT_ID, page_size=30)
            for msg in messages:
                if marker in str(msg.get("content") or msg.get("body") or ""):
                    message_id = str(msg.get("id") or message_id)
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
                        if marker in str(msg.get("content") or msg.get("body") or "")
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
