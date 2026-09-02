"""Tests for authoring table-backed Microsoft Loop snapshots."""

import base64
import json
import struct
import urllib.parse
import uuid
from unittest.mock import MagicMock

import pytest


_BASE = uuid.UUID("1265fa4b-745a-4c19-b9e4-fa11ee7fc830").int


def _uid(local_id: int) -> str:
    return str(uuid.UUID(int=_BASE + local_id))


def _loop_component_url(item_id: str = "template") -> str:
    nav = base64.b64encode(
        urllib.parse.urlencode(
            {
                "s": "/personal/example",
                "d": "template-drive",
                "f": item_id,
                "c": "/",
                "fluid": "1",
                "a": "Teams",
                "p": "loop-test-package",
            }
        ).encode("utf-8")
    ).decode("ascii")
    return "https://example.test/template.loop?" + urllib.parse.urlencode({"nav": nav})


def _synthetic_table_snapshot(*, compressor_limit: int = 521) -> dict:
    entries = []
    blobs = []
    next_blob = 0

    def add_raw(path: str, raw: bytes) -> None:
        nonlocal next_blob
        blob_id = f"blob-{next_blob}"
        next_blob += 1
        entries.append({"path": path, "type": "blob", "id": blob_id})
        blobs.append(
            {
                "id": blob_id,
                "content": base64.b64encode(raw).decode(),
                "encoding": "base64",
                "size": len(raw),
            }
        )

    def add_json(path: str, value) -> None:
        add_raw(path, json.dumps(value, separators=(",", ":")).encode())

    compressor = bytearray(72)
    struct.pack_into("<d", compressor, len(compressor) - 16, float(compressor_limit))
    struct.pack_into("<d", compressor, len(compressor) - 8, 9.0)
    add_json(".app/.idCompressor", base64.b64encode(compressor).decode())
    entries.append({"path": f".app/.channels/{_uid(0)}", "type": "tree"})
    add_json(
        f".app/.channels/{_uid(0)}/.component",
        {"pkg": '["TableroComponentType"]'},
    )
    entries.append({
        "path": ".app/.channels/00000000-0000-4000-8000-000000000010",
        "type": "tree",
    })

    header_ids = [_uid(index) for index in (1, 2, 3)]
    body_ids = [_uid(index) for index in (4, 5, 6)]
    for cell_id in header_ids + body_ids:
        prefix = f".app/.channels/{cell_id}"
        add_json(
            prefix + "/.component",
            {"pkg": '["TableroComponentType","IRichTextData"]'},
        )
        add_json(
            prefix + "/root/header",
            {
                "content": {
                    "storage": {
                        "configuration": {
                            "value": {
                                "presetName": "TemplateCell",
                                "dataStoreId": cell_id,
                            }
                        }
                    }
                }
            },
        )
        add_json(
            prefix + "/text/content/header",
            {
                "chunkSequenceNumber": 15,
                "segmentTexts": [{"text": "template"}],
            },
        )

    column_prototypes = [
        {
            "id": f"old-column-{index}",
            "title": {
                "componentHandle": {"url": f"/{cell_id}"},
                "cellValue": "old",
            },
            "titleDataTypeProps": {
                "initialConfig": {"initialContent": {"textContent": "old"}}
            },
        }
        for index, cell_id in enumerate(header_ids)
    ]
    body_prototypes = [
        {
            "value": {
                "componentHandle": {"url": f"/{cell_id}"},
                "cellValue": "old",
            }
        }
        for cell_id in body_ids
    ]
    add_json(
        f".app/.channels/{_uid(8)}/.channels/matrix-id/cells",
        [column_prototypes + body_prototypes, [None], -1],
    )

    segment_header = {
        "version": "1",
        "segmentCount": 1,
        "length": 2,
        "segments": [[2, 1]],
        "startIndex": 0,
        "headerMetadata": {"totalLength": 2, "totalSegmentCount": 1},
    }
    for kind in ("rows", "cols"):
        base = f".app/.channels/{_uid(8)}/.channels/{kind}"
        add_json(base + "/segments/header", segment_header)
        add_json(base + "/handleTable", [3, 0, 0])

    view_prefix = f".app/.channels/{_uid(7)}/.channels"
    add_json(view_prefix + "/rowSequence-test/header", {"dataArray": []})
    add_json(view_prefix + "/colSequence-test/header", {"dataArray": []})
    add_json(
        view_prefix + "/viewDataPropertyBag-test/header",
        {
            "content": {
                "subdirectories": {
                    "columnViewDataPropertyBag": {
                        "subdirectories": {"old-column": {"content": {}}}
                    }
                }
            }
        },
    )

    nodes = {
        f"/{cell_id}": {
            "outboundRoutes": [f"/{cell_id}/root", f"/{cell_id}/text"]
        }
        for cell_id in header_ids + body_ids
    }
    for cell_id in header_ids + body_ids:
        nodes[f"/{cell_id}/root"] = {
            "outboundRoutes": [f"/{cell_id}", f"/{cell_id}/text"]
        }
        nodes[f"/{cell_id}/text"] = {"outboundRoutes": [f"/{cell_id}"]}
    nodes[f"/{_uid(8)}/matrix-id"] = {
        "outboundRoutes": [f"/{cell_id}" for cell_id in header_ids + body_ids]
    }
    add_json(".app/gc/__gc_root", {"gcNodes": nodes})

    return {
        "trees": [{"id": "tree", "sequenceNumber": 15, "entries": entries}],
        "blobs": blobs,
        "ops": [],
        "latestSequenceNumber": 15,
    }


def _blob_json(snapshot: dict, path: str):
    entry = next(item for item in snapshot["trees"][0]["entries"] if item["path"] == path)
    blob = next(item for item in snapshot["blobs"] if item["id"] == entry["id"])
    return json.loads(base64.b64decode(blob["content"]))


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_build_table_snapshot_updates_matrix_gc_and_id_compressor():
    from teams_skype_sdk.api._loop_tables import build_table_snapshot

    result = build_table_snapshot(
        _synthetic_table_snapshot(),
        ["A", "B", "C"],
        [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]],
    )

    compressor_encoded = _blob_json(result, ".app/.idCompressor")
    compressor = base64.b64decode(compressor_encoded)
    assert struct.unpack_from("<d", compressor, len(compressor) - 8)[0] == 15.0

    expected_cell_ids = {_uid(index) for index in range(1, 7)} | {
        _uid(index) for index in range(9, 15)
    }
    component_paths = {
        entry["path"]
        for entry in result["trees"][0]["entries"]
        if entry["path"].endswith("/.component")
    }
    assert any(
        entry["path"] == ".app/.channels/00000000-0000-4000-8000-000000000010"
        for entry in result["trees"][0]["entries"]
    )
    assert component_paths == {
        f".app/.channels/{_uid(0)}/.component",
        *(
            f".app/.channels/{cell_id}/.component"
            for cell_id in expected_cell_ids
        ),
    }

    matrix = _blob_json(result, f".app/.channels/{_uid(8)}/.channels/matrix-id/cells")
    assert sum(
        1
        for item in _walk(matrix)
        if isinstance(item, dict)
        and isinstance(item.get("value"), dict)
        and "cellValue" in item["value"]
    ) == 9
    assert sum(
        1
        for item in _walk(matrix)
        if isinstance(item, dict) and "title" in item
    ) == 3
    assert sum(
        1
        for item in _walk(matrix)
        if isinstance(item, dict)
        and set(item) == {"id"}
        and str(item["id"]).startswith("row-")
    ) == 3

    row_segments = _blob_json(
        result, f".app/.channels/{_uid(8)}/.channels/rows/segments/header"
    )
    assert row_segments["segments"] == [[1, 4], [3, 1]]
    assert row_segments["segmentCount"] == 2
    assert row_segments["headerMetadata"]["totalSegmentCount"] == 2

    column_segments = _blob_json(
        result, f".app/.channels/{_uid(8)}/.channels/cols/segments/header"
    )
    assert column_segments["segments"] == [[4, 1]]

    gc = _blob_json(result, ".app/gc/__gc_root")["gcNodes"]
    routes = gc[f"/{_uid(8)}/matrix-id"]["outboundRoutes"]
    assert set(routes) == {f"/{cell_id}" for cell_id in expected_cell_ids}


def test_build_create_snapshot_payload_nests_flat_paths():
    from teams_skype_sdk.api._loop_tables import (
        build_create_snapshot_payload,
        build_table_snapshot,
        inspect_table_snapshot,
        read_table_snapshot,
    )

    snapshot = build_table_snapshot(
        _synthetic_table_snapshot(), ["A"], [["1"]]
    )
    payload = build_create_snapshot_payload(snapshot)

    assert payload["type"] == "container"
    assert payload["sequenceNumber"] == 15
    assert payload["entries"]
    assert payload["entries"][0]["type"] in {"tree", "blob"}
    assert inspect_table_snapshot(snapshot) == {
        "rows": 1,
        "columns": 1,
        "body_cells": 1,
        "rich_text_cells": 2,
    }
    assert read_table_snapshot(snapshot) == (["A"], [["1"]])


def test_parse_tsv_and_html_tables():
    from teams_skype_sdk.api._loop_tables import parse_html_table, parse_tsv_table

    assert parse_tsv_table("A\tB\n1\t2\n3\t4\n") == (
        ["A", "B"],
        [["1", "2"], ["3", "4"]],
    )
    assert parse_html_table(
        "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td><b>2</b></td></tr></tbody></table>"
    ) == (["A", "B"], [["1", "2"]])


def test_create_table_authoring_is_public_api():
    from teams_skype_sdk.api import create_table_loop_component

    assert callable(create_table_loop_component)


def test_sparse_matrix_round_trips_large_indices_and_rejects_invalid_ones():
    from teams_skype_sdk.api._loop_tables import _sparse_entries, _sparse_set

    root = [None]
    marker = {"value": "large"}
    _sparse_set(root, 100_000, 50_000, marker)
    assert list(_sparse_entries(root)) == [(100_000, 50_000, marker)]

    with pytest.raises(ValueError, match="non-negative"):
        _sparse_set([None], -1, 0, marker)
    with pytest.raises(ValueError, match="supported 24-bit"):
        _sparse_set([None], 1 << 32, 0, marker)


def test_non_tablero_template_has_actionable_error():
    from teams_skype_sdk.api._loop_tables import build_table_snapshot

    snapshot = _synthetic_table_snapshot()
    root_component = f".app/.channels/{_uid(0)}/.component"
    snapshot["trees"][0]["entries"] = [
        entry
        for entry in snapshot["trees"][0]["entries"]
        if entry["path"] != root_component
    ]
    with pytest.raises(ValueError, match="must be a Tablero table"):
        build_table_snapshot(snapshot, ["A"], [["1"]])


def test_table_input_must_be_rectangular():
    from teams_skype_sdk.api._loop_tables import build_table_snapshot, parse_tsv_table

    with pytest.raises(ValueError, match="same number of columns"):
        parse_tsv_table("A\tB\n1\n")
    with pytest.raises(ValueError, match="same number of columns"):
        build_table_snapshot(_synthetic_table_snapshot(), ["A", "B"], [["1"]])


def test_table_snapshot_rejects_id_compressor_capacity_overflow():
    from teams_skype_sdk.api._loop_tables import build_table_snapshot

    with pytest.raises(ValueError, match="ID compressor capacity"):
        build_table_snapshot(
            _synthetic_table_snapshot(compressor_limit=10),
            ["A", "B", "C"],
            [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]],
        )


class _JsonResponse:
    def __init__(self, value):
        self._value = value
        self.content = b"{}"

    def json(self):
        return self._value


class _AuthoringGraph:
    def __init__(self):
        self.calls = []

    def _request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "POST" and url.endswith("/createLink"):
            return _JsonResponse(
                {"link": {"webUrl": "https://example.test/new.loop?e=share-token"}}
            )
        if method == "GET" and "?$select=size" in url:
            return _JsonResponse({"size": 42496})
        if method == "DELETE":
            return _JsonResponse({})
        raise AssertionError((method, url, kwargs))


def test_create_table_loop_component_requires_exact_live_readback(monkeypatch):
    from teams_skype_sdk.api import _loops
    from teams_skype_sdk.api._loop_tables import build_table_snapshot

    template = _synthetic_table_snapshot()
    expected = build_table_snapshot(template, ["A", "B"], [["1", "2"]])
    fetches = iter([template, expected])
    graph = _AuthoringGraph()
    location = {
        "site_url": "https://example.test/sites/loops",
        "drive_id": "drive",
        "item_id": "template",
        "parent_path": "/drive/root:/Loop Files",
    }
    monkeypatch.setattr(_loops, "_resolve_loop_location", lambda *_: location)
    monkeypatch.setattr(_loops, "_site_access_token", lambda *_: "site-token")
    monkeypatch.setattr(_loops, "_fetch_odsp_snapshot", lambda *_: next(fetches))
    monkeypatch.setattr(_loops, "_create_odsp_snapshot", lambda *args, **kwargs: "new-item")

    result = _loops.create_table_loop_component(
        graph,
        _loop_component_url(),
        "Authored table",
        ["A", "B"],
        [["1", "2"]],
    )

    assert result["item_id"] == "new-item"
    assert result["size"] == 42496
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(result["component_url"]).query
    )
    assert query["e"] == ["share-token"]
    nav = urllib.parse.parse_qs(
        base64.b64decode(query["nav"][0]).decode("utf-8")
    )
    assert nav["d"] == ["drive"]
    assert nav["f"] == ["new-item"]
    assert nav["p"] == ["loop-test-package"]
    assert result["verification"] == {
        "rows": 1,
        "columns": 2,
        "body_cells": 2,
        "rich_text_cells": 4,
        "content_match": True,
    }
    assert not any(method == "DELETE" for method, _, _ in graph.calls)


def test_create_table_loop_component_deletes_failed_readback(monkeypatch):
    from teams_skype_sdk.api import _loops

    template = _synthetic_table_snapshot()
    fetches = iter([template, template])
    graph = _AuthoringGraph()
    location = {
        "site_url": "https://example.test/sites/loops",
        "drive_id": "drive",
        "item_id": "template",
        "parent_path": "/drive/root:/Loop Files",
    }
    monkeypatch.setattr(_loops, "_resolve_loop_location", lambda *_: location)
    monkeypatch.setattr(_loops, "_site_access_token", lambda *_: "site-token")
    monkeypatch.setattr(_loops, "_fetch_odsp_snapshot", lambda *_: next(fetches))
    monkeypatch.setattr(_loops, "_create_odsp_snapshot", lambda *args, **kwargs: "new-item")

    with pytest.raises(RuntimeError, match="readback verification failed"):
        _loops.create_table_loop_component(
            graph,
            _loop_component_url(),
            "Authored table",
            ["A", "B"],
            [["1", "2"]],
        )

    assert any(
        method == "DELETE" and "/items/new-item" in url
        for method, url, _ in graph.calls
    )
    assert not any(url.endswith("/createLink") for _, url, _ in graph.calls)


def test_create_odsp_snapshot_uses_requested_link_scope():
    from teams_skype_sdk.api._loops import _create_odsp_snapshot

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"itemId": "new-item"}

    class Session:
        url = None

        def post(self, url, **kwargs):
            self.url = url
            return Response()

    class Graph:
        _session = Session()
        verify_ssl = True

    graph = Graph()
    location = {
        "site_url": "https://example.test/sites/loops",
        "drive_id": "drive",
        "parent_path": "/drive/root:/Loop Files",
    }

    item_id = _create_odsp_snapshot(
        graph,
        location,
        "site-token",
        "Restricted.loop",
        {"snapshot": {}},
        scope="users",
    )

    assert item_id == "new-item"
    assert "createLinkScope=users" in graph._session.url
    assert "createLinkScope=organization" not in graph._session.url


def test_create_table_loop_component_rejects_anonymous_scope_before_graph_write():
    from teams_skype_sdk.api._loops import create_table_loop_component

    graph = MagicMock()

    with pytest.raises(ValueError, match="organization or users"):
        create_table_loop_component(
            graph,
            "https://tenant.sharepoint.com/:fl:/g/template",
            "Unsafe.loop",
            ["A"],
            [["1"]],
            scope="anonymous",
        )

    graph._request.assert_not_called()
