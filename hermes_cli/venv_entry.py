from hermes_cli.desktop_entry import restore_venv_identity


def main() -> None:
    restore_venv_identity()

    import hermes_bootstrap

    hermes_bootstrap.harden_import_path()

    from hermes_cli.main import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
