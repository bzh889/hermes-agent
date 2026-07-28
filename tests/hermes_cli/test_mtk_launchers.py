from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mtk_launchers_prefer_dot_venv_with_venv_fallback():
    for name in ("hermes.sh", "hermes.bat", "hermes-web.bat", "hermes-desktop.bat"):
        text = (ROOT / name).read_text(encoding="utf-8")
        dot_venv = (
            "./.venv/Scripts/python.exe"
            if name.endswith(".sh")
            else r"%~dp0.venv\Scripts\python.exe"
        )
        fallback = (
            "./venv/Scripts/python.exe"
            if name.endswith(".sh")
            else r"%~dp0venv\Scripts\python.exe"
        )

        assert dot_venv in text, f"{name} does not probe .venv"
        assert fallback in text, f"{name} lost the venv fallback"
        assert text.index(dot_venv) < text.index(fallback)


def test_mtk_launchers_use_real_git_bash_for_terminal_tools():
    bash_text = (ROOT / "hermes.sh").read_text(encoding="utf-8")
    batch_text = (ROOT / "hermes.bat").read_text(encoding="utf-8")

    assert (
        'export HERMES_GIT_BASH_PATH="${PROGRAMFILES:-C:\\Program Files}'
        '\\Git\\usr\\bin\\bash.exe"'
    ) in bash_text
    assert (
        'set "HERMES_GIT_BASH_PATH=%ProgramFiles%\\Git\\usr\\bin\\bash.exe"'
    ) in batch_text


def test_bash_gateway_management_uses_light_entry():
    text = (ROOT / "hermes.sh").read_text(encoding="utf-8")

    assert '"${1:-}" = "gateway"' in text
    assert 'exec "$BASE_HOME/python.exe" -m hermes_cli.gateway_control_entry "$@"' in text
    assert 'exec "$PYEXE" -m hermes_cli.gateway_control_entry "$@"' in text
    assert "sed " not in text
    assert "cygpath" not in text
    assert "dirname " not in text
    assert "${USERPROFILE:-$HOME}" in text


def test_bash_exact_tui_launch_bypasses_full_cli_parser():
    text = (ROOT / "hermes.sh").read_text(encoding="utf-8")

    fast_path = 'if [ "$#" -eq 1 ] && [ "$1" = "--tui" ]; then'
    node_launch = 'exec "$NODE_BIN" --expose-gc "$TUI_ENTRY"'

    assert fast_path in text
    assert '${USERPROFILE:-$HOME}/.cchelper/nodejs/node.exe' in text
    assert 'export HERMES_TUI_GATEWAY_PYTHON="$PYEXE"' in text
    assert node_launch in text
    tui_block = text[text.index(fast_path) : text.index(node_launch)]
    assert "$(command -v node" not in tui_block
    assert "$(pwd -W)" not in tui_block
    assert text.index(fast_path) < text.index(
        'exec "$PYEXE" -m hermes_cli.main "$@"'
    )


def test_windows_exact_tui_launch_bypasses_full_cli_parser():
    text = (ROOT / "hermes.bat").read_text(encoding="utf-8")

    assert 'if /I "%~1"=="--tui" if "%~2"=="" goto :tui' in text
    assert r"%USERPROFILE%\.cchelper\nodejs\node.exe" in text
    assert r"ui-tui\dist\entry.js" in text
    assert '"%NODE_BIN%" --expose-gc "%TUI_ENTRY%"' in text
    assert text.index('goto :tui') < text.index(
        '"%PYEXE%" -m hermes_cli.main %*'
    )


def test_desktop_launcher_accepts_local_or_hoisted_electron():
    text = (ROOT / "hermes-desktop.bat").read_text(encoding="utf-8")

    assert r"apps\desktop\node_modules\electron\dist\electron.exe" in text
    assert r"node_modules\electron\dist\electron.exe" in text
    assert "ELECTRON_OVERRIDE_DIST_PATH" in text


def test_desktop_launcher_prefers_packaged_app_when_present():
    text = (ROOT / "hermes-desktop.bat").read_text(encoding="utf-8")
    packaged = r"apps\desktop\release\win-unpacked\Hermes.exe"

    assert packaged in text
    assert text.index(packaged) < text.index("ELECTRON_LOCAL")


def test_desktop_launcher_points_packaged_app_at_this_checkout():
    text = (ROOT / "hermes-desktop.bat").read_text(encoding="utf-8")
    packaged_launch = text.index('start "" "%HERMES_PACKAGED%"')

    assert 'set "HERMES_HOME=%USERPROFILE%\\.hermes"' in text[:packaged_launch]
    assert 'set "HERMES_DESKTOP_HERMES_ROOT=%~dp0"' in text[:packaged_launch]
