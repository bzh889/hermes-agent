"""[API Service] Activity streams — spaces, activity, notes, call logs, threads, saved."""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

from teams_skype_sdk.cache import get_cache

from ._constants import (
    CHATSVC_BASE, MSG_BASE,
    MAX_PAGE_SIZE, API_MAX_PAGE_SIZE, MAX_FETCH_PAGES,
    SPACE_CONV_TYPES, NOTES_CONV_TYPES,
    THREADS_CONV_TYPES, SAVED_CONV_TYPES,
)
from ._http import HTTPLayer


class ActivityService:
    """Specialized list operations for activity streams."""

    def __init__(self, http: HTTPLayer):
        self._http = http

    # ---- Pagination (absorbed from _base.py) --------------------------------

    def _fetch_conversations_by_type(
        self,
        target_types: set,
        limit: int,
        offset: int = 0,
    ) -> list[dict]:
        """Fetch raw conversation items filtered by threadType with multi-page pagination."""
        limit = min(limit, MAX_PAGE_SIZE)

        url = f"{CHATSVC_BASE}/conversations"
        params = {"view": "msnp24Equivalent", "pageSize": API_MAX_PAGE_SIZE}

        filtered: list[dict] = []
        skipped = 0

        for _ in range(MAX_FETCH_PAGES):
            response = self._http._request("GET", url, params=params)
            data = response.json()
            items = data.get("conversations", [])

            if not items:
                break

            for chat in items:
                thread_props = chat.get("threadProperties", {})
                conv_type = thread_props.get("threadType", "unknown")

                if conv_type not in target_types:
                    continue

                if skipped < offset:
                    skipped += 1
                    continue

                filtered.append(chat)
                if len(filtered) >= limit:
                    return filtered

            metadata = data.get("_metadata", {})
            backward_link = metadata.get("backwardLink")
            sync_state = metadata.get("syncState")

            if backward_link:
                url = backward_link
                params = {}
            elif sync_state:
                params["syncState"] = sync_state
            elif len(items) < API_MAX_PAGE_SIZE:
                break
            else:
                break

        return filtered

    # ---- Public methods -----------------------------------------------------

    def list_spaces(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """List Teams spaces (teams/workspaces)."""
        cache = get_cache()
        raw_items = self._fetch_conversations_by_type(SPACE_CONV_TYPES, limit, offset)

        spaces = []
        for chat in raw_items:
            thread_props = chat.get("threadProperties", {})

            space = {
                "id": chat.get("id", ""),
                "title": thread_props.get("topic") or "Untitled Space",
                "type": thread_props.get("threadType", "unknown"),
                "lastActivity": self._http._format_timestamp(
                    chat.get("lastMessage", {}).get("composetime")
                ),
            }

            last_msg = chat.get("lastMessage", {})
            if last_msg:
                content = self._http._extract_text_content(last_msg.get("content", ""))
                if content:
                    space["lastMessage"] = (
                        content[:100] + "..." if len(content) > 100 else content
                    )

            cache.add_conversation(space["id"], space["title"], space["type"])
            spaces.append(space)

        cache.flush()
        return spaces

    def _get_activity_messages(self, conversation_id: str, limit: int) -> list[dict]:
        """Get activity messages from a specific activity stream."""
        encoded_id = urllib.parse.quote(conversation_id, safe='')
        url = f"{MSG_BASE}/conversations/{encoded_id}/messages"
        params = {"pageSize": min(limit, 50)}

        try:
            response = self._http._request("GET", url, params=params)
        except requests.HTTPError:
            return []

        activities = []
        for msg in response.json().get("messages", []):
            props = msg.get("properties", {})
            activity = props.get("activity", {})

            if not activity:
                continue

            activity_type = activity.get("activityType", "unknown")

            item = {
                "id": msg.get("id"),
                "activityType": activity_type,
                "activitySubtype": activity.get("activitySubtype"),
                "timestamp": self._http._format_timestamp(msg.get("composetime")),
                "source": {
                    "user": activity.get("sourceUserImDisplayName", ""),
                    "topic": activity.get("sourceThreadTopic", ""),
                    "preview": activity.get("messagePreview", ""),
                },
            }

            if activity_type == "reactionInChat":
                context = activity.get("activityContext", {})
                reaction_keys = ("like", "heart", "laugh", "surprised", "sad", "angry")
                item["reactions"] = {
                    k: v for k, v in context.items() if k in reaction_keys
                }

            activities.append(item)

        return activities

    def list(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """List recent activity (notifications and mentions) from Teams."""
        limit = min(limit, MAX_PAGE_SIZE)

        cache = get_cache()
        activities = []

        total_needed = offset + limit

        notifications = self._get_activity_messages("48:notifications", total_needed)
        activities.extend(notifications)

        cache.add_conversation("48:notifications", "Notifications", "streamofnotifications")

        mentions = self._get_activity_messages("48:mentions", total_needed)
        activities.extend(mentions)

        cache.add_conversation("48:mentions", "Mentions", "streamofmentions")

        activities.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        cache.flush()
        return activities[offset : offset + limit]

    def list_notes(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """List Teams notes streams."""
        cache = get_cache()
        raw_items = self._fetch_conversations_by_type(NOTES_CONV_TYPES, limit, offset)

        notes = []
        for chat in raw_items:
            thread_props = chat.get("threadProperties", {})

            note = {
                "id": chat.get("id", ""),
                "title": thread_props.get("topic") or "Notes",
                "type": thread_props.get("threadType", "unknown"),
                "lastActivity": self._http._format_timestamp(
                    chat.get("lastMessage", {}).get("composetime")
                ),
            }

            last_msg = chat.get("lastMessage", {})
            if last_msg.get("content"):
                note["lastMessage"] = self._http._extract_text_content(
                    last_msg.get("content", "")
                )[:100]

            cache.add_conversation(note["id"], note["title"], note["type"])
            notes.append(note)

        cache.flush()
        return notes

    def _get_call_log_messages(
        self, total_needed: int, max_pages: int = MAX_FETCH_PAGES,
    ) -> tuple[list[dict], int, bool]:
        """Fetch raw call-log JSON entries from 48:calllogs messages.

        Returns:
            (entries, parse_errors, scan_truncated)
        """
        encoded_id = urllib.parse.quote("48:calllogs", safe="")
        url = f"{MSG_BASE}/conversations/{encoded_id}/messages"
        params: dict = {"pageSize": min(total_needed, API_MAX_PAGE_SIZE)}

        entries: list[dict] = []
        parse_errors = 0

        for _ in range(max_pages):
            try:
                response = self._http._request("GET", url, params=params)
            except requests.HTTPError:
                break

            data = response.json()
            messages = data.get("messages", [])

            if not messages:
                break

            for msg in messages:
                props = msg.get("properties", {})
                call_log_str = props.get("call-log")
                if not call_log_str:
                    continue

                try:
                    call_data = json.loads(call_log_str)
                    entries.append(call_data)
                except (json.JSONDecodeError, TypeError):
                    parse_errors += 1

            if len(entries) >= total_needed:
                return entries, parse_errors, False

            metadata = data.get("_metadata", {})
            backward_link = metadata.get("backwardLink")
            if backward_link:
                url = backward_link
                params = {}
            else:
                break

        scan_truncated = len(entries) < total_needed and max_pages > 1
        return entries, parse_errors, scan_truncated

    @staticmethod
    def _resolve_call_person(call_data: dict) -> tuple[str, str]:
        """Determine the other person's name and MRI from a call-log entry.

        Returns:
            (person_name, person_id)
        """
        direction = call_data.get("callDirection", "")
        call_type = call_data.get("callType", "twoParty")

        originator = call_data.get("originatorParticipant") or {}
        target = call_data.get("targetParticipant") or {}

        if call_type == "multiParty":
            initiator_name = originator.get("displayName", "")
            initiator_id = originator.get("id", "")
            if initiator_name:
                return f"Group Call (initiated by {initiator_name})", initiator_id
            return "Group Call", initiator_id

        # twoParty: pick the "other" participant
        if direction == "incoming":
            other, fallback = originator, target
        else:
            other, fallback = target, originator

        name = other.get("displayName") or fallback.get("displayName") or other.get("alternateId") or ""
        person_id = other.get("id") or fallback.get("id") or ""

        # Ensure MRI format (prefix with 8:orgid: if bare GUID)
        if person_id and not person_id.startswith(("8:", "4:", "28:")):
            person_id = f"8:orgid:{person_id}"

        return name or "Unknown", person_id

    def list_call_logs(
        self,
        limit: int = 20,
        offset: int = 0,
        target_person: str = "",
        days_back: int = 0,
    ) -> dict:
        """List Teams call logs with filtering and agentic metadata.

        Returns:
            dict with keys: items, parse_errors, scan_truncated, has_filters
        """
        limit = min(limit, MAX_PAGE_SIZE)
        has_filters = bool(target_person or days_back)
        cache = get_cache()

        # When filtering, fetch more to compensate for filtered-out entries
        fetch_limit = (offset + limit) * 5 if has_filters else offset + limit
        raw_entries, parse_errors, scan_truncated = self._get_call_log_messages(
            fetch_limit
        )

        # Prepare date cutoff for days_back filter
        cutoff_dt = None
        if days_back > 0:
            cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days_back)

        call_logs: list[dict] = []
        for call_data in raw_entries:
            person_name, person_id = self._resolve_call_person(call_data)

            # Client-side filtering
            if target_person and target_person.lower() not in person_name.lower():
                continue

            start_time_str = call_data.get("startTime")
            if cutoff_dt and start_time_str:
                try:
                    start_dt = datetime.fromisoformat(
                        start_time_str.replace("Z", "+00:00")
                    )
                    if start_dt < cutoff_dt:
                        continue
                except (ValueError, AttributeError):
                    pass

            direction = call_data.get("callDirection", "unknown")
            state = call_data.get("callState", "unknown")
            call_type = call_data.get("callType", "twoParty")

            call_log: dict = {
                "id": call_data.get("callId", ""),
                "direction": direction,
                "state": state,
                "callType": call_type,
                "timestamp": self._http._format_timestamp(start_time_str),
                "person": person_name,
                "personId": person_id,
            }

            # Duration: connectTime → endTime (actual talk time)
            connect_time = call_data.get("connectTime")
            end_time = call_data.get("endTime")
            if connect_time and end_time:
                try:
                    connect_dt = datetime.fromisoformat(
                        connect_time.replace("Z", "+00:00")
                    )
                    end_dt = datetime.fromisoformat(
                        end_time.replace("Z", "+00:00")
                    )
                    duration_secs = int((end_dt - connect_dt).total_seconds())
                    if duration_secs >= 0:
                        call_log["duration"] = f"{duration_secs // 60}m {duration_secs % 60}s"
                        call_log["durationSeconds"] = duration_secs
                except (ValueError, AttributeError):
                    pass

            # Cache participant for cross-tool resolution
            if person_id and person_name and person_name != "Unknown":
                cache.add_member("48:calllogs", person_id, person_name)

            call_logs.append(call_log)

        cache.add_conversation("48:calllogs", "Call Logs", "streamofcalllogs")
        cache.flush()

        return {
            "items": call_logs[offset:offset + limit],
            "parse_errors": parse_errors,
            "scan_truncated": scan_truncated,
            "has_filters": has_filters,
        }

    def list_threads(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """List Teams tracked threads (discussions you're following)."""
        cache = get_cache()
        raw_items = self._fetch_conversations_by_type(THREADS_CONV_TYPES, limit, offset)

        threads = []
        for chat in raw_items:
            thread_props = chat.get("threadProperties", {})
            last_msg = chat.get("lastMessage", {})
            msg_props = last_msg.get("properties", {})

            thread = {
                "id": chat.get("id", ""),
                "type": thread_props.get("threadType", "unknown"),
                "reason": msg_props.get("activityReason", "unknown"),
                "topic": msg_props.get("sourceThreadTopic", "Unknown Topic"),
                "author": msg_props.get("sourceUserImDisplayName", "Unknown"),
                "timestamp": self._http._format_timestamp(last_msg.get("composetime")),
            }

            subject = msg_props.get("parentMessageSubject")
            if subject:
                thread["subject"] = subject

            preview = msg_props.get("messagePreview", "")
            if preview:
                thread["preview"] = preview[:100] + "..." if len(preview) > 100 else preview

            replies = msg_props.get("repliesCount")
            if replies:
                thread["replies"] = int(replies)

            cache.add_conversation(thread["id"], thread.get("topic", "Unknown Topic"), thread["type"])
            threads.append(thread)

        cache.flush()
        return threads

    def list_saved(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """List Teams saved messages."""
        cache = get_cache()
        raw_items = self._fetch_conversations_by_type(SAVED_CONV_TYPES, limit, offset)

        saved_messages = []
        for chat in raw_items:
            thread_props = chat.get("threadProperties", {})
            last_msg = chat.get("lastMessage", {})
            msg_props = last_msg.get("properties", {})

            saved = {
                "id": chat.get("id", ""),
                "type": thread_props.get("threadType", "unknown"),
                "activityType": msg_props.get("activityType", "savedMessage"),
                "topic": msg_props.get("sourceThreadTopic", "Unknown Topic"),
                "author": msg_props.get("sourceUserImDisplayName", "Unknown"),
                "timestamp": self._http._format_timestamp(last_msg.get("composetime")),
            }

            preview = msg_props.get("messagePreview", "")
            if preview:
                saved["preview"] = preview[:100] + "..." if len(preview) > 100 else preview

            cache.add_conversation(saved["id"], saved.get("topic", "Unknown Topic"), saved["type"])
            saved_messages.append(saved)

        cache.flush()
        return saved_messages
