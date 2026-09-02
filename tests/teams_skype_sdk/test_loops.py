"""Contract tests for native Teams Loop (FluidEmbedCard) messages."""

import json
from unittest.mock import MagicMock

import pytest


def _response(data, *, status_code=200, headers=None):
    response = MagicMock()
    response.json.return_value = data
    response.status_code = status_code
    response.headers = headers or {}
    response.content = b"{}" if data else b""
    return response


def test_build_fluid_embed_payload_matches_live_teams_envelope():
    from teams_skype_sdk.api._loops import build_fluid_embed_payload

    payload = build_fluid_embed_payload(
        "https://tenant.sharepoint.com/:fl:/g/example",
        card_client_id="0123456789abcdef0123456789abcdef",
    )

    assert payload["messagetype"] == "RichText/Html"
    assert payload["contenttype"] == "Text"
    assert payload["amsreferences"] == []
    assert payload["content"] == (
        '<span style="display:none"></span> \n        '
        '<span itemtype="http://schema.skype.com/FluidEmbedCard" '
        'itemid="01234567-89ab-cdef-0123-456789abcdef"></span>'
    )
    assert "s2spartnername" not in payload["properties"]
    assert payload["properties"]["hermes_sender"] == "bot"
    assert payload["properties"]["mentions"] == "[]"
    assert payload["properties"]["links"] == "[]"
    assert payload["properties"]["files"] == "[]"
    assert payload["properties"]["formatVariant"] == "TEAMS"
    assert json.loads(payload["properties"]["cards"]) == [
        {
            "appId": "FluidEmbedCard",
            "cardClientId": "01234567-89ab-cdef-0123-456789abcdef",
            "content": {
                "componentUrl": "https://tenant.sharepoint.com/:fl:/g/example",
                "sourceType": "Compose",
            },
            "contentType": "application/vnd.microsoft.card.fluidEmbedCard",
        },
    ]


def test_clone_loop_component_accepts_item_location_without_polling():
    from teams_skype_sdk.api._loops import clone_loop_drive_item

    graph = MagicMock()
    graph._request.side_effect = [
        _response(
            {},
            status_code=202,
            headers={
                "Location": (
                    "https://tenant.sharepoint.com/personal/me/_api/v2.0/"
                    "drives/drive-1/items/item-new"
                )
            },
        ),
        _response({"link": {"webUrl": "https://tenant.sharepoint.com/:fl:/g/new"}}),
    ]

    result = clone_loop_drive_item(
        graph,
        "drive-1",
        "item-old",
        "parent-1",
        "Clone.loop",
        poll_interval=0,
    )

    assert result["item_id"] == "item-new"
    assert len(graph._request.call_args_list) == 2
    assert graph._request.call_args_list[1].args == (
        "POST",
        "/drives/drive-1/items/item-new/createLink",
    )


def test_send_existing_posts_card_and_normalizes_original_arrival_time():
    from teams_skype_sdk.api._loops import LoopsService

    http = MagicMock()
    http._request.return_value = _response({"OriginalArrivalTime": 1784809672999})

    result = LoopsService(http).send_existing(
        "19:test@thread.v2",
        "https://tenant.sharepoint.com/:fl:/g/example",
        card_client_id="fedcba9876543210fedcba9876543210",
    )

    assert result == {
        "id": "1784809672999",
        "status": "sent",
        "card_client_id": "fedcba98-7654-3210-fedc-ba9876543210",
        "component_url": "https://tenant.sharepoint.com/:fl:/g/example",
    }
    method, url = http._request.call_args.args
    assert method == "POST"
    assert "19%3Atest%40thread.v2/messages" in url
    posted = http._request.call_args.kwargs["json"]
    assert json.loads(posted["properties"]["cards"])[0]["content"]["componentUrl"].endswith("/example")


def test_loop_component_url_must_be_https():
    from teams_skype_sdk.api._loops import build_fluid_embed_payload

    with pytest.raises(ValueError, match="HTTPS"):
        build_fluid_embed_payload("javascript:alert(1)")


def test_encode_share_url_uses_graph_shares_format():
    from teams_skype_sdk.api._loops import encode_share_url

    encoded = encode_share_url("https://tenant.sharepoint.com/:fl:/g/example")

    assert encoded.startswith("u!")
    assert "=" not in encoded


def test_resolve_loop_location_gets_site_url_from_sharepoint_site_id():
    from teams_skype_sdk.api._loops import _resolve_loop_location

    graph = MagicMock()
    graph._request.side_effect = [
        _response({
            "id": "template-item",
            "parentReference": {
                "driveId": "drive-1",
                "path": "/drives/drive-1/root:/Loop Files",
            },
            "sharepointIds": {"siteId": "site-1"},
        }),
        _response({"webUrl": "https://tenant.sharepoint.com/sites/loops"}),
    ]

    assert _resolve_loop_location(
        graph, "https://tenant.sharepoint.com/:fl:/g/template"
    ) == {
        "site_url": "https://tenant.sharepoint.com/sites/loops",
        "drive_id": "drive-1",
        "item_id": "template-item",
        "parent_path": "/drives/drive-1/root:/Loop Files",
    }
    assert graph._request.call_args_list[1].args == (
        "GET",
        "/sites/site-1?$select=webUrl",
    )


def test_clone_loop_component_copies_and_creates_edit_link():
    from teams_skype_sdk.api._loops import clone_loop_component

    graph = MagicMock()
    resolve = _response({
        "id": "template-item",
        "parentReference": {"driveId": "drive-1", "id": "folder-1"},
    })
    copy = _response({})
    copy.status_code = 202
    copy.headers = {"Location": "https://graph.microsoft.com/monitor/copy-1"}
    monitor = _response({"status": "completed", "resourceId": "new-item"})
    monitor.status_code = 200
    link = _response({"link": {"webUrl": "https://tenant.sharepoint.com/:fl:/g/new"}})
    graph._request.side_effect = [resolve, copy, monitor, link]

    result = clone_loop_component(
        graph,
        "https://tenant.sharepoint.com/:fl:/g/template",
        "Tracker preview.loop",
        poll_interval=0,
    )

    assert result == {
        "component_url": "https://tenant.sharepoint.com/:fl:/g/new",
        "drive_id": "drive-1",
        "item_id": "new-item",
        "name": "Tracker preview.loop",
    }
    copy_call = graph._request.call_args_list[1]
    assert copy_call.args == (
        "POST",
        "/drives/drive-1/items/template-item/copy",
    )
    assert copy_call.kwargs["json"]["parentReference"]["id"] == "folder-1"
    link_call = graph._request.call_args_list[3]
    assert link_call.kwargs["json"] == {"type": "edit", "scope": "organization"}


def test_clone_loop_drive_item_rejects_anonymous_scope_before_graph_write():
    from teams_skype_sdk.api._loops import clone_loop_drive_item

    graph = MagicMock()

    with pytest.raises(ValueError, match="organization or users"):
        clone_loop_drive_item(
            graph,
            "drive-1",
            "item-old",
            "parent-1",
            "Unsafe.loop",
            scope="anonymous",
        )

    graph._request.assert_not_called()

