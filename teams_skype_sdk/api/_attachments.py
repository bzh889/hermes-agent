"""[API Service] Attachment download operations."""

import urllib.parse

from teams_skype_sdk.config import DEFAULT_TIMEOUT
from ._http import HTTPLayer


class AttachmentsService:
    """Download attachments and images from Teams messages."""

    def __init__(self, http: HTTPLayer):
        self._http = http

    def get(self, attachment_url: str) -> bytes:
        """Download an attachment or image.

        Delegates to HTTPLayer.download_with_auth for correct auth header
        selection based on the URL domain.

        Args:
            attachment_url: URL of the attachment to download

        Returns:
            Bytes content of the attachment
        """
        return self._http.download_with_auth(attachment_url)
