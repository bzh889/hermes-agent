"""[API Service] Low-level HTTP implementation for Messages.

Handles get, send, edit, delete, reply, and forward operations.
"""

import json
import re
import urllib.parse
from datetime import datetime, timezone

from teams_skype_sdk.cache import get_cache

from ._constants import MSG_BASE, AMS_BASE_URL, MAX_PAGE_SIZE, API_MAX_PAGE_SIZE, MAX_MESSAGE_HTML_BYTES, EMOJI_REACTION_MAP
from ._files import _extract_ams_id
from ._http import HTTPLayer
from teams_skype_sdk.utils import agent_error


class MessagesService:
    """Message retrieval, sending, editing, deletion, reply, and forward."""

    def __init__(self, http: HTTPLayer):
        self._http = http

    # ---- Helpers (absorbed from _base.py) -----------------------------------

    def _get_my_display_name(self) -> str:
        """Get display name of the current user from cache or default."""
        cache = get_cache()
        my_oid = self._http._get_my_oid()
        if my_oid:
            my_mri = f"8:orgid:{my_oid}"
            name = cache.get_display_name(my_mri)
            if name:
                return name
        return "You"

    def _get_recent_context(self, conversation_id: str, count: int = 3) -> list[dict]:
        """Fetch last N messages for post-action context preview."""
        try:
            messages = self.get(conversation_id, limit=count)
            return [
                {
                    "sender": m.get("sender", "Unknown"),
                    "text": m.get("content", "")[:100],
                    "time": m.get("timestamp", ""),
                    "id": m.get("id", ""),
                }
                for m in messages
            ]
        except Exception:
            return []

    # ---- Content size validation ---------------------------------------------

    def _validate_content_size(self, html_content: str, action: str) -> None:
        """Raise ValueError if HTML content exceeds Teams API limit."""
        size_bytes = len(html_content.encode("utf-8"))
        if size_bytes <= MAX_MESSAGE_HTML_BYTES:
            return
        overage = size_bytes - MAX_MESSAGE_HTML_BYTES
        size_kb = size_bytes / 1024
        limit_kb = MAX_MESSAGE_HTML_BYTES / 1024

        if action == "edit_message":
            strategy = (
                "Shorten the content. "
                "Strategies: (1) Remove verbose sections, "
                "(2) Delete this message and send the new content as a fresh message chain instead."
            )
        else:
            strategy = (
                "Shorten the content or split into multiple messages. "
                "Strategies: (1) Remove verbose sections, (2) Send in 2-3 parts with '(Part 1/N)' prefix, "
                "(3) For data tables, reduce rows or use teams_send_card."
            )

        raise ValueError(agent_error(
            action,
            f"Message too large: {size_kb:.1f} KB (limit: {limit_kb:.1f} KB, over by {overage:,} bytes). "
            f"HTML is typically 1.5-3x larger than source text. "
            f"CJK characters use 3 bytes each in UTF-8.",
            strategy,
        ))

    # ---- Public methods -----------------------------------------------------

    def get(self, conversation_id: str, limit: int = None) -> list[dict]:
        """Get messages from a specific conversation.

        Uses backwardLink pagination to traverse full history.
        When limit is None (default), fetches ALL messages with no cap.
        When limit is set, stops after returning that many messages.

        Args:
            conversation_id: The conversation/chat ID
            limit: Maximum number of messages to return, or None for all (default: None)

        Returns:
            List of message dictionaries with sender, content, timestamp, newest first
        """
        encoded_conv_id = urllib.parse.quote(conversation_id, safe='')
        url = f"{MSG_BASE}/conversations/{encoded_conv_id}/messages"
        params = {"pageSize": API_MAX_PAGE_SIZE}

        results = []
        seen_ids: set = set()

        while url:
            response = self._http._request("GET", url, params=params)
            data = response.json()
            raw_msgs = data.get("messages", [])
            params = {}  # subsequent requests use full URL from backwardLink

            if not raw_msgs:
                break

            for msg in raw_msgs:
                msg_id = msg.get("id", "")
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                normalized = self._normalize_raw(msg, conversation_id)
                if normalized:
                    results.append(normalized)
                    if limit is not None and len(results) >= limit:
                        return results

            url = data.get("_metadata", {}).get("backwardLink")

        return results

    def get_page(self, conversation_id: str, page_size: int = 20,
                 msg_base: str = None) -> list[dict]:
        """Fetch a single page of messages (no backwardLink chasing).

        Ideal for poll-loop scenarios that only need the most recent messages.
        Supports a custom ``msg_base`` for regional endpoint discovery
        (e.g. gateways that learn the region from Skype authz).

        Args:
            conversation_id: Conversation/chat ID
            page_size: Number of messages per page (default 20)
            msg_base: Override MSG_BASE for regional endpoints.
                      Defaults to ``MSG_BASE`` constant.

        Returns:
            List of normalized message dicts (newest first).
        """
        base = msg_base or MSG_BASE
        encoded = urllib.parse.quote(conversation_id, safe="")
        url = f"{base}/conversations/{encoded}/messages"
        params = {"pageSize": page_size, "startTime": 0}

        response = self._http._request("GET", url, params=params)
        data = response.json()
        raw_msgs = data.get("messages") or []

        results = []
        for msg in raw_msgs:
            normalized = self._normalize_raw(msg, conversation_id)
            if normalized:
                results.append(normalized)
        return results

    def get_by_date(
        date_from: str = None, date_to: str = None,
        limit: int = 200,
    ) -> list[dict]:
        """Fetch messages using backwardLink pagination, with optional date filtering.

        Unlike get(), this follows _metadata.backwardLink to traverse full
        conversation history. When date_from/date_to are None, fetches all messages.

        Args:
            conversation_id: The conversation/chat ID
            date_from: Start date inclusive (YYYY-MM-DD), or None for no lower bound
            date_to: End date inclusive (YYYY-MM-DD), or None for no upper bound
            limit: Max messages to return

        Returns:
            List of message dicts, newest first
        """
        cutoff_ms = None
        dt_to = None
        if date_from:
            dt_from = datetime(*[int(x) for x in date_from.split("-")], tzinfo=timezone.utc)
            cutoff_ms = int(dt_from.timestamp() * 1000)
        if date_to:
            dt_to = datetime(
                *[int(x) for x in date_to.split("-")],
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )

        encoded_conv_id = urllib.parse.quote(conversation_id, safe='')
        url = f"{MSG_BASE}/conversations/{encoded_conv_id}/messages"
        params = {"pageSize": API_MAX_PAGE_SIZE}

        results = []
        seen_ids: set = set()

        while url:
            response = self._http._request("GET", url, params=params)
            data = response.json()
            raw_msgs = data.get("messages", [])
            params = {}  # subsequent requests use full URL from backwardLink

            if not raw_msgs:
                break

            oldest_id = min(int(m.get("id", "0")) for m in raw_msgs)
            if cutoff_ms and oldest_id < cutoff_ms:
                stop_after = True
            else:
                stop_after = False

            for msg in raw_msgs:
                msg_id = msg.get("id", "")
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                msg_ms = int(msg_id) if msg_id else 0
                if cutoff_ms and msg_ms < cutoff_ms:
                    continue
                if dt_to:
                    msg_dt = datetime.fromtimestamp(msg_ms / 1000, tz=timezone.utc)
                    if msg_dt > dt_to:
                        continue

                normalized = self._normalize_raw(msg, conversation_id)
                if normalized:
                    results.append(normalized)
                    if len(results) >= limit:
                        return results

            if stop_after:
                break

            url = data.get("_metadata", {}).get("backwardLink")

        return results

    def _normalize_raw(self, msg: dict, conversation_id: str) -> dict | None:
        """Normalize a raw MSG_BASE message dict. Returns None for non-text messages."""
        if msg.get("messagetype", "") not in ("", "Text", "RichText/Html"):
            return None

        cache = get_cache()
        sender_mri = self._http._extract_mri_from_url(msg.get("from", ""))
        sender_name = msg.get("imdisplayname") or "Unknown"

        raw_content = msg.get("content", "")
        is_forwarded = 'itemtype="http://schema.skype.com/Forward"' in raw_content
        text, inline_images = self._http._process_message_content(raw_content)

        message = {
            "id": msg.get("id", ""),
            "from": sender_mri,
            "sender": sender_name,
            "content": text,
            "timestamp": self._http._format_timestamp(
                msg.get("originalarrivaltime") or msg.get("composetime")
            ),
            "type": msg.get("messagetype", "text"),
            # Preserve raw data for downstream echo guard / fingerprint detection
            "_raw_content": raw_content,
            "_raw_properties": msg.get("properties"),
        }

        if is_forwarded:
            message["forwarded"] = True

        # ---- Extract attachments (4-layer, dedup via _extract_message_attachments) ----
        attachments = self._http._extract_message_attachments(msg, raw_content)
        if attachments:
            message["attachments"] = attachments

        # ---- Inline images from _process_message_content ----
        if inline_images:
            img_attach = [
                {"url": i["src"], "name": i.get("alt", "image"), "kind": i.get("kind", "image")}
                for i in inline_images
                if i.get("kind") == "image" and i.get("src")
            ]
            if img_attach:
                # Merge with dedup against existing attachments
                seen = {a["url"] for a in attachments} if attachments else set()
                for ia in img_attach:
                    if ia["url"] not in seen:
                        seen.add(ia["url"])
                        message.setdefault("attachments", []).append(ia)

        if sender_mri and sender_name and sender_name != "Unknown":
            cache.add_member(conversation_id, sender_mri, sender_name)

        return message

    @staticmethod
    def _build_mention_html(mentions: list[dict]) -> tuple[str, list[dict]]:
        """Build @mention HTML spans and properties from resolved mention dicts.

        Args:
            mentions: List of dicts with keys: mri, displayName

        Returns:
            Tuple of (html_suffix with mention spans, mention properties list)
        """
        html_parts = []
        props = []
        for idx, m in enumerate(mentions):
            mri = m["mri"]
            name = m["displayName"]
            html_parts.append(
                f'<span itemtype="http://schema.skype.com/Mention" '
                f'itemscope="" itemid="{idx}">{name}</span>'
            )
            props.append({
                "@type": "http://schema.skype.com/Mention",
                "itemid": idx,
                "mri": mri,
                "mentionType": "person",
                "displayName": name,
            })
        return "&nbsp;".join(html_parts), props

    def send(
        self, conversation_id: str, content: str,
        ams_refs: list[str] | None = None, file_schemas: list[dict] | None = None,
        is_html: bool = False, return_context: bool = True,
        mentions: list[dict] | None = None,
    ) -> dict:
        """Send a message to a conversation.

        Args:
            conversation_id: The conversation/chat ID
            content: Message content (plain text, markdown, or HTML)
            ams_refs: Optional list of AMS object IDs for image attachments
            file_schemas: Optional list of SharePoint file schema dicts
            is_html: If True, skip markdown conversion
            return_context: If True, include conversation preview in result
            mentions: Optional list of dicts with 'mri' and 'displayName' for @mentions

        Returns:
            Dictionary with message ID and status
        """
        encoded_conv_id = urllib.parse.quote(conversation_id, safe='')
        url = f"{MSG_BASE}/conversations/{encoded_conv_id}/messages"

        if is_html:
            html_content = content
        else:
            html_content = self._http._markdown_to_teams_html(content)

        # Inject @mention spans into HTML (append inside last <p> or wrap in new <p>)
        mention_props = None
        if mentions:
            mention_html, mention_props = self._build_mention_html(mentions)
            # Insert before closing </p> if present, otherwise append wrapped
            if html_content.rstrip().endswith("</p>"):
                html_content = html_content.rstrip()[:-4] + f"&nbsp;{mention_html}</p>"
            else:
                html_content += f"<p>{mention_html}</p>"

        self._validate_content_size(html_content, "send_message")

        payload = {
            "content": html_content,
            "messagetype": "RichText/Html",
            "contenttype": "text",
        }

        # ---- Echo guard: mark outgoing messages as bot-sent ----
        payload.setdefault("properties", {})
        payload["properties"]["hermes_sender"] = "bot"

        if mention_props:
            payload["properties"]["mentions"] = json.dumps(mention_props)

        if ams_refs:
            payload["amsreferences"] = ams_refs

        if file_schemas:
            payload.setdefault("properties", {})
            payload["properties"]["files"] = json.dumps(file_schemas)

        response = self._http._request("POST", url, json=payload)

        result_data = response.json()
        result = {
            "id": result_data.get("id", "") or str(result_data.get("OriginalArrivalTime", "")),
            "status": "sent",
            "timestamp": self._http._format_timestamp(result_data.get("composetime")),
        }
        if return_context:
            recent = self._get_recent_context(conversation_id, count=3)
            msg_id = result["id"]
            sent_ids = {m.get("id") for m in recent}
            if msg_id and msg_id not in sent_ids:
                my_name = self._get_my_display_name()
                recent.append({
                    "sender": my_name,
                    "text": self._http._extract_text_content(content)[:100],
                    "time": result["timestamp"],
                    "id": msg_id,
                    "is_self": True,
                })
                recent = recent[-3:]
            result["conversation_preview"] = recent
        return result

    def edit(self, conversation_id: str, message_id: str, content: str) -> dict:
        """Edit an existing message in a conversation."""
        encoded_conv_id = urllib.parse.quote(conversation_id, safe='')
        url = f"{MSG_BASE}/conversations/{encoded_conv_id}/messages/{message_id}"

        html_content = self._http._markdown_to_teams_html(content)

        self._validate_content_size(html_content, "edit_message")

        payload = {
            "content": html_content,
            "messagetype": "RichText/Html",
        }

        response = self._http._request("PUT", url, json=payload)

        if response.content:
            result = response.json()
            return {
                "id": result.get("id", message_id),
                "status": "edited",
                "timestamp": self._http._format_timestamp(result.get("composetime")),
            }
        return {
            "id": message_id,
            "status": "edited",
            "timestamp": "",
        }

    def delete(self, conversation_id: str, message_id: str) -> dict:
        """Delete a message from a conversation."""
        encoded_conv_id = urllib.parse.quote(conversation_id, safe='')
        url = f"{MSG_BASE}/conversations/{encoded_conv_id}/messages/{message_id}"

        self._http._request("DELETE", url)

        return {
            "id": message_id,
            "status": "deleted",
        }

    def reply(
        self, conversation_id: str, message_id: str,
        content: str, return_context: bool = True,
    ) -> dict:
        """Reply to a specific message using Teams native blockquote format."""
        encoded_conv_id = urllib.parse.quote(conversation_id, safe='')

        fetch_url = f"{MSG_BASE}/conversations/{encoded_conv_id}/messages"
        fetch_resp = self._http._request("GET", fetch_url, params={"pageSize": 5})
        raw_messages = fetch_resp.json().get("messages", [])

        original = None
        for msg in raw_messages:
            if str(msg.get("id")) == str(message_id):
                original = msg
                break

        html_content = self._http._markdown_to_teams_html(content)

        if original:
            sender_name = original.get("imdisplayname") or "Unknown"
            sender_from = original.get("from", "")
            sender_mri = sender_from.rsplit("/", 1)[-1] if "/contacts/" in sender_from else ""

            preview = self._http._extract_text_content(original.get("content", ""))[:100]

            reply_html = (
                f'<blockquote itemscope="" itemtype="http://schema.skype.com/Reply" itemid="{message_id}">'
                f'<strong itemprop="mri" itemid="{sender_mri}">{sender_name}</strong>'
                f'<span itemprop="time" itemid="{message_id}"></span>'
                f'<p itemprop="preview">{preview}</p>'
                f'</blockquote>'
                f'{html_content}'
            )

            qtd_msgs = json.dumps([{
                "messageId": str(message_id),
                "sender": sender_mri,
                "time": int(message_id),
            }])

            properties = {
                "replyChainMessageId": message_id,
                "qtdMsgs": qtd_msgs,
            }
        else:
            reply_html = html_content
            properties = {
                "replyChainMessageId": message_id,
            }

        # Quote Shedding: if blockquote pushes total over limit but user
        # content alone is fine, drop the blockquote (threading preserved
        # via replyChainMessageId).  If user content itself is too large,
        # raise the normal size error.
        reply_size = len(reply_html.encode("utf-8"))
        if reply_size > MAX_MESSAGE_HTML_BYTES:
            user_size = len(html_content.encode("utf-8"))
            if user_size <= MAX_MESSAGE_HTML_BYTES:
                reply_html = html_content
            else:
                self._validate_content_size(html_content, "reply_message")

        url = f"{MSG_BASE}/conversations/{encoded_conv_id}/messages"
        payload = {
            "content": reply_html,
            "messagetype": "RichText/Html",
            "contenttype": "text",
            "properties": {**properties, "hermes_sender": "bot"},
        }

        response = self._http._request("POST", url, json=payload)

        result_data = response.json()
        result = {
            "id": result_data.get("id", "") or str(result_data.get("OriginalArrivalTime", "")),
            "status": "sent",
            "timestamp": self._http._format_timestamp(result_data.get("composetime")),
        }
        if return_context:
            recent = self._get_recent_context(conversation_id, count=3)
            msg_id = result["id"]
            sent_ids = {m.get("id") for m in recent}
            if msg_id and msg_id not in sent_ids:
                my_name = self._get_my_display_name()
                recent.append({
                    "sender": my_name,
                    "text": self._http._extract_text_content(content)[:100],
                    "time": result["timestamp"],
                    "id": msg_id,
                    "is_self": True,
                })
                recent = recent[-3:]
            result["conversation_preview"] = recent
        return result

    def forward(
        self,
        source_conversation_id: str,
        message_id: str,
        target_conversation_id: str,
    ) -> dict:
        """Forward a message using Teams blockquote format.

        Raises:
            ValueError: If the original message is not found
        """
        encoded_src = urllib.parse.quote(source_conversation_id, safe='')
        url = f"{MSG_BASE}/conversations/{encoded_src}/messages"
        response = self._http._request("GET", url, params={"pageSize": 50})
        raw_messages = response.json().get("messages", [])

        original = None
        for msg in raw_messages:
            if str(msg.get("id")) == str(message_id):
                original = msg
                break

        if not original:
            raise ValueError(f"Message {message_id} not found in conversation {source_conversation_id}")

        sender_name = original.get("imdisplayname") or "Unknown"
        content = original.get("content", "")

        forward_html = (
            '<blockquote itemtype="http://schema.skype.com/Forward">'
            f'<p><strong>Forwarded from {sender_name}:</strong></p>'
            f'{content}'
            '</blockquote>'
        )

        return self.send(target_conversation_id, forward_html, is_html=True)

    # ---- Pinned messages (via chatsvcs thread properties) --------------------

    _THREADS_BASE = "https://amer.ng.msg.teams.microsoft.com/v1/threads"

    def list_pinned(self, conversation_id: str) -> list[dict]:
        """List pinned messages in a conversation."""
        url = f"{self._THREADS_BASE}/{conversation_id}?view=msnp24Equivalent"
        resp = self._http._request("GET", url)
        raw = resp.json().get("properties", {}).get("pinnedItems", "[]")
        return json.loads(raw)

    def pin(self, conversation_id: str, message_id: str) -> dict:
        """Pin a message in a conversation."""
        pinned = self.list_pinned(conversation_id)
        if any(p["itemId"] == str(message_id) for p in pinned):
            return {"status": "already_pinned", "id": message_id}
        pinned.append({"itemId": str(message_id), "itemType": "Message"})
        self._set_pinned(conversation_id, pinned)
        return {"status": "pinned", "id": message_id}

    def unpin(self, conversation_id: str, message_id: str) -> dict:
        """Unpin a message from a conversation."""
        pinned = self.list_pinned(conversation_id)
        new_pinned = [p for p in pinned if p["itemId"] != str(message_id)]
        if len(new_pinned) == len(pinned):
            return {"status": "not_pinned", "id": message_id}
        self._set_pinned(conversation_id, new_pinned)
        return {"status": "unpinned", "id": message_id}

    def _set_pinned(self, conversation_id: str, pinned: list[dict]) -> None:
        """Update the pinnedItems thread property."""
        url = f"{self._THREADS_BASE}/{conversation_id}/properties?name=pinnedItems"
        self._http._request("PUT", url, json={"pinnedItems": json.dumps(pinned)})
