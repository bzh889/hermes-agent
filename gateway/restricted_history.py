"""Exact-group semantic history retrieval for restricted-context tasks.

History retrieval is bound to the exact ``conv_id`` from the
OriginEgressBinding — no cross-conversation fan-out.

Two-stage retrieval:
1. Reply-chain traversal (backwardLink pagination) — full conversation context
2. Sliding-window recent messages — supplementary context

No mechanical pre-filter — the LLM judges the relevance of each message.
No redaction — the owner has already authorized the group's access.

History is injected as a standalone user message followed by an assistant
ack separator, preserving role alternation and prompt caching.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from gateway.restricted_origin import OriginEgressBinding, get_origin_binding

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoryMessage:
    """One retrieved message from conversation history."""

    message_id: str
    sender_id: str
    sender_name: str
    content: str
    timestamp: str
    reply_to: str = ""  # message_id this replies to (for backwardLink)
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class HistoryResult:
    """Result of a history retrieval operation."""

    messages: list[HistoryMessage]
    conv_id: str
    retrieval_method: str  # "reply_chain" | "sliding_window" | "combined"


class CrossConversationError(Exception):
    """Raised when history retrieval attempts to access a different conv_id."""
    pass


# ---------------------------------------------------------------------------
# Retrieval function
# ---------------------------------------------------------------------------

def retrieve_history(
    fetch_fn: Callable[..., list[dict[str, Any]]],
    conv_id: str,
    binding: Optional[OriginEgressBinding] = None,
    *,
    use_reply_chain: bool = True,
    window_size: int = 30,
    max_messages: int = 100,
) -> HistoryResult:
    """Retrieve conversation history bound to the exact conv_id.

    Parameters
    ----------
    fetch_fn:
        Function that fetches messages. Called as
        ``fetch_fn(conv_id, limit, backward_link)`` — returns a list of
        message dicts with keys: message_id, sender_id, sender_name,
        content, timestamp, reply_to, attachments.
    conv_id:
        The exact conversation ID to retrieve from. Must match the
        binding's conv_id.
    binding:
        The origin binding (from ContextVar if None).
    use_reply_chain:
        If True, traverse reply chains (backwardLink) first.
    window_size:
        Number of recent messages for sliding-window supplementary context.
    max_messages:
        Max total messages to return.

    Returns
    -------
    HistoryResult
        Messages and metadata.

    Raises
    ------
    CrossConversationError
        If conv_id doesn't match the binding's conv_id.
    """
    if binding is None:
        binding = get_origin_binding()

    # Cross-conversation guard — the conv_id must match the binding
    if binding is not None and conv_id != binding.conv_id:
        raise CrossConversationError(
            f"history retrieval conv_id mismatch: requested={conv_id} "
            f"but binding={binding.conv_id}"
        )

    all_messages: list[HistoryMessage] = []
    seen_ids: set[str] = set()

    # Stage 1: Reply-chain traversal (backwardLink pagination)
    if use_reply_chain:
        backward_link = ""
        for _ in range(max_messages):  # safety limit
            raw_messages = fetch_fn(conv_id, limit=50, backward_link=backward_link)
            if not raw_messages:
                break
            for msg in raw_messages:
                mid = msg.get("message_id", "")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_messages.append(_to_history_message(msg))
            # Get the next backward link
            if raw_messages:
                backward_link = raw_messages[0].get("reply_to", "")
                if not backward_link:
                    break
            if len(all_messages) >= max_messages:
                break

    # Stage 2: Sliding-window recent messages (supplement reply-chain)
    if len(all_messages) < window_size:
        recent = fetch_fn(conv_id, limit=window_size, backward_link="")
        for msg in recent:
            mid = msg.get("message_id", "")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                all_messages.append(_to_history_message(msg))
        if not all_messages:
            retrieval_method = "sliding_window"
        else:
            retrieval_method = "combined"
    else:
        retrieval_method = "reply_chain"

    # Trim to max
    all_messages = all_messages[:max_messages]

    return HistoryResult(
        messages=all_messages,
        conv_id=conv_id,
        retrieval_method=retrieval_method if all_messages else "empty",
    )


def _to_history_message(raw: dict[str, Any]) -> HistoryMessage:
    """Convert a raw message dict to a HistoryMessage."""
    return HistoryMessage(
        message_id=raw.get("message_id", ""),
        sender_id=raw.get("sender_id", ""),
        sender_name=raw.get("sender_name", ""),
        content=raw.get("content", ""),
        timestamp=raw.get("timestamp", ""),
        reply_to=raw.get("reply_to", ""),
        attachments=raw.get("attachments", []),
    )


# ---------------------------------------------------------------------------
# History injection — role-preserving format
# ---------------------------------------------------------------------------

def format_history_for_injection(result: HistoryResult) -> tuple[str, str]:
    """Format history for injection into the conversation.

    Returns a tuple of (user_message, assistant_ack) that preserves
    role alternation and prompt caching:

    - user_message: the history as a standalone user message
    - assistant_ack: a short assistant acknowledgment separator

    The agent loop injects the user_message, then the assistant_ack,
    then the actual user turn — maintaining strict role alternation.
    """
    lines: list[str] = [
        f"## Conversation History (conv_id: {result.conv_id})",
        f"*Retrieved via {result.retrieval_method}, {len(result.messages)} messages*",
        "",
    ]
    for msg in result.messages:
        sender = msg.sender_name or msg.sender_id or "unknown"
        lines.append(f"**[{msg.timestamp}] {sender}:** {msg.content}")
        if msg.attachments:
            for att in msg.attachments:
                name = att.get("name", "attachment")
                preview = att.get("preview", "")
                lines.append(f"  📎 {name}" + (f" ({preview})" if preview else ""))

    user_message = "\n".join(lines)
    assistant_ack = "Understood — I have the conversation history context."

    return user_message, assistant_ack
