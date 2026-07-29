from hermes_cli.desktop_entry import restore_venv_identity


def _inject_system_trust_store() -> None:
    """Install OS certificate trust before gateway HTTP clients are imported."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        # Optional hardening: environments without truststore retain the
        # existing CA-bundle/default SSL behavior.
        pass


def main() -> None:
    """Run the detached Gateway without constructing the general CLI."""
    restore_venv_identity()

    import hermes_bootstrap

    hermes_bootstrap.harden_import_path()
    _inject_system_trust_store()

    from gateway.run import main as gateway_main

    gateway_main()


if __name__ == "__main__":
    main()
