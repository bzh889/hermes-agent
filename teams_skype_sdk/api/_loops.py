"""Native Teams Loop component message support.

This module sends an existing Microsoft Loop component URL as the same
``FluidEmbedCard`` envelope emitted by the Teams desktop client and
orchestrates verified ODSP snapshot creation for authored table components.
"""

import base64
import binascii
import json
import time
import urllib.parse
import uuid

from ._constants import MSG_BASE
from ._loop_tables import (
    build_create_snapshot_payload,
    build_table_snapshot,
    inspect_table_snapshot,
    read_table_snapshot,
)


_FLUID_ITEMTYPE = "http://schema.skype.com/FluidEmbedCard"
_FLUID_CONTENT_TYPE = "application/vnd.microsoft.card.fluidEmbedCard"



def _validate_component_url(component_url: str) -> str:
    """Return a validated HTTPS Loop component URL."""
    value = str(component_url or "").strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("Loop component URL must be an absolute HTTPS URL")
    return value


def _loop_nav_pairs(component_url: str) -> list[tuple[str, str]]:
    """Decode the Teams Loop ``nav`` locator carried by a component URL."""
    parsed = urllib.parse.urlparse(_validate_component_url(component_url))
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    values = query.get("nav") or []
    if len(values) != 1 or not values[0]:
        raise ValueError(
            "Loop template URL must include its Teams nav parameter; "
            "copy the component link from an existing Loop table message"
        )
    encoded = values[0]
    try:
        decoded = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), validate=True
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Loop template URL has an invalid Teams nav parameter") from exc
    pairs = urllib.parse.parse_qsl(decoded, keep_blank_values=True)
    keys = {key for key, _ in pairs}
    if not {"d", "f", "fluid"}.issubset(keys):
        raise ValueError("Loop template URL has an incomplete Teams nav parameter")
    return pairs


def _retarget_loop_nav(
    template_url: str,
    component_url: str,
    *,
    drive_id: str,
    item_id: str,
) -> str:
    """Retarget a template's Fluid locator to a newly created Loop file."""
    nav_pairs = [
        (key, str(drive_id) if key == "d" else str(item_id) if key == "f" else value)
        for key, value in _loop_nav_pairs(template_url)
    ]
    nav = base64.b64encode(
        urllib.parse.urlencode(nav_pairs, doseq=True).encode("utf-8")
    ).decode("ascii")

    parsed = urllib.parse.urlparse(_validate_component_url(component_url))
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(
            parsed.query, keep_blank_values=True
        )
        if key != "nav"
    ]
    query.append(("nav", nav))
    return urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(query, doseq=True))
    )


def _validate_card_client_id(card_client_id: str | None) -> str:
    """Return the canonical UUID form emitted by the Teams desktop client."""
    value = str(card_client_id or uuid.uuid4())
    try:
        return str(uuid.UUID(value))
    except (AttributeError, ValueError) as exc:
        raise ValueError("card_client_id must be a UUID") from exc


def build_fluid_embed_payload(
    component_url: str,
    *,
    card_client_id: str | None = None,
    source_type: str = "Compose",
) -> dict:
    """Build the live Teams ``FluidEmbedCard`` MSG payload.

    ``properties.cards`` is intentionally JSON-encoded. Teams message
    properties are string-valued on POST even though the GET response may
    deserialize them for clients.
    """
    component_url = _validate_component_url(component_url)
    card_client_id = _validate_card_client_id(card_client_id)
    if not source_type or not str(source_type).strip():
        raise ValueError("source_type must not be empty")

    card = {
        "appId": "FluidEmbedCard",
        "cardClientId": card_client_id,
        "content": {
            "componentUrl": component_url,
            "sourceType": str(source_type).strip(),
        },
        "contentType": _FLUID_CONTENT_TYPE,
    }
    return {
        "amsreferences": [],
        "content": (
            '<span style="display:none"></span> \n        '
            f'<span itemtype="{_FLUID_ITEMTYPE}" '
            f'itemid="{card_client_id}"></span>'
        ),
        "messagetype": "RichText/Html",
        "contenttype": "Text",
        "properties": {
            "cards": json.dumps([card], ensure_ascii=False, separators=(",", ":")),
            "mentions": "[]",
            "links": "[]",
            "files": "[]",
            "formatVariant": "TEAMS",
            "hermes_sender": "bot",
        },
    }


def encode_share_url(component_url: str) -> str:
    """Encode a sharing URL for the Microsoft Graph ``/shares`` API."""
    component_url = _validate_component_url(component_url)
    encoded = base64.urlsafe_b64encode(component_url.encode("utf-8")).decode("ascii")
    return "u!" + encoded.rstrip("=")


def _path_id(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _item_id_from_location(location: str | None) -> str | None:
    """Extract a completed copy's item ID from a SharePoint Location URL."""
    if not location:
        return None
    parts = [urllib.parse.unquote(part) for part in urllib.parse.urlparse(location).path.split("/")]
    for index, part in enumerate(parts[:-1]):
        if part.lower() == "items" and parts[index + 1]:
            return parts[index + 1]
    return None


def clone_loop_drive_item(
    graph_api,
    drive_id: str,
    item_id: str,
    parent_id: str,
    name: str,
    *,
    scope: str = "organization",
    poll_interval: float = 1.0,
    timeout_seconds: float = 90.0,
) -> dict:
    """Copy a known Loop drive item and return an editable URL."""
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Loop clone name must not be empty")
    if "/" in clean_name or "\\" in clean_name:
        raise ValueError("Loop clone name must not contain path separators")
    if not clean_name.lower().endswith(".loop"):
        clean_name += ".loop"
    if scope not in {"organization", "users"}:
        raise ValueError("scope must be organization or users")

    if not item_id or not drive_id or not parent_id:
        raise ValueError("drive_id, item_id, and parent_id are required")

    copy_response = graph_api._request(
        "POST",
        f"/drives/{_path_id(drive_id)}/items/{_path_id(item_id)}/copy",
        json={
            "name": clean_name,
            "parentReference": {"driveId": drive_id, "id": parent_id},
        },
    )
    copy_data = copy_response.json() if copy_response.content else {}
    new_item_id = copy_data.get("id") or copy_data.get("resourceId")

    monitor_url = copy_response.headers.get("Location")
    new_item_id = new_item_id or _item_id_from_location(monitor_url)
    deadline = time.monotonic() + timeout_seconds
    while not new_item_id and monitor_url:
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for Loop component copy")
        monitor_response = graph_api._request("GET", monitor_url)
        monitor_data = monitor_response.json() if monitor_response.content else {}
        status = str(monitor_data.get("status") or "").lower()
        if status in {"failed", "deletefailed"}:
            raise RuntimeError(f"Loop component copy failed: {monitor_data}")
        new_item_id = monitor_data.get("resourceId") or monitor_data.get("id")
        if not new_item_id and poll_interval:
            time.sleep(poll_interval)

    if not new_item_id:
        raise RuntimeError("Loop component copy completed without a resource ID")

    link_data = graph_api._request(
        "POST",
        f"/drives/{_path_id(drive_id)}/items/{_path_id(new_item_id)}/createLink",
        json={"type": "edit", "scope": scope},
    ).json()
    component_url = _validate_component_url((link_data.get("link") or {}).get("webUrl"))
    return {
        "component_url": component_url,
        "drive_id": str(drive_id),
        "item_id": str(new_item_id),
        "name": clean_name,
    }


def clone_loop_component(
    graph_api,
    template_url: str,
    name: str,
    *,
    scope: str = "organization",
    poll_interval: float = 1.0,
    timeout_seconds: float = 90.0,
) -> dict:
    """Resolve a sharing URL, copy its Loop file, and return an edit URL."""
    shared = graph_api._request(
        "GET",
        f"/shares/{encode_share_url(template_url)}/driveItem",
        params={"$select": "id,name,parentReference"},
    ).json()
    item_id = shared.get("id")
    parent = shared.get("parentReference") or {}
    drive_id = parent.get("driveId")
    parent_id = parent.get("id")
    if not item_id or not drive_id or not parent_id:
        raise ValueError("Template URL did not resolve to a copyable Loop drive item")
    return clone_loop_drive_item(
        graph_api,
        drive_id,
        item_id,
        parent_id,
        name,
        scope=scope,
        poll_interval=poll_interval,
        timeout_seconds=timeout_seconds,
    )


def _clean_loop_name(name: str) -> str:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Loop component name must not be empty")
    if "/" in clean_name or "\\" in clean_name:
        raise ValueError("Loop component name must not contain path separators")
    if not clean_name.lower().endswith(".loop"):
        clean_name += ".loop"
    return clean_name


def _resolve_loop_location(graph_api, component_url: str) -> dict:
    shared = graph_api._request(
        "GET",
        f"/shares/{encode_share_url(component_url)}/driveItem",
        params={"$select": "id,name,parentReference,sharepointIds"},
    ).json()
    parent = shared.get("parentReference") or {}
    site_url = parent.get("siteUrl")
    ids = shared.get("sharepointIds") or shared.get("sharePointIds") or {}
    site_id = ids.get("siteId") or parent.get("siteId")
    drive_id = parent.get("driveId")
    if not site_url and not site_id and drive_id:
        drive = graph_api._request(
            "GET",
            f"/drives/{_path_id(drive_id)}?$select=sharePointIds",
        ).json()
        ids = drive.get("sharepointIds") or drive.get("sharePointIds") or {}
        site_id = ids.get("siteId")
    if not site_url and site_id:
        site_url = graph_api._request(
            "GET",
            f"/sites/{_path_id(site_id)}?$select=webUrl",
        ).json().get("webUrl")
    location = {
        "site_url": site_url,
        "drive_id": drive_id,
        "item_id": shared.get("id"),
        "parent_path": parent.get("path"),
    }
    missing = [key for key, value in location.items() if not value]
    if missing:
        raise ValueError(
            "Loop component URL did not resolve complete ODSP location fields: "
            + ", ".join(missing)
        )
    return location


def _site_access_token(graph_api, site_url: str) -> str:
    parsed = urllib.parse.urlsplit(site_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("Loop template siteUrl must be an absolute HTTPS URL")
    scope = f"{parsed.scheme}://{parsed.netloc}/.default offline_access"
    result = graph_api.graph_token.auth.exchange_for_scope(scope)
    token = result.get("access_token")
    if not token:
        raise RuntimeError("SharePoint token exchange returned no access_token")
    return token


def _raise_odsp_error(response, operation: str) -> None:
    try:
        response.raise_for_status()
    except Exception as exc:
        body = (getattr(response, "text", "") or "")[:500]
        status = getattr(response, "status_code", "unknown")
        raise RuntimeError(
            f"{operation} failed with HTTP {status}: {body or '(empty response)'}"
        ) from exc


def _fetch_odsp_snapshot(graph_api, location: dict, site_token: str) -> dict:
    site_url = str(location["site_url"]).rstrip("/")
    drive_id = _path_id(location["drive_id"])
    item_id = _path_id(location["item_id"])
    url = (
        f"{site_url}/_api/v2.1/drives/{drive_id}/items/{item_id}"
        "/opStream/snapshots/trees/latest?ump=1"
    )
    boundary = "HermesLoopSnapshot"
    body = "\r\n".join(
        [
            f"--{boundary}",
            f"Authorization: Bearer {site_token}",
            "X-HTTP-Method-Override: GET",
            "Prefer: manualredirect",
            "X-CLP-Compliant-App: true",
            "_post: 1",
            f"\r\n--{boundary}--",
        ]
    )
    response = graph_api._session.post(
        url,
        headers={
            "Authorization": f"Bearer {site_token}",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data;boundary={boundary}",
            "X-CLP-Compliant-App": "true",
        },
        data=body.encode("utf-8"),
        timeout=(20, 120),
        verify=graph_api.verify_ssl,
    )
    _raise_odsp_error(response, "Loop snapshot read")
    return response.json()


def _create_odsp_snapshot(
    graph_api,
    location: dict,
    site_token: str,
    name: str,
    payload: dict,
    *,
    scope: str,
) -> str:
    site_url = str(location["site_url"]).rstrip("/")
    drive_id = _path_id(location["drive_id"])
    parent = str(location["parent_path"]).split("root:", 1)[-1].strip("/")
    folder = urllib.parse.quote("/" + parent, safe="")
    encoded_name = urllib.parse.quote(name, safe="")
    encoded_scope = urllib.parse.quote(scope, safe="")
    url = (
        f"{site_url}/_api/v2.1/drives/{drive_id}/items/root:/{folder}/"
        f"{encoded_name}:/opStream/snapshots/snapshot"
        f"?createLinkScope={encoded_scope}&createLinkRole=edit"
    )
    response = graph_api._session.post(
        url,
        headers={
            "Authorization": f"Bearer {site_token}",
            "Content-Type": "application/json",
            "X-CLP-Compliant-App": "true",
        },
        json=payload,
        timeout=(20, 120),
        verify=graph_api.verify_ssl,
    )
    _raise_odsp_error(response, "Loop snapshot create")
    data = response.json()
    item_id = data.get("itemId") or data.get("id")
    if not item_id:
        raise RuntimeError("Loop snapshot create returned no item ID")
    return str(item_id)


def create_table_loop_component(
    graph_api,
    template_url: str,
    name: str,
    headers,
    rows,
    *,
    scope: str = "organization",
    locale: str = "en-us",
) -> dict:
    """Create a table Loop file and require exact ODSP content readback."""
    if scope not in {"organization", "users"}:
        raise ValueError("scope must be organization or users")
    clean_name = _clean_loop_name(name)
    _loop_nav_pairs(template_url)
    location = _resolve_loop_location(graph_api, template_url)
    site_token = _site_access_token(graph_api, location["site_url"])
    template_snapshot = _fetch_odsp_snapshot(graph_api, location, site_token)
    authored_snapshot = build_table_snapshot(
        template_snapshot, headers, rows, locale=locale
    )
    expected_headers, expected_rows = read_table_snapshot(authored_snapshot)
    payload = build_create_snapshot_payload(authored_snapshot)
    item_id = _create_odsp_snapshot(
        graph_api,
        location,
        site_token,
        clean_name,
        payload,
        scope=scope,
    )
    new_location = dict(location, item_id=item_id)
    try:
        try:
            readback = _fetch_odsp_snapshot(graph_api, new_location, site_token)
            actual_headers, actual_rows = read_table_snapshot(readback)
            verification = inspect_table_snapshot(readback)
        except Exception as exc:
            raise RuntimeError(
                f"Loop table readback verification failed: {exc}"
            ) from exc
        if (actual_headers, actual_rows) != (expected_headers, expected_rows):
            raise RuntimeError(
                "Loop table readback verification failed: ordered cell content differs"
            )
        expected_counts = {
            "rows": len(expected_rows),
            "columns": len(expected_headers),
            "body_cells": len(expected_rows) * len(expected_headers),
            "rich_text_cells": len(expected_headers)
            + len(expected_rows) * len(expected_headers),
        }
        if verification != expected_counts:
            raise RuntimeError(
                "Loop table readback verification failed: "
                f"expected {expected_counts}, got {verification}"
            )

        drive_id = str(location["drive_id"])
        link_data = graph_api._request(
            "POST",
            f"/drives/{_path_id(drive_id)}/items/{_path_id(item_id)}/createLink",
            json={"type": "edit", "scope": scope},
        ).json()
        component_url = _retarget_loop_nav(
            template_url,
            (link_data.get("link") or {}).get("webUrl"),
            drive_id=drive_id,
            item_id=item_id,
        )
        item = graph_api._request(
            "GET",
            f"/drives/{_path_id(drive_id)}/items/{_path_id(item_id)}?$select=size",
        ).json()
    except Exception:
        graph_api._request(
            "DELETE",
            f"/drives/{_path_id(location['drive_id'])}/items/{_path_id(item_id)}",
        )
        raise

    return {
        "component_url": component_url,
        "drive_id": str(location["drive_id"]),
        "item_id": item_id,
        "name": clean_name,
        "size": int(item.get("size") or 0),
        "verification": dict(verification, content_match=True),
    }


class LoopsService:
    """Send existing Loop components through the Teams MSG API."""

    def __init__(self, http):
        self._http = http

    def send_existing(
        self,
        conversation_id: str,
        component_url: str,
        *,
        card_client_id: str | None = None,
        source_type: str = "Compose",
    ) -> dict:
        """Send an existing Loop component URL to a Teams conversation."""
        if not conversation_id:
            raise ValueError("conversation_id must not be empty")

        payload = build_fluid_embed_payload(
            component_url,
            card_client_id=card_client_id,
            source_type=source_type,
        )
        card_client_id = json.loads(payload["properties"]["cards"])[0][
            "cardClientId"
        ]
        encoded = urllib.parse.quote(conversation_id, safe="")
        response = self._http._request(
            "POST",
            f"{MSG_BASE}/conversations/{encoded}/messages",
            json=payload,
        )
        data = response.json()
        message_id = (
            data.get("id")
            or data.get("OriginalArrivalTime")
            or data.get("originalArrivalTime")
            or data.get("originalarrivaltime")
            or ""
        )
        return {
            "id": str(message_id) if message_id else "",
            "status": "sent",
            "card_client_id": card_client_id,
            "component_url": _validate_component_url(component_url),
        }
