"""Microsoft Graph API integration for Teams MCP.

Provides user lookup, calendar scheduling, and compound availability
queries using delegated Graph API tokens.
"""

import os
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING
# from zoneinfo import ZoneInfo  # Removed - using timezone(timedelta) instead

import requests

from .config import VERIFY_SSL, DEFAULT_TIMEOUT, TIMEZONE
from .utils import agent_error

if TYPE_CHECKING:
    from .auth import TeamsAuth

# Constants
GRAPH_SCOPE = "https://graph.microsoft.com/.default offline_access"
GRAPH_CHAT_SCOPE = "https://graph.microsoft.com/Chat.Read offline_access"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
TOKEN_REFRESH_BUFFER = 300


def extract_aad_id(mri: str) -> str:
    """Extract AAD UUID from a Teams MRI string.

    Args:
        mri: Teams MRI string (e.g., '8:orgid:abc-123-def')

    Returns:
        AAD UUID string, or original value if not an org MRI.
    """
    if mri.startswith("8:orgid:"):
        return mri[8:]
    return mri


class GraphToken:
    """Graph API token manager with auto-refresh.

    Tokens are in-memory only (not persisted to token_cache.json).
    Obtained via TeamsAuth.exchange_for_scope() for thread-safe
    refresh_token handling.
    """

    def __init__(self, auth: 'TeamsAuth', scope: str = GRAPH_SCOPE):
        self.auth = auth
        self._scope = scope
        self._token: Optional[str] = None
        self._expires_at: Optional[int] = None

    def is_expired(self) -> bool:
        if self._token is None or self._expires_at is None:
            return True
        return int(time.time()) >= (self._expires_at - TOKEN_REFRESH_BUFFER)

    def get_token(self) -> str:
        """Get a valid Graph token, refreshing if necessary."""
        if self.is_expired():
            self.refresh()
        return self._token

    def refresh(self) -> str:
        """Force refresh the Graph token."""
        result = self.auth.exchange_for_scope(self._scope)
        self._token = result.get("access_token")
        expires_in = result.get("expires_in", 3600)
        self._expires_at = int(time.time()) + expires_in
        return self._token


class GraphAPI:
    """Microsoft Graph API client using delegated tokens."""

    def __init__(self, graph_token: GraphToken, verify_ssl: bool = VERIFY_SSL):
        self.graph_token = graph_token
        self._chat_token: Optional[GraphToken] = None  # lazy, Chat.Read scope
        self.verify_ssl = verify_ssl
        self._session = requests.Session()

    def _get_chat_token(self) -> GraphToken:
        """Get (or lazily create) a Chat.Read scoped token."""
        if self._chat_token is None:
            self._chat_token = GraphToken(self.graph_token.auth, GRAPH_CHAT_SCOPE)
        return self._chat_token

    def _headers(self, token: Optional[GraphToken] = None) -> dict:
        tok = token or self.graph_token
        return {
            "Authorization": f"Bearer {tok.get_token()}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make an authenticated Graph API request."""
        if not url.startswith("http"):
            url = f"{GRAPH_BASE_URL}{url}"

        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        kwargs.setdefault("verify", self.verify_ssl)
        if "headers" not in kwargs:
            kwargs["headers"] = self._headers()

        response = self._session.request(method, url, **kwargs)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            body = response.text[:500] if response.text else "(empty)"
            raise requests.HTTPError(
                f"{e} | Response body: {body}",
                response=response,
            ) from e
        return response

    # --- User operations ---

    def get_me(self) -> dict:
        """Get current user's profile."""
        return self._request("GET", "/me").json()

    def get_user(self, identifier: str) -> dict:
        """Get a user profile by ID or email (userPrincipalName)."""
        return self._request("GET", f"/users/{identifier}").json()

    def search_users(self, query: str) -> list[dict]:
        """Search for users by displayName or mail prefix.

        Args:
            query: Search string (name or email prefix).

        Returns:
            List of matching user profile dicts.
        """
        # Use $filter with startswith for both displayName and mail
        filter_str = (
            f"startswith(displayName,'{query}') or "
            f"startswith(mail,'{query}')"
        )
        response = self._request(
            "GET", "/users",
            params={"$filter": filter_str, "$top": 10},
        )
        return response.json().get("value", [])

    # --- Calendar operations ---

    def get_schedule(
        self,
        emails: list[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: int = 30,
    ) -> list[dict]:
        """Get free/busy schedule for multiple users.

        Args:
            emails: List of email addresses to check.
            start: Window start (defaults to now).
            end: Window end (defaults to end of today).
            interval: Availability interval in minutes.

        Returns:
            List of schedule result dicts from Graph API.
        """
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)

        if start is None:
            start = now
        if end is None:
            end = now.replace(hour=23, minute=59, second=59)

        body = {
            "schedules": emails,
            "startTime": {
                "dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": TIMEZONE,
            },
            "endTime": {
                "dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": TIMEZONE,
            },
            "availabilityViewInterval": interval,
        }

        response = self._request("POST", "/me/calendar/getSchedule", json=body)
        return response.json().get("value", [])

    # --- Compound operations ---

    def find_common_availability(
        self, user_queries: list[str], date_str: Optional[str] = None,
    ) -> dict:
        """Find meeting slots where all participants are free.

        Resolves user names -> emails, checks schedules, computes intersection.
        Includes ambiguity guard: fails if any name matches multiple users.

        Args:
            user_queries: List of user name/email strings.
            date_str: Date in YYYY-MM-DD format (defaults to today).

        Returns:
            Dict with resolved_users, available_slots, and notes.

        Raises:
            ValueError: If any user is ambiguous (2+ matches) or not found.
        """
        tz = timezone(timedelta(hours=8))

        # Parse target date
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
        else:
            target_date = datetime.now(tz)

        start = target_date.replace(hour=9, minute=0, second=0)
        end = target_date.replace(hour=18, minute=0, second=0)

        # Resolve each user with ambiguity guard
        resolved: list[dict] = []
        for query in user_queries:
            query = query.strip()
            if not query:
                continue

            # If it looks like an email, use directly
            if "@" in query:
                resolved.append({"query": query, "email": query, "name": query})
                continue

            results = self.search_users(query)

            if len(results) == 0:
                raise ValueError(
                    agent_error(
                        "find_common_availability",
                        f"User '{query}' not found in directory.",
                        "Try using the full name or email address.",
                    )
                )
            elif len(results) == 1:
                user = results[0]
                email = user.get("mail") or user.get("userPrincipalName", "")
                resolved.append({
                    "query": query,
                    "email": email,
                    "name": user.get("displayName", query),
                    "department": user.get("department", ""),
                })
            else:
                # Ambiguity -- list all candidates with department
                candidates = []
                for u in results[:5]:
                    dept = u.get("department", "")
                    email = u.get("mail") or u.get("userPrincipalName", "")
                    name = u.get("displayName", "")
                    dept_str = f" ({dept})" if dept else ""
                    candidates.append(f"  - {name}{dept_str} -- {email}")
                candidate_list = "\n".join(candidates)
                raise ValueError(
                    agent_error(
                        "find_common_availability",
                        f"Ambiguous user '{query}'. Found {len(results)} matches:\n{candidate_list}",
                        "Ask the user which person they mean, or provide the full email address.",
                    )
                )

        if not resolved:
            raise ValueError(
                agent_error(
                    "find_common_availability",
                    "No users specified.",
                    "Provide at least one user name or email.",
                )
            )

        # Fetch schedules
        emails = [r["email"] for r in resolved]
        schedules = self.get_schedule(emails, start, end, interval=30)

        # Parse availability views and find common free slots
        available_slots = []
        notes = []

        if schedules:
            # Each schedule has an availabilityView string: 0=free, 1=tentative, 2=busy, 3=oof, 4=working elsewhere
            status_map = {"1": "tentative", "2": "busy", "3": "OOF", "4": "working elsewhere"}
            slot_count = max(
                (len(s.get("availabilityView", "")) for s in schedules), default=0,
            )

            for slot_idx in range(slot_count):
                slot_start = start + timedelta(minutes=30 * slot_idx)
                slot_end = slot_start + timedelta(minutes=30)
                all_free = True
                slot_notes = []

                for i, sched in enumerate(schedules):
                    view = sched.get("availabilityView", "")
                    name = resolved[i]["name"] if i < len(resolved) else emails[i]
                    if slot_idx < len(view):
                        status = view[slot_idx]
                        if status != "0":
                            all_free = False
                            slot_notes.append(f"{name}: {status_map.get(status, 'unavailable')}")
                    else:
                        # Missing data != free — treat as unavailable
                        all_free = False
                        slot_notes.append(f"{name}: unknown (no data)")

                if all_free:
                    available_slots.append({
                        "start": slot_start.strftime("%H:%M"),
                        "end": slot_end.strftime("%H:%M"),
                    })
                elif slot_notes:
                    for note in slot_notes:
                        if note not in notes:
                            notes.append(note)

        # Merge adjacent free slots
        merged_slots = []
        for slot in available_slots:
            if merged_slots and merged_slots[-1]["end"] == slot["start"]:
                merged_slots[-1]["end"] = slot["end"]
            else:
                merged_slots.append(dict(slot))

        return {
            "resolved_users": resolved,
            "date": target_date.strftime("%Y-%m-%d"),
            "available_slots": merged_slots,
            "notes": notes,
        }

    # --- OneDrive operations (delegated /me context) ---

    _SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024  # 4 MB

    def upload_to_onedrive(self, file_bytes: bytes, original_filename: str) -> dict:
        """Upload a file to OneDrive in the TeamsMCP subfolder.

        Uses dual-mode upload:
        - <= 4MB: Simple PUT (one request)
        - > 4MB: Upload session with single PUT + Content-Range

        Args:
            file_bytes: Raw file content bytes.
            original_filename: Original filename (for extension extraction).

        Returns:
            Dict with id, fileName, webUrl, downloadUrl, size.
        """
        ext = os.path.splitext(original_filename)[1]
        unique_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
        target_path = f"/Microsoft Teams Chat Files/TeamsMCP/{unique_name}"

        read_timeout = max(120, len(file_bytes) / (100 * 1024))
        timeout = (10, read_timeout)
        headers = self._headers()
        headers["Content-Type"] = "application/octet-stream"

        if len(file_bytes) <= self._SIMPLE_UPLOAD_LIMIT:
            # Simple upload
            url = f"{GRAPH_BASE_URL}/me/drive/root:{target_path}:/content"
            response = self._session.put(
                url, headers=headers, data=file_bytes,
                verify=self.verify_ssl, timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()
        else:
            # Upload session (single PUT with Content-Range)
            session_url = f"{GRAPH_BASE_URL}/me/drive/root:{target_path}:/createUploadSession"
            session_headers = self._headers()  # JSON content type for session creation
            session_resp = self._session.post(
                session_url, headers=session_headers, json={},
                verify=self.verify_ssl, timeout=DEFAULT_TIMEOUT,
            )
            session_resp.raise_for_status()
            upload_url = session_resp.json()["uploadUrl"]

            file_size = len(file_bytes)
            response = self._session.put(
                upload_url,
                headers={
                    "Content-Length": str(file_size),
                    "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                },
                data=file_bytes,
                verify=self.verify_ssl, timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()

        return {
            "id": result["id"],
            "fileName": result["name"],
            "webUrl": result.get("webUrl", ""),
            "downloadUrl": result.get("@microsoft.graph.downloadUrl", ""),
            "size": result.get("size", len(file_bytes)),
        }

    def create_sharing_link(self, item_id: str) -> str:
        """Create an organization-wide view link for a OneDrive item.

        Args:
            item_id: OneDrive item ID from upload_to_onedrive().

        Returns:
            Sharing URL string.
        """
        response = self._request(
            "POST",
            f"/me/drive/items/{item_id}/createLink",
            json={"type": "view", "scope": "organization"},
        )
        return response.json().get("link", {}).get("webUrl", "")

    def get_sharepoint_ids(self, item_id: str) -> dict:
        """Get SharePoint IDs for a OneDrive item.

        Args:
            item_id: OneDrive item ID from upload_to_onedrive().

        Returns:
            Dict with listItemUniqueId, siteId, siteUrl, etc.
        """
        response = self._request(
            "GET", f"/me/drive/items/{item_id}?select=sharepointIds",
        )
        return response.json().get("sharepointIds", {})

    def get_chat_messages(
        self,
        chat_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch messages from a chat with server-side date filtering.

        Uses Graph API $filter=createdDateTime for true historical search,
        unlike the MSG_BASE API which only returns the latest ~50 messages.

        Args:
            chat_id: Teams chat/conversation ID.
            date_from: Start date (YYYY-MM-DD), inclusive.
            date_to: End date (YYYY-MM-DD), inclusive.
            limit: Max messages to return (follows @odata.nextLink).

        Returns:
            List of raw Graph API message dicts.
        """
        params: dict = {"$top": min(limit, 50)}
        filters = []
        if date_from:
            filters.append(f"createdDateTime ge {date_from}T00:00:00Z")
        if date_to:
            filters.append(f"createdDateTime le {date_to}T23:59:59Z")
        if filters:
            params["$filter"] = " and ".join(filters)

        encoded_id = urllib.parse.quote(chat_id, safe="")
        url = f"{GRAPH_BASE_URL}/chats/{encoded_id}/messages"
        chat_token = self._get_chat_token()
        all_messages: list[dict] = []

        while len(all_messages) < limit:
            response = self._request("GET", url, params=params,
                                     headers=self._headers(chat_token))
            data = response.json()
            items = data.get("value", [])
            all_messages.extend(items)
            next_link = data.get("@odata.nextLink")
            if not next_link or not items:
                break
            url = next_link
            params = {}

        return all_messages[:limit]

    def delete_onedrive_item(self, item_id: str) -> bool:
        """Delete a OneDrive item. Used for orphan cleanup on failure."""
        response = self._session.delete(
            f"{GRAPH_BASE_URL}/me/drive/items/{item_id}",
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=DEFAULT_TIMEOUT,
        )
        return response.status_code in (200, 204)

