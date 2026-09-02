"""Author table-backed Microsoft Loop (Fluid) snapshots.

The Teams/Graph APIs can transport an existing Loop URL, but table content is
stored in an ODSP Fluid snapshot.  This module performs the deterministic,
pure transformation from a table template snapshot to arbitrary rectangular
cell data.  Network and authentication orchestration live in ``_loops.py``.
"""

from __future__ import annotations

import base64
import copy
import csv
import io
import json
import struct
import uuid
from html.parser import HTMLParser
from typing import Iterable


def _validate_table(headers: Iterable[object], rows: Iterable[Iterable[object]]):
    normalized_headers = [str(value) for value in headers]
    normalized_rows = [[str(value) for value in row] for row in rows]
    if not normalized_headers:
        raise ValueError("Loop table must contain at least one column")
    width = len(normalized_headers)
    if any(len(row) != width for row in normalized_rows):
        raise ValueError("All Loop table rows must have the same number of columns")
    return normalized_headers, normalized_rows


def parse_tsv_table(value: str) -> tuple[list[str], list[list[str]]]:
    """Parse a TSV document whose first row contains column headers."""
    table = list(csv.reader(io.StringIO(str(value)), delimiter="\t"))
    while table and all(cell == "" for cell in table[-1]):
        table.pop()
    if not table:
        raise ValueError("TSV table must contain a header row")
    return _validate_table(table[0], table[1:])


class _FirstTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._table_depth = 0
        self._finished = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag == "table" and not self._finished:
            self._table_depth += 1
            return
        if self._table_depth != 1:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                self._finished = True
            return
        if self._table_depth != 1:
            return
        if tag in {"th", "td"} and self._cell is not None:
            assert self._row is not None
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str):
        if self._table_depth == 1 and self._cell is not None:
            self._cell.append(data)


def parse_html_table(value: str) -> tuple[list[str], list[list[str]]]:
    """Parse the first HTML table; the first row becomes the header row."""
    parser = _FirstTableParser()
    parser.feed(str(value))
    parser.close()
    if not parser.rows:
        raise ValueError("HTML must contain a non-empty table")
    return _validate_table(parser.rows[0], parser.rows[1:])


class _SnapshotEditor:
    def __init__(self, snapshot: dict):
        if not snapshot.get("trees") or not snapshot["trees"][0].get("entries"):
            raise ValueError("Loop template snapshot has no tree entries")
        self.snapshot = copy.deepcopy(snapshot)
        self.entries = self.snapshot["trees"][0]["entries"]
        self.blobs = self.snapshot.get("blobs", [])
        self.blob_by_id = {blob["id"]: blob for blob in self.blobs}

    def blob_json(self, entry: dict):
        blob = self.blob_by_id[entry["id"]]
        raw = base64.b64decode(blob["content"])
        return json.loads(raw)

    def add_json(self, value) -> str:
        raw = json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        blob_id = "local-" + uuid.uuid4().hex
        blob = {
            "id": blob_id,
            "content": base64.b64encode(raw).decode("ascii"),
            "encoding": "base64",
            "size": len(raw),
        }
        self.blobs.append(blob)
        self.blob_by_id[blob_id] = blob
        return blob_id

    def set_json(self, entry: dict, value) -> None:
        entry["id"] = self.add_json(value)

    def by_suffix(self, suffix: str) -> dict:
        matches = [
            entry
            for entry in self.entries
            if entry.get("type") == "blob" and entry["path"].endswith(suffix)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Loop template expected one {suffix!r} blob, found {len(matches)}"
            )
        return matches[0]


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _template_cell_ids(matrix) -> tuple[list[str], list[str]]:
    headers: list[str] = []
    bodies: list[str] = []
    for value in _walk(matrix):
        if not isinstance(value, dict):
            continue
        title = value.get("title")
        if isinstance(title, dict):
            url = (title.get("componentHandle") or {}).get("url")
            if url:
                headers.append(url.lstrip("/"))
        body = value.get("value")
        if isinstance(body, dict):
            url = (body.get("componentHandle") or {}).get("url")
            if url:
                bodies.append(url.lstrip("/"))
    return list(dict.fromkeys(headers)), list(dict.fromkeys(bodies))


def _json_utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _rich_text_blob(text: str, sequence_number: int, locale: str) -> dict:
    segments = []
    if text:
        segments.append({"text": text, "props": {"content!locale": locale}})
    segments.append(
        {
            "marker": {"refType": 1},
            "props": {"markerId": str(uuid.uuid4()), "nodeType": "Paragraph"},
        }
    )
    length = _json_utf16_length(text) + 1
    return {
        "chunkStartSegmentIndex": 0,
        "chunkSegmentCount": len(segments),
        "chunkLengthChars": length,
        "totalLengthChars": length,
        "totalSegmentCount": len(segments),
        "chunkSequenceNumber": sequence_number,
        "segmentTexts": segments,
        "headerMetadata": {
            "orderedChunkMetadata": [{"id": "header"}],
            "sequenceNumber": sequence_number,
            "totalLength": length,
            "totalSegmentCount": len(segments),
        },
    }


def _spread8(value: int) -> int:
    value = (value | (value << 4)) & 0x0F0F
    value = (value | (value << 2)) & 0x3333
    return (value | (value << 1)) & 0x5555


def _interlace16(value: int) -> int:
    return ((_spread8((value >> 8) & 255) << 16) | _spread8(value & 255)) & 0xFFFFFFFF


def _morton(row: int, column: int) -> int:
    return ((_interlace16(row) << 1) | _interlace16(column)) & 0xFFFFFFFF


def _ensure_sparse(array: list, index: int) -> list:
    if len(array) <= index:
        array.extend([None] * (index + 1 - len(array)))
    if array[index] is None:
        array[index] = [None] * 256
    return array[index]


def _sparse_set(root: list, row: int, column: int, value) -> None:
    if row < 0 or column < 0:
        raise ValueError("Sparse matrix coordinates must be non-negative")
    if row > 0xFFFFFF or column > 0xFFFFFF:
        raise ValueError(
            "Sparse matrix coordinates exceed the supported 24-bit range"
        )
    high = _morton(row >> 16, column >> 16)
    low = _morton(row & 0xFFFF, column & 0xFFFF)
    level0 = _ensure_sparse(root, high)
    level1 = _ensure_sparse(level0, (low >> 24) & 255)
    level2 = _ensure_sparse(level1, (low >> 16) & 255)
    level3 = _ensure_sparse(level2, (low >> 8) & 255)
    level3[low & 255] = value


def _direct_data_store_ids(entries: list[dict]) -> set[str]:
    result = set()
    for entry in entries:
        parts = entry["path"].split("/")
        if len(parts) >= 3 and parts[:2] == [".app", ".channels"]:
            result.add(parts[2])
    return result


def _component_store_id(editor: _SnapshotEditor, component_type: str) -> str:
    matches = []
    for entry in editor.entries:
        if entry.get("type") != "blob" or not entry["path"].endswith("/.component"):
            continue
        value = editor.blob_json(entry)
        package_chain = value.get("pkg") if isinstance(value, dict) else None
        if isinstance(package_chain, str):
            try:
                package_chain = json.loads(package_chain)
            except json.JSONDecodeError:
                package_chain = None
        if package_chain != [component_type]:
            continue
        parts = entry["path"].split("/")
        if len(parts) >= 3:
            matches.append(parts[2])
    if len(matches) != 1:
        raise ValueError(
            f"Loop template expected one {component_type!r} component, "
            f"found {len(matches)}"
        )
    return matches[0]


def build_table_snapshot(
    template_snapshot: dict,
    headers: Iterable[object],
    rows: Iterable[Iterable[object]],
    *,
    locale: str = "en-us",
) -> dict:
    """Return a table template snapshot rewritten with rectangular cell data."""
    headers, rows = _validate_table(headers, rows)
    editor = _SnapshotEditor(template_snapshot)
    matrix_entry = editor.by_suffix("/cells")
    matrix = editor.blob_json(matrix_entry)
    old_headers, old_bodies = _template_cell_ids(matrix)
    if not old_headers or not old_bodies:
        raise ValueError("Loop template does not contain header and body cells")

    header_template = old_headers[0]
    body_template = old_bodies[0]
    old_cells = set(old_headers + old_bodies)
    template_entries = copy.deepcopy(editor.entries)
    try:
        table_root_id = _component_store_id(editor, "TableroComponentType")
    except ValueError as exc:
        raise ValueError(
            "Loop template must be a Tablero table with exactly one root "
            "component; use an existing Loop table URL"
        ) from exc

    def clone_cell(template_id: str, new_id: str, text: str, preset: str):
        prefix = f".app/.channels/{template_id}"
        result = []
        for entry in template_entries:
            path = entry["path"]
            if path != prefix and not path.startswith(prefix + "/"):
                continue
            new_entry = copy.deepcopy(entry)
            new_entry["path"] = path.replace(
                prefix, f".app/.channels/{new_id}", 1
            )
            if new_entry.get("type") == "blob" and path.endswith("/root/header"):
                value = editor.blob_json(entry)
                value = json.loads(
                    json.dumps(value, ensure_ascii=False).replace(template_id, new_id)
                )
                value["content"]["storage"]["configuration"]["value"][
                    "presetName"
                ] = preset
                editor.set_json(new_entry, value)
            elif new_entry.get("type") == "blob" and path.endswith(
                "/text/content/header"
            ):
                old_value = editor.blob_json(entry)
                editor.set_json(
                    new_entry,
                    _rich_text_blob(
                        text, old_value.get("chunkSequenceNumber", 0), locale
                    ),
                )
            result.append(new_entry)
        if not result:
            raise ValueError(f"Loop template cell {template_id!r} has no snapshot subtree")
        return result

    body_prototype = next(
        copy.deepcopy(value)
        for value in _walk(matrix)
        if isinstance(value, dict)
        and isinstance(value.get("value"), dict)
        and (value["value"].get("componentHandle") or {}).get("url")
    )
    column_prototype = next(
        copy.deepcopy(value)
        for value in _walk(matrix)
        if isinstance(value, dict)
        and isinstance(value.get("title"), dict)
        and (value["title"].get("componentHandle") or {}).get("url")
    )

    editor.entries[:] = [
        entry
        for entry in editor.entries
        if not any(
            entry["path"] == f".app/.channels/{cell_id}"
            or entry["path"].startswith(f".app/.channels/{cell_id}/")
            for cell_id in old_cells
        )
    ]

    compressor_entry = next(
        entry
        for entry in editor.entries
        if entry.get("type") == "blob" and entry["path"] == ".app/.idCompressor"
    )
    compressor = bytearray(base64.b64decode(editor.blob_json(compressor_entry)))
    if len(compressor) < 16:
        raise ValueError("Loop template ID compressor state is truncated")
    compressor_limit = int(struct.unpack_from("<d", compressor, len(compressor) - 16)[0])
    allocated = int(struct.unpack_from("<d", compressor, len(compressor) - 8)[0])

    ordered_old = sorted(old_cells, key=lambda value: uuid.UUID(value).int)
    required = len(headers) + len(rows) * len(headers)
    cell_ids = ordered_old[:required]
    if len(cell_ids) < required:
        try:
            namespace_base = uuid.UUID(table_root_id).int
        except ValueError as exc:
            raise ValueError("Loop Tablero root is not a compressed UUID") from exc
        for cell_id in ordered_old:
            local_id = uuid.UUID(cell_id).int - namespace_base
            if not 0 <= local_id < allocated:
                raise ValueError(
                    f"Loop template cell {cell_id} is outside the ID compressor cluster"
                )
        new_allocated = allocated + required - len(cell_ids)
        if new_allocated > compressor_limit:
            raise ValueError(
                "Loop table exceeds the template ID compressor capacity "
                f"({new_allocated} > {compressor_limit})"
            )
        reserved = _direct_data_store_ids(template_entries)
        for local_id in range(allocated, new_allocated):
            candidate = str(uuid.UUID(int=namespace_base + local_id))
            if candidate in reserved:
                raise ValueError(f"Loop compressed ID collision: {candidate}")
            cell_ids.append(candidate)
        allocated = new_allocated
        struct.pack_into("<d", compressor, len(compressor) - 8, float(allocated))
        editor.set_json(
            compressor_entry, base64.b64encode(compressor).decode("ascii")
        )

    column_count = len(headers)
    header_ids = cell_ids[:column_count]
    flat_body_ids = cell_ids[column_count:]
    body_ids = [
        flat_body_ids[index * column_count : (index + 1) * column_count]
        for index in range(len(rows))
    ]
    for index, text in enumerate(headers):
        editor.entries.extend(
            clone_cell(header_template, header_ids[index], text, "TableHeaderCell")
        )
    for row_index, row in enumerate(rows):
        for column_index, text in enumerate(row):
            editor.entries.extend(
                clone_cell(
                    body_template,
                    body_ids[row_index][column_index],
                    text,
                    "RichTextCell",
                )
            )

    sparse_root: list = [None]
    row_ids = [f"row-{index}" for index in range(len(rows))]
    column_ids = [f"column-{index}" for index in range(column_count)]
    for row_index, row in enumerate(rows):
        _sparse_set(sparse_root, row_index + 1, 1, {"id": row_ids[row_index]})
        for column_index, text in enumerate(row):
            value = copy.deepcopy(body_prototype)
            value["value"]["componentHandle"]["url"] = (
                "/" + body_ids[row_index][column_index]
            )
            value["value"]["cellValue"] = text
            _sparse_set(sparse_root, row_index + 1, column_index + 2, value)
    for column_index, text in enumerate(headers):
        value = copy.deepcopy(column_prototype)
        value["id"] = column_ids[column_index]
        value["title"]["componentHandle"]["url"] = "/" + header_ids[column_index]
        value["title"]["cellValue"] = text
        value["titleDataTypeProps"]["initialConfig"]["initialContent"][
            "textContent"
        ] = text
        _sparse_set(sparse_root, len(rows) + 1, column_index + 2, value)
    editor.set_json(matrix_entry, [sparse_root, [None], -1])

    def set_permutation(kind: str, count: int) -> None:
        entry = editor.by_suffix(f"/{kind}/segments/header")
        value = editor.blob_json(entry)
        segments = (
            [[1, count], [count - 1, 1]]
            if kind == "rows" and count > 1
            else [[count, 1]]
        )
        value.update(
            {
                "version": "1",
                "segmentCount": len(segments),
                "length": count,
                "segments": segments,
                "startIndex": 0,
            }
        )
        value["headerMetadata"].update(
            {"totalLength": count, "totalSegmentCount": len(segments)}
        )
        editor.set_json(entry, value)
        editor.set_json(editor.by_suffix(f"/{kind}/handleTable"), [count + 1] + [0] * count)

    set_permutation("rows", len(rows) + 1)
    set_permutation("cols", column_count + 1)

    row_sequence = next(
        entry
        for entry in editor.entries
        if entry.get("type") == "blob"
        and "/rowSequence-" in entry["path"]
        and entry["path"].endswith("/header")
    )
    column_sequence = next(
        entry
        for entry in editor.entries
        if entry.get("type") == "blob"
        and "/colSequence-" in entry["path"]
        and entry["path"].endswith("/header")
    )
    editor.set_json(
        row_sequence,
        {
            "dataArray": [
                {"entryId": str(uuid.uuid4()), "value": value, "isDeleted": False}
                for value in row_ids
            ]
        },
    )
    editor.set_json(
        column_sequence,
        {
            "dataArray": [
                {"entryId": str(uuid.uuid4()), "value": value, "isDeleted": False}
                for value in column_ids
            ]
        },
    )

    view_entry = next(
        entry
        for entry in editor.entries
        if entry.get("type") == "blob"
        and "/viewDataPropertyBag-" in entry["path"]
        and entry["path"].endswith("/header")
    )
    view = editor.blob_json(view_entry)
    column_views = view["content"]["subdirectories"][
        "columnViewDataPropertyBag"
    ]["subdirectories"]
    prototype = copy.deepcopy(next(iter(column_views.values())))
    view["content"]["subdirectories"]["columnViewDataPropertyBag"][
        "subdirectories"
    ] = {column_id: copy.deepcopy(prototype) for column_id in column_ids}
    editor.set_json(view_entry, view)

    gc_entry = next(
        entry
        for entry in editor.entries
        if entry.get("type") == "blob" and entry["path"] == ".app/gc/__gc_root"
    )
    gc = editor.blob_json(gc_entry)
    nodes = gc["gcNodes"]
    for cell_id in old_cells:
        for suffix in ("", "/root", "/text"):
            nodes.pop("/" + cell_id + suffix, None)
    for cell_id in cell_ids:
        nodes["/" + cell_id] = {
            "outboundRoutes": ["/" + cell_id + "/root", "/" + cell_id + "/text"]
        }
        nodes["/" + cell_id + "/root"] = {
            "outboundRoutes": ["/" + cell_id, "/" + cell_id + "/text"]
        }
        nodes["/" + cell_id + "/text"] = {"outboundRoutes": ["/" + cell_id]}
    matrix_id = matrix_entry["path"].split("/")[-2]
    route_key = next(key for key in nodes if key.endswith("/" + matrix_id))
    base_routes = [
        route for route in nodes[route_key]["outboundRoutes"] if route.lstrip("/") not in old_cells
    ]
    nodes[route_key]["outboundRoutes"] = sorted(
        set(base_routes + ["/" + cell_id for cell_id in cell_ids])
    )
    editor.set_json(gc_entry, gc)

    editor.snapshot["ops"] = []
    return editor.snapshot


def build_create_snapshot_payload(snapshot: dict) -> dict:
    """Convert a flat ODSP snapshot readback into the nested create payload."""
    entries = snapshot["trees"][0]["entries"]
    blob_by_id = {blob["id"]: blob for blob in snapshot["blobs"]}
    root = {"children": {}}
    for entry in entries:
        node = root
        for part in entry["path"].split("/"):
            node = node["children"].setdefault(
                part, {"kind": "tree", "children": {}}
            )
        if entry["type"] == "blob":
            node.clear()
            node.update({"kind": "blob", "id": entry["id"]})

    def render(node: dict) -> list[dict]:
        result = []
        for name, child in node.get("children", {}).items():
            if child["kind"] == "blob":
                raw = base64.b64decode(blob_by_id[child["id"]]["content"])
                try:
                    content = raw.decode("utf-8")
                    encoding = "utf-8"
                except UnicodeDecodeError:
                    content = base64.b64encode(raw).decode("ascii")
                    encoding = "base64"
                result.append(
                    {
                        "path": name,
                        "type": "blob",
                        "value": {
                            "type": "blob",
                            "content": content,
                            "encoding": encoding,
                        },
                    }
                )
            else:
                result.append(
                    {
                        "path": name,
                        "type": "tree",
                        "value": {"type": "tree", "entries": render(child)},
                    }
                )
        return result

    return {
        "entries": render(root),
        "message": "app",
        "sequenceNumber": snapshot["trees"][0].get("sequenceNumber", 0),
        "type": "container",
    }


def _compact_interlaced(value: int) -> int:
    value &= 0x55555555
    value = (value | (value >> 1)) & 0x33333333
    value = (value | (value >> 2)) & 0x0F0F0F0F
    value = (value | (value >> 4)) & 0x00FF00FF
    return (value | (value >> 8)) & 0x0000FFFF


def _sparse_entries(root: list):
    for high, level0 in enumerate(root):
        if not isinstance(level0, list):
            continue
        for byte3, level1 in enumerate(level0):
            if not isinstance(level1, list):
                continue
            for byte2, level2 in enumerate(level1):
                if not isinstance(level2, list):
                    continue
                for byte1, level3 in enumerate(level2):
                    if not isinstance(level3, list):
                        continue
                    for byte0, value in enumerate(level3):
                        if value is None:
                            continue
                        low = (
                            (byte3 << 24)
                            | (byte2 << 16)
                            | (byte1 << 8)
                            | byte0
                        )
                        row = (
                            _compact_interlaced(high >> 1) << 16
                        ) | _compact_interlaced(low >> 1)
                        column = (
                            _compact_interlaced(high) << 16
                        ) | _compact_interlaced(low)
                        yield row, column, value


def read_table_snapshot(snapshot: dict) -> tuple[list[str], list[list[str]]]:
    """Decode ordered headers and rows from a table snapshot's SparseArray2D."""
    editor = _SnapshotEditor(snapshot)
    matrix = editor.blob_json(editor.by_suffix("/cells"))
    if not isinstance(matrix, list) or not matrix or not isinstance(matrix[0], list):
        raise ValueError("Loop table matrix has an invalid SparseArray2D root")
    coordinates = {(row, column): value for row, column, value in _sparse_entries(matrix[0])}
    row_positions = sorted(
        row
        for (row, column), value in coordinates.items()
        if column == 1
        and isinstance(value, dict)
        and str(value.get("id", "")).startswith("row-")
    )
    row_count = len(row_positions)
    if row_positions != list(range(1, row_count + 1)):
        raise ValueError("Loop table row identifiers are not contiguous")

    header_row = row_count + 1
    header_columns = sorted(
        column
        for (row, column), value in coordinates.items()
        if row == header_row
        and column >= 2
        and isinstance(value, dict)
        and "title" in value
    )
    if header_columns != list(range(2, 2 + len(header_columns))):
        raise ValueError("Loop table columns are not contiguous")
    headers = [
        str(coordinates[(header_row, column)]["title"]["cellValue"])
        for column in header_columns
    ]
    rows = []
    for row in row_positions:
        values = []
        for column in header_columns:
            try:
                value = coordinates[(row, column)]["value"]["cellValue"]
            except (KeyError, TypeError) as exc:
                raise ValueError(
                    f"Loop table is missing body cell ({row}, {column - 1})"
                ) from exc
            values.append(str(value))
        rows.append(values)
    return headers, rows


def inspect_table_snapshot(snapshot: dict) -> dict[str, int]:
    """Return structural table counts used to verify an ODSP readback."""
    editor = _SnapshotEditor(snapshot)
    headers, rows = read_table_snapshot(snapshot)

    rich_text_cells = 0
    for entry in editor.entries:
        if entry.get("type") != "blob" or not entry["path"].endswith("/.component"):
            continue
        blob = editor.blob_by_id[entry["id"]]
        if b"IRichTextData" in base64.b64decode(blob["content"]):
            rich_text_cells += 1
    return {
        "rows": len(rows),
        "columns": len(headers),
        "body_cells": sum(len(row) for row in rows),
        "rich_text_cells": rich_text_cells,
    }
