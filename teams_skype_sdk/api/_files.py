"""[API Service] File and image upload operations.

Contains AMS image upload, OneDrive file upload, and the SharePoint
file schema builder used for native Teams file cards.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from teams_skype_sdk.config import DEFAULT_TIMEOUT

from ._constants import AMS_BASE_URL, AMS_USER_AGENT
from ._http import HTTPLayer

if TYPE_CHECKING:
    from ._messages import MessagesService


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_ams_id(url: str) -> str | None:
    """Extract AMS object ID from a URL.

    Supports URLs like:
    - https://api.asm.skype.com/v1/objects/{ams_id}/views/...
    - https://.../objects/{ams_id}/...

    Args:
        url: Attachment URL

    Returns:
        AMS ID string, or None if not found
    """
    match = re.search(r"/objects/([^/]+)/", url)
    return match.group(1) if match else None


def _build_file_schema(
    od_meta: dict, sp_ids: dict, original_filename: str,
    share_url: str = "",
) -> dict:
    """Build SharePoint-native file schema for Teams file card.

    Replicates the exact schema structure used by the Teams client.
    Verified via FlipBot's ablation testing — minimal schema is unreliable,
    so this uses the full ~25-field schema.

    Args:
        od_meta: OneDrive upload result (id, fileName, webUrl, size).
        sp_ids: SharePoint IDs (listItemUniqueId, siteId, siteUrl).
        original_filename: Display filename for the user.
        share_url: Organization sharing link (best-effort, may be empty).

    Returns:
        Schema dict for the ``properties.files`` JSON array.
    """
    list_item_uid = sp_ids.get("listItemUniqueId", "")
    site_id = sp_ids.get("siteId", "")
    site_url = sp_ids.get("siteUrl", "")
    file_url = od_meta.get("webUrl", "")
    file_ext = os.path.splitext(original_filename)[1].lstrip(".")
    if not file_ext:
        file_ext = "file"

    return {
        "itemid": list_item_uid,
        "fileName": original_filename,
        "fileType": file_ext,
        "fileInfo": {
            "itemId": None,
            "fileUrl": file_url,
            "siteUrl": site_url + "/",
            "serverRelativeUrl": "",
            "shareUrl": share_url or None,
            "shareId": None,
        },
        "fileChicletState": {
            "serviceName": "p2p",
            "state": "active",
        },
        "@type": "http://schema.skype.com/File",
        "version": 2,
        "id": list_item_uid,
        "baseUrl": site_url + "/",
        "objectUrl": file_url,
        "type": file_ext,
        "title": original_filename,
        "state": "active",
        "chicletBreadcrumbs": None,
        "providerData": "",
        "botFileProperties": {},
        "isUploadError": None,
        "progressComplete": None,
        "permissionScope": "users",
        "filePreview": {
            "previewUrl": "",
            "previewHeight": 0,
            "previewWidth": 0,
        },
        "sharepointIds": {
            "listId": None,
            "listItemUniqueId": list_item_uid,
            "siteId": site_id,
            "siteUrl": None,
            "webId": None,
        },
        "publication": None,
        "site": None,
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class FilesService:
    """AMS image upload, OneDrive file upload, and file card sending."""

    def __init__(self, http: HTTPLayer, messages: "MessagesService"):
        self._http = http
        self._messages = messages

    def upload_to_ams(
        self, conversation_id: str,
        image_data: bytes, content_type: str = "image/png",
    ) -> str:
        """Upload an image to AMS and return its object ID.

        Two-step reverse-engineered AMS protocol:
        1. POST /v1/objects -> create AMS object with read permission
        2. PUT /v1/objects/{id}/content/imgpsh -> upload binary image data

        Note: Uses raw session calls (not self._http._request()) because AMS
        requires a different auth header format (skype_token {token}).
        """
        skype_token = self._http.auth.get_skype_token()
        ams_headers = {
            "Authorization": f"skype_token {skype_token}",
            "User-Agent": AMS_USER_AGENT,
        }

        # Step 1: Create AMS object
        create_resp = self._http._session.post(
            AMS_BASE_URL,
            headers={**ams_headers, "Content-Type": "application/json"},
            json={
                "type": "pish/image",
                "permissions": {conversation_id: ["read"]},
            },
            verify=self._http.verify_ssl,
            timeout=DEFAULT_TIMEOUT,
        )
        create_resp.raise_for_status()
        ams_id = create_resp.json()["id"]

        # Step 2: Upload image binary
        upload_resp = self._http._session.put(
            f"{AMS_BASE_URL}/{ams_id}/content/imgpsh",
            headers={**ams_headers, "Content-Type": content_type},
            data=image_data,
            verify=self._http.verify_ssl,
            timeout=(10, 120),
        )
        upload_resp.raise_for_status()

        return ams_id

    def send_image(
        self, conversation_id: str, image_data: bytes,
        content_type: str = "image/png", caption: str = "",
    ) -> dict:
        """Upload image to AMS and send inline in Teams message."""
        ams_id = self.upload_to_ams(conversation_id, image_data, content_type)

        img_url = f"{AMS_BASE_URL}/{ams_id}/views/imgo"
        img_html = (
            f'<div itemscope itemtype="http://schema.skype.com/AMSImage">'
            f'<img src="{img_url}" itemid="{ams_id}" '
            f'itemtype="http://schema.skype.com/AMSImage">'
            f'</div>'
        )
        content = f"{caption}<br>{img_html}" if caption else img_html

        result = self._messages.send(conversation_id, content, ams_refs=[ams_id], is_html=True)
        result["ams_id"] = ams_id
        return result

    def send_file(
        self, conversation_id: str, file_bytes: bytes,
        original_filename: str, graph_api, caption: str = "",
    ) -> dict:
        """Upload file to OneDrive and send as Teams file card.

        5-step flow: upload -> sharing link -> SP IDs -> schema -> send.
        """
        od_item_id = None
        try:
            od_meta = graph_api.upload_to_onedrive(file_bytes, original_filename)
            od_item_id = od_meta["id"]

            share_url = ""
            try:
                share_url = graph_api.create_sharing_link(od_item_id)
            except Exception:
                pass

            sp_ids = graph_api.get_sharepoint_ids(od_item_id)
            schema = _build_file_schema(od_meta, sp_ids, original_filename, share_url)

            content = caption if caption else ""
            result = self._messages.send(
                conversation_id, content, file_schemas=[schema],
            )
            result["file_name"] = original_filename
            result["file_size"] = od_meta.get("size", 0)
            result["file_url"] = od_meta.get("webUrl", "")
            return result
        except Exception:
            if od_item_id:
                try:
                    graph_api.delete_onedrive_item(od_item_id)
                except Exception:
                    pass
            raise
