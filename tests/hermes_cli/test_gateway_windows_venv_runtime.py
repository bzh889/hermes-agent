"""Regression tests for detached gateway interpreter selection."""

from pathlib import Path

from hermes_cli import gateway_windows


def test_resolve_gateway_python_keeps_venv_interpreter(tmp_path):
    venv = tmp_path / ".venv"
    python = venv / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    (venv / "pyvenv.cfg").write_text(
        "home = C:/Users/example/AppData/Local/Programs/Python/Python312\n",
        encoding="utf-8",
    )

    resolved, resolved_venv, extra_path = gateway_windows._resolve_gateway_python(str(python))

    assert resolved == str(python)
    assert resolved_venv == venv
    assert extra_path == []


def test_build_gateway_argv_keeps_selected_venv_python(monkeypatch, tmp_path):
    venv = tmp_path / "project" / "venv"
    python = venv / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setattr(gateway_windows, "_get_gateway_python_path", lambda: str(python))
    monkeypatch.setattr(gateway_windows, "_stable_gateway_working_dir", lambda root: str(tmp_path))
    monkeypatch.setattr(gateway_windows, "get_hermes_home", lambda: tmp_path / "home")

    argv, _cwd, env = gateway_windows._build_gateway_argv()

    assert argv[0] == str(python)
    assert env["HERMES_VENV_PYTHON"] == str(python)
    assert env["HERMES_VENV_PREFIX"] == str(venv)
