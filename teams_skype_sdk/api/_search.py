"""[API Service] Message search across conversations."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

import requests

from ._constants import MAX_PAGE_SIZE

if TYPE_CHECKING:
    from ._messages import MessagesService
    from ._conversations import ConversationsService


def _strip_html(html: str) -> str:
    return re.sub(r'<[^>]+>', '', html).strip()


class SearchService:
    """Keyword search across conversations with optional filters."""

    def __init__(
        self,
        messages: "MessagesService",
        conversations: "ConversationsService",
        graph_api: Any = None,
    ):
        self._messages = messages
        self._conversations = conversations
        self._graph = graph_api

    @staticmethod
    def _normalize_graph_msg(raw: dict) -> dict:
        """Normalize a Graph API message dict to internal format."""
        from_info = raw.get("from") or {}
        user_info = from_info.get("user") or {}
        sender = user_info.get("displayName") or "Unknown"
        sender_oid = user_info.get("id") or ""
        sender_mri = f"8:orgid:{sender_oid}" if sender_oid else ""

        body = raw.get("body") or {}
        content = _strip_html(body.get("content") or "")

        created = raw.get("createdDateTime") or ""
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            timestamp = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            timestamp = created

        return {
            "id": raw.get("id", ""),
            "from": sender_mri,
            "sender": sender,
            "content": content,
            "timestamp": timestamp,
            "type": raw.get("messageType", "message"),
        }

    def messages(
        self, keyword: str,
        conversation_id: Optional[str] = None,
        max_conversations: int = 10, messages_per_conversation: int = 50,
        sender_filter: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> list[dict]:
        """Search messages by keyword with optional filters.

        When date_from/date_to is provided and graph_api is available, uses
        Graph API with server-side $filter=createdDateTime for historical search.
        Otherwise falls back to fetching the latest N messages via MSG_BASE API.

        Args:
            keyword: Search term to look for
            conversation_id: Optional conversation ID to limit search scope
            max_conversations: Max conversations to search (default 10, max 50)
            messages_per_conversation: Messages to fetch per conversation (default 50, max 200)
            sender_filter: Filter by sender name (case-insensitive partial match)
            date_from: Filter messages from this date (YYYY-MM-DD)
            date_to: Filter messages up to this date (YYYY-MM-DD)

        Returns:
            List of matching message dictionaries
        """
        max_conversations = min(max_conversations, 50)
        messages_per_conversation = min(messages_per_conversation, MAX_PAGE_SIZE)
        use_date_search = bool(date_from or date_to)

        def _matches(msg: dict) -> bool:
            if keyword.lower() not in msg.get("content", "").lower():
                return False
            if sender_filter and sender_filter.lower() not in msg.get("sender", "").lower():
                return False
            return True

        def _fetch_by_date(conv_id: str) -> list[dict]:
            return self._messages.get_by_date(
                conv_id,
                date_from=date_from,
                date_to=date_to,
                limit=messages_per_conversation,
            )

        def _fetch_legacy(conv_id: str) -> list[dict]:
            return self._messages.get(conv_id, limit=messages_per_conversation)

        fetch = _fetch_by_date if use_date_search else _fetch_legacy

        results = []

        if conversation_id:
            msgs = fetch(conversation_id)
            for msg in msgs:
                if _matches(msg):
                    msg["conversation_id"] = conversation_id
                    results.append(msg)
        else:
            conversations = self._conversations.list(limit=max_conversations)
            for conv in conversations:
                if len(results) >= 50:
                    break
                try:
                    msgs = fetch(conv["id"])
                    for msg in msgs:
                        if _matches(msg):
                            msg["conversation_id"] = conv["id"]
                            msg["conversation_title"] = conv.get("title", "Unknown")
                            results.append(msg)
                except requests.HTTPError:
                    continue

        return results[:50]
