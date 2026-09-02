"""Teams API package — Composition-based architecture.

Public API:
    from src.api import TeamsClient
    from src.api._files import _extract_ams_id, _build_file_schema
    from src.api._constants import VALID_REACTIONS, REACTION_EMOJI_MAP, MAX_PAGE_SIZE, ...
"""

from ._http import HTTPLayer
from ._messages import MessagesService
from ._conversations import ConversationsService
from ._files import FilesService, _extract_ams_id, _build_file_schema
from ._search import SearchService
from ._attachments import AttachmentsService
from ._activity import ActivityService
from ._loops import LoopsService, create_table_loop_component
from ..graph import GraphToken, GraphAPI


class TeamsClient:
    """Teams API wrapper using Skype token authentication."""

    def __init__(self, auth):
        self._http = HTTPLayer(auth)
        self.messages = MessagesService(self._http)
        self.conversations = ConversationsService(self._http, self.messages)
        self.files = FilesService(self._http, self.messages)
        graph_api = GraphAPI(GraphToken(auth))
        self.search = SearchService(self.messages, self.conversations, graph_api)
        self.attachments = AttachmentsService(self._http)
        self.activity = ActivityService(self._http)
        self.loops = LoopsService(self._http)

    def __getattr__(self, name):
        old_methods = {
            "send_message": "messages.send",
            "get_messages": "messages.get",
            "edit_message": "messages.edit",
            "delete_message": "messages.delete",
            "reply_message": "messages.reply",
            "forward_message": "messages.forward",
            "list_conversations": "conversations.list",
            "get_conversation_info": "conversations.info",
            "find_conversation": "conversations.find",
            "get_messages_by_name": "conversations.get_messages_by_name",
            "upload_to_ams": "files.upload_to_ams",
            "send_image_message": "files.send_image",
            "send_file_message": "files.send_file",
            "search_messages": "search.messages",
            "get_attachment": "attachments.get",
            "list_spaces": "activity.list_spaces",
            "list_activity": "activity.list",
            "list_notes": "activity.list_notes",
            "list_call_logs": "activity.list_call_logs",
            "list_threads": "activity.list_threads",
            "list_saved": "activity.list_saved",
        }
        if name in old_methods:
            raise AttributeError(
                f"TeamsClient has no method '{name}'. "
                f"Use client.{old_methods[name]}() instead."
            )
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


__all__ = [
    "TeamsClient",
    "HTTPLayer",
    "MessagesService",
    "ConversationsService",
    "FilesService",
    "SearchService",
    "AttachmentsService",
    "ActivityService",
    "LoopsService",
    "create_table_loop_component",
    "_extract_ams_id",
    "_build_file_schema",
]
