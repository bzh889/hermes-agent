import argparse
import sys

from hermes_cli.desktop_entry import restore_venv_identity


def _dispatch_gateway(args) -> None:
    if sys.platform == "win32":
        from hermes_cli import gateway_windows

        command = getattr(args, "gateway_command", None)
        if command == "start":
            gateway_windows.start()
            return
        if command == "stop":
            gateway_windows.stop()
            return
        if command == "restart":
            gateway_windows.restart()
            return
        if command == "status":
            gateway_windows.status(deep=bool(getattr(args, "deep", False)))
            return

    from hermes_cli.gateway import gateway_command

    gateway_command(args)


def _parser() -> argparse.ArgumentParser:
    from hermes_cli.subcommands.gateway import build_gateway_parser

    parser = argparse.ArgumentParser(prog="hermes")
    subparsers = parser.add_subparsers(dest="command")
    build_gateway_parser(
        subparsers,
        cmd_gateway=_dispatch_gateway,
        cmd_proxy=lambda _args: None,
        cmd_gateway_enroll=lambda _args: None,
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    restore_venv_identity()

    import hermes_bootstrap

    hermes_bootstrap.harden_import_path()

    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.command != "gateway":
        raise SystemExit(2)
    _dispatch_gateway(args)


if __name__ == "__main__":
    main()
