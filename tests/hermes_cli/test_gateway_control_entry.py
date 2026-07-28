from hermes_cli import gateway_control_entry


def test_gateway_control_entry_dispatches_restart(monkeypatch):
    called = []
    monkeypatch.setattr(gateway_control_entry.sys, "platform", "win32")
    monkeypatch.setattr(
        "hermes_cli.gateway_windows.restart",
        lambda: called.append("restart"),
    )

    gateway_control_entry.main(["gateway", "restart"])

    assert called == ["restart"]
