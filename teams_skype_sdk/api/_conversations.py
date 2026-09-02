"""[API Service] Conversation listing, lookup, and info retrieval."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from teams_skype_sdk.cache import get_cache

from ._constants import (
    CHATSVC_BASE, FILTERED_CONV_TYPES,
    MAX_PAGE_SIZE, API_MAX_PAGE_SIZE,
)
import json
from ._http import HTTPLayer

if TYPE_CHECKING:
    from ._messages import MessagesService

_conv_cache: list[dict] | None = None
_conv_cache_time: float = 0


class ConversationsService:
    """Conversation listing, info, find, and get-by-name."""

    def __init__(self, http: HTTPLayer, messages: "MessagesService"):
        self._http = http
        self._messages = messages

    def list(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """List recent Teams conversations (chats, groups, and meetings).

        Filters out channels, activity streams, and system conversations.

        Args:
            limit: Maximum number of conversations to return (max: 200)
            offset: Number of conversations to skip for pagination (default: 0)

        Returns:
            List of conversation dictionaries with id, title, type, lastMessage
        """
        limit = min(limit, MAX_PAGE_SIZE)

        global _conv_cache, _conv_cache_time
        if offset == 0 and _conv_cache is not None and (time.time() - _conv_cache_time) < 60:
            return _conv_cache[:limit]

        url = f"{CHATSVC_BASE}/conversations"
        total_needed = offset + limit
        api_request_size = min(total_needed * 2, MAX_PAGE_SIZE)

        all_raw_items = []
        fetched = 0

        while len(all_raw_items) < api_request_size:
            params = {"pageSize": min(API_MAX_PAGE_SIZE, api_request_size - fetched)}

            response = self._http._request("GET", url, params=params)

            data = response.json()
            items = data.get("conversations", [])

            if not items:
                break

            all_raw_items.extend(items)
            fetched += len(items)

            if len(items) < API_MAX_PAGE_SIZE:
                break

        conversations = []
        cache = get_cache()
        skipped = 0

        for chat in all_raw_items:
            thread_props = chat.get("threadProperties", {})
            conv_type = thread_props.get("threadType", "unknown")

            if conv_type in FILTERED_CONV_TYPES:
                continue

            if skipped < offset:
                skipped += 1
                continue

            if len(conversations) >= limit:
                break

            conv = {
                "id": chat.get("id", ""),
                "title": thread_props.get("topic") or "Untitled",
                "type": conv_type,
                "lastActivity": self._http._format_timestamp(
                    chat.get("lastMessage", {}).get("composetime")
                ),
            }

            last_msg = chat.get("lastMessage", {})
            if last_msg:
                content = self._http._extract_text_content(last_msg.get("content", ""))
                if content:
                    conv["lastMessage"] = (
                        content[:100] + "..." if len(content) > 100 else content
                    )

                sender_mri = self._http._extract_mri_from_url(last_msg.get("from", ""))
                sender_name = last_msg.get("imdisplayname", "")

                if sender_mri and sender_name:
                    cache.add_member(conv["id"], sender_mri, sender_name)

                if conv["title"] == "Untitled" and conv["type"] == "chat":
                    other_oid = self._http._get_other_person_oid(conv["id"])
                    if other_oid:
                        other_mri = f"8:orgid:{other_oid}"

                        if sender_mri == other_mri and sender_name:
                            conv["title"] = sender_name
                        else:
                            other_name = cache.get_display_name(other_mri)

                            if not other_name:
                                try:
                                    self._messages.get(conv["id"], limit=5)
                                    other_name = cache.get_display_name(other_mri)
                                except Exception:
                                    pass

                            if other_name:
                                conv["title"] = other_name

            cache.add_conversation(conv["id"], conv["title"], conv["type"])
            conversations.append(conv)

        cache.flush()
        if offset == 0:
            _conv_cache = conversations
            _conv_cache_time = time.time()
        return conversations

    def info(self, conversation_id: str) -> dict:
        """Get detailed information about a conversation including members."""
        cache = get_cache()

        conversations = self.list(limit=50)
        base_info = None

        for conv in conversations:
            if conv.get("id") == conversation_id:
                base_info = {
                    "id": conv.get("id", ""),
                    "title": conv.get("title", "Untitled"),
                    "type": conv.get("type", "unknown"),
                    "lastActivity": conv.get("lastActivity", "Unknown"),
                }
                break

        if base_info is None:
            base_info = {
                "id": conversation_id,
                "title": "Unknown",
                "type": "unknown",
                "lastActivity": "Unknown",
            }

        try:
            messages = self._messages.get(conversation_id, limit=50)
            members_found = {}

            for msg in messages:
                sender_mri = msg.get("from", "")
                sender_name = msg.get("sender", "")

                if sender_mri and sender_name and sender_name != "Unknown":
                    members_found[sender_mri] = sender_name
                    cache.add_member(conversation_id, sender_mri, sender_name)

            cached_members = cache.get_all_members(conversation_id)
            for mri, member_info in cached_members.items():
                if isinstance(member_info, dict) and "displayName" in member_info:
                    if mri not in members_found:
                        members_found[mri] = member_info["displayName"]

            if members_found:
                base_info["members"] = [
                    {"id": mri, "name": name}
                    for mri, name in members_found.items()
                ]

            if base_info["title"] in ("Untitled", "Unknown") and members_found:
                for name in members_found.values():
                    base_info["title"] = name
                    break

        except Exception:
            pass

        return base_info

    def find(self, name: str) -> list[dict]:
        """Find conversations by name (searches cache first, then refreshes)."""
        cache = get_cache()

        results = cache.find_conversation_by_name(name)

        if not results:
            self.list(limit=50)
            results = cache.find_conversation_by_name(name)

        return results

    def create(self, members: list[str], topic: str = "") -> dict:
        """Create a new group chat with specified members.

        Args:
            members: List of MRIs (e.g. ['8:orgid:<aad_id>', ...]) — must include self
            topic: Optional group display name

        Returns:
            dict with id, title of the new conversation
        """
        my_oid = self._http._get_my_oid()
        my_mri = f"8:orgid:{my_oid}"

        members_payload = [{"id": my_mri, "role": "Admin"}]
        for mri in members:
            if mri != my_mri:
                members_payload.append({"id": mri, "role": "User"})

        payload = {
            "members": members_payload,
            "properties": {
                "threadType": "chat",
            },
        }
        if topic:
            payload["properties"]["topic"] = topic

        url = "https://amer.ng.msg.teams.microsoft.com/v1/threads"
        resp = self._http._request("POST", url, json=payload)
        location = resp.headers.get("Location", "")
        conv_id = location.split("/threads/")[-1] if "/threads/" in location else ""
        return {"id": conv_id, "title": topic or "New Group Chat"}

    def set_topic(self, conversation_id: str, topic: str) -> dict:
        """Rename a group chat by updating its topic.

        Args:
            conversation_id: Target conversation ID
            topic: New display name

        Returns:
            dict with id and new title
        """
        url = f"https://amer.ng.msg.teams.microsoft.com/v1/threads/{conversation_id}/properties"
        payload = {"topic": topic}
        self._http._request("PUT", url, json=payload)
        cache = get_cache()
        cache.add_conversation(conversation_id, topic, "chat")
        cache.flush()
        return {"id": conversation_id, "title": topic}

    def get_messages_by_name(self, name: str, limit: int = 20) -> list[dict]:
        """Get messages from a conversation by its name.

        Raises:
            ValueError: If no matching conversation is found
        """
        cache = get_cache()

        conversation_id = cache.get_conversation_id(name)

        if not conversation_id:
            self.list(limit=50)
            conversation_id = cache.get_conversation_id(name)

        if not conversation_id:
            raise ValueError(f"No conversation found matching '{name}'")

        return self._messages.get(conversation_id, limit=limit)
