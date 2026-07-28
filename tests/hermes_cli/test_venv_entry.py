from hermes_cli import venv_entry


def test_venv_entry_restores_identity_before_cli_main(monkeypatch):
    events = []
    monkeypatch.setattr(
        venv_entry,
        "restore_venv_identity",
        lambda: events.append("restore"),
    )
    monkeypatch.setattr(
        "hermes_cli.main.main",
        lambda: events.append("main"),
    )

    venv_entry.main()

    assert events == ["restore", "main"]
