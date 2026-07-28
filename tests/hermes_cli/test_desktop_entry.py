import sys

from hermes_cli.desktop_entry import restore_venv_identity


def test_restore_venv_identity(monkeypatch, tmp_path):
    venv = tmp_path / ".venv"
    python = venv / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setenv("HERMES_VENV_PYTHON", str(python))
    monkeypatch.setenv("HERMES_VENV_PREFIX", str(venv))

    restore_venv_identity()

    assert sys.executable == str(python)
    assert sys.prefix == str(venv)
    assert sys.exec_prefix == str(venv)
