"""Teams cache module for storing and retrieving member display names and conversation info.

Teams API doesn't directly provide member displayName - the only way to get names
is from the `imdisplayname` field in message history. This module provides a
persistent cache to remember identified members and conversations across sessions.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class TeamsCache:
    """Teams cache management class.

    Stores:
    - Member information (displayName, email) keyed by conversation_id + MRI
    - Conversation information (id, title, type) for quick name-to-id lookup

    Automatically persists to a JSON file for cross-session persistence.
    """

    def __init__(self, cache_file: str = None, auto_save_delay: float = 2.0):
        """Initialize teams cache.

        Args:
            cache_file: Path to cache file. Defaults to
                       $HERMES_HOME/cache/teams_skype_sdk/cache.json.
            auto_save_delay: Delay in seconds before auto-saving changes (default: 2.0)
        """
        if cache_file is None:
            hermes_home = Path(
                os.environ.get("HERMES_HOME") or Path.home() / ".hermes"
            )
            cache_file = str(
                hermes_home / "cache" / "teams_skype_sdk" / "cache.json"
            )

        self.cache_file = cache_file
        self.cache: dict = {}
        self._dirty = False  # Track if there are unsaved changes
        self._auto_save_delay = auto_save_delay
        self._last_change_time: Optional[float] = None
        self._load_cache()

    def _load_cache(self):
        """Load cache from file and auto-cleanup old entries."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                # Auto-cleanup entries older than 90 days
                self.cleanup_old_entries(days=90)
        except (json.JSONDecodeError, IOError):
            # If file is corrupted, start with empty cache
            self.cache = {}

    def _save_cache(self):
        """Save cache to file."""
        try:
            Path(self.cache_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except IOError:
            pass  # Silently ignore save errors

    def _mark_dirty(self):
        """Mark cache as modified, needing save."""
        self._dirty = True
        self._last_change_time = time.time()

    def _maybe_save(self):
        """Save if dirty and delay has passed since last change."""
        if self._dirty and self._last_change_time:
            if time.time() - self._last_change_time >= self._auto_save_delay:
                self._save_cache()
                self._dirty = False

    def flush(self):
        """Force save all pending changes immediately."""
        if self._dirty:
            self._save_cache()
            self._dirty = False

    # ========== Member Cache Methods ==========

    def add_member(
        self, conversation_id: str, mri: str, display_name: str, email: str = ""
    ):
        """Add or update member information in cache.

        Args:
            conversation_id: Conversation ID
            mri: Member Resource Identifier (e.g., "8:orgid:xxx")
            display_name: Display name of the member
            email: Email address (optional)

        Note:
            Automatically skips entries with "Member xxx" format (unknown members)
            to avoid polluting the cache.
        """
        # Skip unknown members (don't pollute cache)
        if not display_name or display_name.startswith("Member "):
            return

        # Skip empty or "Unknown" names
        if display_name in ("", "Unknown"):
            return

        # Ensure conversation entry exists
        if conversation_id not in self.cache:
            self.cache[conversation_id] = {}

        # Update member info
        self.cache[conversation_id][mri] = {
            "displayName": display_name,
            "email": email,
            "lastSeen": datetime.now().isoformat(),
        }

        # Also update global mapping for cross-conversation lookup
        if "_global" not in self.cache:
            self.cache["_global"] = {}
        self.cache["_global"][mri] = display_name

        # Use delayed save to reduce disk writes
        self._mark_dirty()
        self._maybe_save()

    def get_member(self, conversation_id: str, mri: str) -> Optional[dict]:
        """Get member information from cache.

        Args:
            conversation_id: Conversation ID
            mri: Member Resource Identifier

        Returns:
            Member info dict with displayName, email, lastSeen, or None if not found
        """
        if conversation_id in self.cache:
            if mri in self.cache[conversation_id]:
                return self.cache[conversation_id][mri]
        return None

    def get_display_name(self, mri: str) -> Optional[str]:
        """Get display name by MRI (global cross-conversation lookup).

        Args:
            mri: Member Resource Identifier

        Returns:
            Display name string or None if not found
        """
        global_cache = self.cache.get("_global", {})
        return global_cache.get(mri)

    def get_all_members(self, conversation_id: str) -> dict:
        """Get all cached members for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Dict of {mri: member_info}
        """
        return self.cache.get(conversation_id, {})

    def update_email(self, conversation_id: str, mri: str, email: str):
        """Update member email.

        Args:
            conversation_id: Conversation ID
            mri: Member Resource Identifier
            email: Email address
        """
        if conversation_id in self.cache and mri in self.cache[conversation_id]:
            self.cache[conversation_id][mri]["email"] = email
            self.cache[conversation_id][mri]["lastSeen"] = datetime.now().isoformat()
            self._save_cache()

    # ========== Conversation Cache Methods ==========

    def add_conversation(self, conversation_id: str, title: str, conv_type: str):
        """Cache conversation information for name-to-id lookup.

        Args:
            conversation_id: Conversation ID (e.g., "19:xxx@thread.v2")
            title: Conversation title/name
            conv_type: Conversation type (e.g., "chat", "group", "channel")
        """
        # Skip untitled or unknown conversations
        if not title or title in ("Untitled", "Unknown", ""):
            return

        # Ensure _conversations entry exists
        if "_conversations" not in self.cache:
            self.cache["_conversations"] = {}

        # Store conversation info keyed by title
        self.cache["_conversations"][title] = {
            "id": conversation_id,
            "type": conv_type,
            "lastSeen": datetime.now().isoformat(),
        }

        # Use delayed save to reduce disk writes
        self._mark_dirty()
        self._maybe_save()

    def find_conversation_by_name(self, name: str) -> list[dict]:
        """Search for conversations by name (fuzzy match).

        Args:
            name: Conversation name to search for (supports partial matching)

        Returns:
            List of matching conversations: [{"id": ..., "title": ..., "type": ...}, ...]
        """
        conversations = self.cache.get("_conversations", {})
        results = []
        name_lower = name.lower()

        for title, info in conversations.items():
            # Check if name matches (case-insensitive partial match)
            if name_lower in title.lower():
                results.append({
                    "id": info["id"],
                    "title": title,
                    "type": info.get("type", "unknown"),
                    "lastSeen": info.get("lastSeen", ""),
                })

        # Sort by relevance: exact match first, then by lastSeen
        def sort_key(conv):
            is_exact = conv["title"].lower() == name_lower
            return (not is_exact, conv.get("lastSeen", "") or "")

        results.sort(key=sort_key, reverse=True)
        return results

    def get_conversation_id(self, name: str) -> Optional[str]:
        """Get conversation ID by name (exact match preferred, then best fuzzy match).

        Args:
            name: Conversation name to look up

        Returns:
            Conversation ID string or None if not found
        """
        conversations = self.cache.get("_conversations", {})

        # Try exact match first (case-insensitive)
        name_lower = name.lower()
        for title, info in conversations.items():
            if title.lower() == name_lower:
                return info["id"]

        # Fall back to fuzzy match - return best match
        matches = self.find_conversation_by_name(name)
        if matches:
            return matches[0]["id"]

        return None

    def get_all_conversations(self) -> dict:
        """Get all cached conversations.

        Returns:
            Dict of {title: {"id": ..., "type": ..., "lastSeen": ...}}
        """
        return self.cache.get("_conversations", {})

    # ========== Utility Methods ==========

    def cleanup_old_entries(self, days: int = 90):
        """Clean up old cache entries.

        Args:
            days: Entries older than this many days will be removed
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        cleaned = False

        # Clean up member entries
        for conv_id in list(self.cache.keys()):
            if conv_id in ("_global", "_conversations"):
                continue

            for mri in list(self.cache[conv_id].keys()):
                member = self.cache[conv_id][mri]
                try:
                    last_seen = datetime.fromisoformat(member.get("lastSeen", ""))
                    if last_seen < cutoff:
                        del self.cache[conv_id][mri]
                        cleaned = True
                except (ValueError, TypeError):
                    pass

            # Remove empty conversations
            if not self.cache[conv_id]:
                del self.cache[conv_id]
                cleaned = True

        # Clean up conversation entries
        conversations = self.cache.get("_conversations", {})
        for title in list(conversations.keys()):
            try:
                last_seen = datetime.fromisoformat(conversations[title].get("lastSeen", ""))
                if last_seen < cutoff:
                    del conversations[title]
                    cleaned = True
            except (ValueError, TypeError):
                pass

        if cleaned:
            self._save_cache()

    def get_cache_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dict with conversations count, members count, and cache file path
        """
        member_conversations = len([
            k for k in self.cache.keys()
            if k not in ("_global", "_conversations")
        ])
        members = sum(
            len(v) for k, v in self.cache.items()
            if k not in ("_global", "_conversations")
        )
        cached_conversations = len(self.cache.get("_conversations", {}))

        return {
            "member_conversations": member_conversations,
            "members": members,
            "cached_conversations": cached_conversations,
            "cache_file": self.cache_file,
        }

    def clear(self):
        """Clear all cached data and delete cache file."""
        self.cache = {}
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)


# Global cache instance (singleton)
_global_cache: Optional[TeamsCache] = None


def get_cache() -> TeamsCache:
    """Get global teams cache instance (singleton pattern).

    Ensures the entire application shares a single cache instance,
    avoiding multiple file reads/writes.

    Returns:
        TeamsCache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = TeamsCache()
    return _global_cache
