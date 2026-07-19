"""Tests for the npm-shim-bypass helpers in _subprocess_compat that let LSP
servers spawn under a CyberArk-EPM-style substring path filter on Windows."""
import os
import sys

import pytest

from hermes_cli import _subprocess_compat as sc


IS_WIN = sys.platform == "win32"


def _write_npm_cmd_shim(path, rel_js):
    """Write a minimal npm-style .cmd shim whose line 17 invokes rel_js."""
    path.write_text(
        "@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n"
        ":start\r\nSETLOCAL\r\nCALL :find_dp0\r\n\r\n"
        'IF EXIST "%dp0%\\node.exe" ( SET "_prog=%dp0%\\node.exe" ) '
        'ELSE ( SET "_prog=node" )\r\n\r\n'
        f'endLocal & goto #_undefined_# 2>NUL || "%_prog%"  "%dp0%\\{rel_js}" %*\r\n'
    )


@pytest.mark.skipif(not IS_WIN, reason="shim bypass is Windows-only")
def test_shim_entrypoint_resolves_existing_js(tmp_path):
    binn = tmp_path / "bin"
    binn.mkdir()
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    js = pkg / "server.js"
    js.write_text("// entry\n")
    shim = binn / "foo.cmd"
    _write_npm_cmd_shim(shim, "..\\pkg\\server.js")
    got = sc._npm_shim_entrypoint(str(shim))
    assert got is not None
    assert os.path.normcase(got) == os.path.normcase(str(js))


@pytest.mark.skipif(not IS_WIN, reason="shim bypass is Windows-only")
def test_shim_entrypoint_none_when_js_missing(tmp_path):
    binn = tmp_path / "bin"
    binn.mkdir()
    shim = binn / "foo.cmd"
    _write_npm_cmd_shim(shim, "..\\pkg\\missing.js")  # target doesn't exist
    assert sc._npm_shim_entrypoint(str(shim)) is None


@pytest.mark.skipif(not IS_WIN, reason="shim bypass is Windows-only")
def test_shim_entrypoint_falls_back_to_node_modules_bin(tmp_path):
    """A stale top-level lsp/bin shim should defer to the node_modules/.bin copy."""
    lsp = tmp_path
    (lsp / "bin").mkdir()
    (lsp / "node_modules" / ".bin").mkdir(parents=True)
    pkg = lsp / "node_modules" / "pyright"
    pkg.mkdir(parents=True)
    js = pkg / "langserver.index.js"
    js.write_text("// entry\n")

    # top-level bin shim points at a NON-existent path (stale)
    stale = lsp / "bin" / "pyright-langserver.cmd"
    _write_npm_cmd_shim(stale, "..\\pyright\\langserver.index.js")  # lsp/pyright/... missing
    # node_modules/.bin shim points at the real one
    good = lsp / "node_modules" / ".bin" / "pyright-langserver.cmd"
    _write_npm_cmd_shim(good, "..\\pyright\\langserver.index.js")  # nm/pyright/... exists

    got = sc._npm_shim_entrypoint(str(stale))
    assert got is not None
    assert os.path.normcase(got) == os.path.normcase(str(js))


@pytest.mark.skipif(not IS_WIN, reason="shim bypass is Windows-only")
def test_resolve_shim_direct_node_forward_slashes(tmp_path, monkeypatch):
    binn = tmp_path / "bin"
    binn.mkdir()
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "server.js").write_text("// entry\n")
    shim = binn / "foo.cmd"
    _write_npm_cmd_shim(shim, "..\\pkg\\server.js")

    monkeypatch.setattr(sc.shutil, "which", lambda n: r"C:\node\node.exe" if n == "node" else None)
    out = sc.resolve_shim_direct_node([str(shim), "--stdio"])
    assert out is not None
    assert out[0] == "C:/node/node.exe"          # forward-slashed
    assert out[1].endswith("/pkg/server.js")      # forward-slashed .js
    assert "\\" not in out[1]                      # no backslash for EPM to match
    assert out[-1] == "--stdio"


def test_resolve_shim_direct_node_noop_off_windows_or_non_shim():
    # Non-.cmd first arg -> None (caller falls back).
    if not IS_WIN:
        assert sc.resolve_shim_direct_node(["node", "x.js"]) is None
    else:
        assert sc.resolve_shim_direct_node(["C:\\bin\\already.exe", "--stdio"]) is None
