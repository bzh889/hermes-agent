from hermes_cli.desktop_entry import restore_venv_identity


def main() -> None:
    """Run the detached Gateway without constructing the general CLI."""
    restore_venv_identity()

    import hermes_bootstrap

    hermes_bootstrap.harden_import_path()

    from gateway.run import main as gateway_main

    gateway_main()


if __name__ == "__main__":
    main()
