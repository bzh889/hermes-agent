"""Tests for evade_path_string_filter — the CyberArk-EPM-style path filter
evasion helper in hermes_cli._subprocess_compat."""

import sys

import pytest

from hermes_cli._subprocess_compat import evade_path_string_filter


class TestEvadePathStringFilter:
    def test_noop_on_posix(self, monkeypatch):
        monkeypatch.setattr("hermes_cli._subprocess_compat.IS_WINDOWS", False)
        argv = [r"C:\Users\x\.hermes\lsp\s.py", "--stdio"]
        # On POSIX the argv is returned unchanged (as a list copy).
        assert evade_path_string_filter(argv) == argv

    def test_rewrites_absolute_windows_path(self, monkeypatch):
        monkeypatch.setattr("hermes_cli._subprocess_compat.IS_WINDOWS", True)
        out = evade_path_string_filter(
            [r"python.exe", r"C:\Users\x\.hermes\scripts\job.py"]
        )
        # The absolute path arg loses its backslashes; the ``\.hermes\``
        # substring a filter keys on is gone.
        assert out[1] == "C:/Users/x/.hermes/scripts/job.py"
        assert "\\" not in out[1]
        assert "\\.hermes\\" not in out[1]

    def test_leaves_options_and_bare_words_untouched(self, monkeypatch):
        monkeypatch.setattr("hermes_cli._subprocess_compat.IS_WINDOWS", True)
        out = evade_path_string_filter(
            [r"C:\bin\node.exe", "--stdio", "server", r"--flag=a\b"]
        )
        assert out[0] == "C:/bin/node.exe"  # absolute path rewritten
        assert out[1] == "--stdio"           # option untouched
        assert out[2] == "server"            # bare word untouched
        assert out[3] == r"--flag=a\b"       # non-path token untouched

    def test_forward_slash_path_is_idempotent(self, monkeypatch):
        monkeypatch.setattr("hermes_cli._subprocess_compat.IS_WINDOWS", True)
        argv = ["C:/already/forward/slash.py"]
        assert evade_path_string_filter(argv) == argv

    def test_relative_path_not_rewritten(self, monkeypatch):
        monkeypatch.setattr("hermes_cli._subprocess_compat.IS_WINDOWS", True)
        # No drive letter → not an absolute Windows path → left alone.
        argv = [r"sub\dir\file.py"]
        assert evade_path_string_filter(argv) == argv

    def test_returns_list_not_input_object(self, monkeypatch):
        monkeypatch.setattr("hermes_cli._subprocess_compat.IS_WINDOWS", True)
        argv = ("C:/x.py",)  # tuple input
        out = evade_path_string_filter(argv)
        assert isinstance(out, list)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only spawn")
    def test_real_spawn_bypasses_backslash_but_forward_slash_runs(self, tmp_path):
        """Sanity: the rewritten argv actually executes under CreateProcessW.

        We can't reproduce the EPM filter in CI, but we CAN prove the
        forward-slash argv the helper produces is a valid spawn on Windows.
        """
        import subprocess

        script = tmp_path / "probe.py"
        script.write_text("print('SPAWN-OK')\n")
        argv = evade_path_string_filter([sys.executable, str(script)])
        r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0
        assert "SPAWN-OK" in r.stdout
