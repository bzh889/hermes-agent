import os
import sys


def restore_venv_identity() -> None:
    venv_python = os.environ.get("HERMES_VENV_PYTHON", "").strip()
    venv_prefix = os.environ.get("HERMES_VENV_PREFIX", "").strip()
    if (
        venv_python
        and venv_prefix
        and os.path.isfile(venv_python)
        and os.path.isdir(venv_prefix)
    ):
        sys.executable = venv_python
        sys.prefix = venv_prefix
        sys.exec_prefix = venv_prefix


def main() -> None:
    restore_venv_identity()

    import hermes_bootstrap

    hermes_bootstrap.harden_import_path()

    from hermes_cli.main import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
