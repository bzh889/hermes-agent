"""Tests for CLI/TUI CWD resolution in load_cli_config().

Rules:
- Local backend CLI/TUI: use the launcher-captured project directory when
  available, otherwise fall back to os.getcwd().
- Non-local with placeholder: pop cwd for backend default.
- Non-local with explicit path: keep as-is.
"""

from pathlib import Path


_CWD_PLACEHOLDERS = (".", "auto", "cwd")


def _resolve_cwd(terminal_config: dict, defaults: dict, env: dict):
    """Mirror the CWD resolution logic from cli.py load_cli_config()."""
    effective_backend = terminal_config.get("env_type", "local")

    if effective_backend == "local":
        launch_cwd = env.get("HERMES_LAUNCH_CWD", "").strip()
        if launch_cwd and Path(launch_cwd).is_dir():
            terminal_cwd = str(Path(launch_cwd).resolve())
        else:
            terminal_cwd = "/fake/getcwd"
        terminal_config["cwd"] = terminal_cwd
        defaults["terminal"]["cwd"] = terminal_config["cwd"]
    elif terminal_config.get("cwd") in _CWD_PLACEHOLDERS:
        terminal_config.pop("cwd", None)

    # Bridge: TERMINAL_CWD always exported in CLI, skipped in gateway
    _is_gateway = env.get("_HERMES_GATEWAY") == "1"
    if "cwd" in terminal_config:
        if _is_gateway:
            pass  # don't touch env
        else:
            env["TERMINAL_CWD"] = str(terminal_config["cwd"])

    return env.get("TERMINAL_CWD", "")


class TestLocalBackendCli:
    """Local backend resolves the project that launched Hermes."""

    def test_launcher_cwd_wins_over_hermes_process_cwd(self, tmp_path):
        project = tmp_path / "caller-project"
        project.mkdir()
        env = {
            "HERMES_LAUNCH_CWD": str(project),
            "TERMINAL_CWD": str(tmp_path / "hermes-install"),
        }
        tc = {"cwd": str(tmp_path / "hermes-install"), "env_type": "local"}
        d = {"terminal": {"cwd": tc["cwd"]}}

        assert _resolve_cwd(tc, d, env) == str(project.resolve())

    def test_explicit_config_ignored(self):
        env = {}
        tc = {"cwd": "/explicit/path", "env_type": "local"}
        d = {"terminal": {"cwd": "/explicit/path"}}
        assert _resolve_cwd(tc, d, env) == "/fake/getcwd"

    def test_inherited_env_overwritten(self):
        env = {"TERMINAL_CWD": "/parent/hermes"}
        tc = {"cwd": "/home/user", "env_type": "local"}
        d = {"terminal": {"cwd": "/home/user"}}
        assert _resolve_cwd(tc, d, env) == "/fake/getcwd"

    def test_placeholder_resolved(self):
        env = {}
        tc = {"cwd": "."}
        d = {"terminal": {"cwd": "."}}
        assert _resolve_cwd(tc, d, env) == "/fake/getcwd"

    def test_env_and_no_config_file(self):
        env = {"TERMINAL_CWD": "/stale/value"}
        tc = {"cwd": ".", "env_type": "local"}
        d = {"terminal": {"cwd": "."}}
        assert _resolve_cwd(tc, d, env) == "/fake/getcwd"


class TestNonLocalBackends:
    """Non-local backends use config or per-backend defaults."""

    def test_placeholder_popped(self):
        env = {}
        tc = {"cwd": ".", "env_type": "docker"}
        d = {"terminal": {"cwd": "."}}
        assert _resolve_cwd(tc, d, env) == ""

    def test_explicit_path_kept(self):
        env = {}
        tc = {"cwd": "/srv/app", "env_type": "ssh"}
        d = {"terminal": {"cwd": "/srv/app"}}
        assert _resolve_cwd(tc, d, env) == "/srv/app"

    def test_auto_placeholder_popped(self):
        env = {}
        tc = {"cwd": "auto", "env_type": "modal"}
        d = {"terminal": {"cwd": "auto"}}
        assert _resolve_cwd(tc, d, env) == ""


class TestGatewayLazyImport:
    """Gateway lazy import of cli.py must not clobber TERMINAL_CWD."""

    def test_gateway_cwd_preserved(self):
        env = {"_HERMES_GATEWAY": "1", "TERMINAL_CWD": "/home/user/project"}
        tc = {"cwd": "/home/user", "env_type": "local"}
        d = {"terminal": {"cwd": "/home/user"}}
        result = _resolve_cwd(tc, d, env)
        assert result == "/home/user/project"

    def test_cli_overwrites_stale_env(self):
        env = {"TERMINAL_CWD": "/stale/from/dotenv"}
        tc = {"cwd": "/home/user", "env_type": "local"}
        d = {"terminal": {"cwd": "/home/user"}}
        result = _resolve_cwd(tc, d, env)
        assert result == "/fake/getcwd"
