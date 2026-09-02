"""[API Service] Emoji reaction operations on messages via Graph API."""

import requests

from ._constants import VALID_REACTIONS, REACTION_EMOJI_MAP


class ReactionsService:
    """Send and remove emoji reactions on Teams messages using Graph API."""

    def __init__(self, graph_api):
        self._graph = graph_api

    def send(self, conversation_id: str, message_id: str, reaction: str) -> dict:
        """Send a reaction (emoji) to a message.

        Uses Graph API beta endpoint: POST /beta/chats/{id}/messages/{id}/setReaction

        Raises:
            ValueError: If reaction type is invalid
        """
        if reaction not in VALID_REACTIONS:
            raise ValueError(
                f"Invalid reaction '{reaction}'. "
                f"Valid reactions: {', '.join(sorted(VALID_REACTIONS))}"
            )

        emoji = REACTION_EMOJI_MAP[reaction]
        url = (
            f"https://graph.microsoft.com/beta/chats/{conversation_id}"
            f"/messages/{message_id}/setReaction"
        )

        try:
            self._graph._request("POST", url, json={"reactionType": emoji})
            return {"status": "reacted", "reaction": reaction, "message_id": message_id}
        except requests.HTTPError as e:
            resp = getattr(e, "response", None)
            if resp is not None and resp.status_code == 409:
                return {"status": "reacted", "reaction": reaction, "message_id": message_id}
            raise

    def remove(self, conversation_id: str, message_id: str, reaction: str) -> dict:
        """Remove a reaction from a message.

        Uses Graph API beta endpoint: POST /beta/chats/{id}/messages/{id}/unsetReaction

        Raises:
            ValueError: If reaction type is invalid
        """
        if reaction not in VALID_REACTIONS:
            raise ValueError(
                f"Invalid reaction '{reaction}'. "
                f"Valid reactions: {', '.join(sorted(VALID_REACTIONS))}"
            )

        emoji = REACTION_EMOJI_MAP[reaction]
        url = (
            f"https://graph.microsoft.com/beta/chats/{conversation_id}"
            f"/messages/{message_id}/unsetReaction"
        )

        try:
            self._graph._request("POST", url, json={"reactionType": emoji})
            return {"status": "removed", "reaction": reaction, "message_id": message_id}
        except requests.HTTPError as e:
            resp = getattr(e, "response", None)
            if resp is not None and resp.status_code == 404:
                return {"status": "removed", "reaction": reaction, "message_id": message_id}
            raise
