"""Behavior tests for per-turn Execution Authority at the skill write seam."""

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from gateway.session_context import clear_session_vars, set_session_vars
from tools.skill_manager_tool import skill_manage


VALID_SKILL = """---
name: authority-skill
description: Tests owner-authorized skill maintenance.
---

# Authority Skill

OLD_MARKER
"""


def _config() -> dict:
    return {
        "gateway": {
            "teams_mtk": {
                "control_conversations": {
                    "control-chat": {"owner_user_ids": ["owner-oid"]},
                },
                # These legacy routing/access settings are deliberately not
                # execution-authority grants.
                "home_channel": {
                    "chat_id": "home-chat",
                    "user_id": "owner-oid",
                },
                "groups": {
                    "group-chat": {"allowed_user_ids": ["owner-oid"]},
                },
            }
        }
    }


@pytest.fixture
def skill_root(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    skill_dir = root / "authority-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(VALID_SKILL, encoding="utf-8")

    from hermes_cli import config as config_module

    monkeypatch.setattr(config_module, "load_config_readonly", _config)
    with patch("tools.skill_manager_tool.SKILLS_DIR", root), patch(
        "agent.skill_utils.get_all_skills_dirs", return_value=[root]
    ):
        yield root


def _bind(*, platform="", source="", chat_id="", user_id=""):
    return set_session_vars(
        platform=platform,
        source=source,
        chat_id=chat_id,
        user_id=user_id,
        session_key=f"{platform or source}:{chat_id}:{user_id}",
    )


def _patch(name="authority-skill", old="OLD_MARKER", new="NEW_MARKER"):
    return json.loads(
        skill_manage(
            action="patch",
            name=name,
            old_string=old,
            new_string=new,
        )
    )


@pytest.mark.parametrize(
    ("action", "name", "kwargs"),
    [
        (
            "create",
            "created-skill",
            {"content": VALID_SKILL.replace("authority-skill", "created-skill")},
        ),
        ("edit", "authority-skill", {"content": VALID_SKILL.replace("OLD_MARKER", "EDITED_MARKER")}),
        ("patch", "authority-skill", {"old_string": "OLD_MARKER", "new_string": "NEW_MARKER"}),
        (
            "write_file",
            "authority-skill",
            {"file_path": "references/note.md", "file_content": "note"},
        ),
        ("remove_file", "authority-skill", {"file_path": "references/note.md"}),
    ],
)
def test_tui_owner_can_perform_nondestructive_skill_maintenance(
    skill_root, action, name, kwargs
):
    support = skill_root / "authority-skill" / "references" / "note.md"
    if action == "remove_file":
        support.parent.mkdir()
        support.write_text("note", encoding="utf-8")

    tokens = _bind(source="tui")
    try:
        result = json.loads(skill_manage(action=action, name=name, **kwargs))
    finally:
        clear_session_vars(tokens)

    assert result["success"] is True, result
    if action == "create":
        assert (skill_root / "created-skill" / "SKILL.md").exists()
    elif action == "edit":
        assert "EDITED_MARKER" in (skill_root / name / "SKILL.md").read_text(encoding="utf-8")
    elif action == "patch":
        assert "NEW_MARKER" in (skill_root / name / "SKILL.md").read_text(encoding="utf-8")
    elif action == "write_file":
        assert support.read_text(encoding="utf-8") == "note"
    else:
        assert not support.exists()


def test_exact_teams_control_owner_can_patch_user_owned_skill(skill_root):
    from gateway.run import GatewayRunner
    from gateway.session import Platform, SessionContext, SessionSource

    runner = GatewayRunner.__new__(GatewayRunner)
    runner.adapters = {}
    context = SessionContext(
        source=SessionSource(
            platform=Platform.TEAMS_MTK,
            chat_id="control-chat",
            user_id="owner-oid",
        ),
        connected_platforms=[Platform.TEAMS_MTK],
        home_channels={},
        session_key="teams_mtk:control-chat",
    )
    tokens = runner._set_session_env(context)
    try:
        result = _patch()
    finally:
        runner._clear_session_env(tokens)

    assert result["success"] is True, result


@pytest.mark.parametrize(
    ("platform", "source", "chat_id", "user_id"),
    [
        ("teams_mtk", "", "other-chat", "owner-oid"),
        ("teams_mtk", "", "control-chat", "other-oid"),
        ("teams_mtk", "", "home-chat", "owner-oid"),
        ("teams_mtk", "", "group-chat", "owner-oid"),
        ("telegram", "", "control-chat", "owner-oid"),
        ("", "desktop", "", ""),
    ],
)
def test_non_control_turns_cannot_patch_skills(
    skill_root, platform, source, chat_id, user_id
):
    tokens = _bind(
        platform=platform,
        source=source,
        chat_id=chat_id,
        user_id=user_id,
    )
    try:
        result = _patch()
    finally:
        clear_session_vars(tokens)

    assert result["success"] is False, result
    assert "execution authority" in result["error"].lower()
    assert "OLD_MARKER" in (skill_root / "authority-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_model_arguments_cannot_claim_execution_authority():
    from tools.skill_manager_tool import SKILL_MANAGE_SCHEMA

    params = SKILL_MANAGE_SCHEMA["parameters"]["properties"]
    assert not ({"authority", "platform", "chat_id", "user_id"} & set(params))


def test_owner_authority_can_modify_a_directory_symlink_target(
    skill_root, tmp_path
):
    target = tmp_path / "shared" / "linked-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        VALID_SKILL.replace("authority-skill", "linked-skill"), encoding="utf-8"
    )
    link = skill_root / "linked-skill"
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
    else:
        link.symlink_to(target, target_is_directory=True)

    tokens = _bind(source="tui")
    try:
        result = _patch(name="linked-skill")
    finally:
        clear_session_vars(tokens)

    assert result["success"] is True, result
    assert "NEW_MARKER" in (target / "SKILL.md").read_text(encoding="utf-8")


def test_concurrent_turns_do_not_share_owner_authority(skill_root):
    for name in ("owner-skill", "other-skill"):
        path = skill_root / name
        path.mkdir()
        (path / "SKILL.md").write_text(
            VALID_SKILL.replace("authority-skill", name), encoding="utf-8"
        )

    def make_context(chat_id, user_id):
        ctx = copy_context()
        ctx.run(
            _bind,
            platform="teams_mtk",
            chat_id=chat_id,
            user_id=user_id,
        )
        return ctx

    owner_context = make_context("control-chat", "owner-oid")
    other_context = make_context("control-chat", "other-oid")
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner_future = pool.submit(owner_context.run, _patch, "owner-skill")
        other_future = pool.submit(other_context.run, _patch, "other-skill")
        owner_result = owner_future.result()
        other_result = other_future.result()

    assert owner_result["success"] is True, owner_result
    assert other_result["success"] is False, other_result
    assert "NEW_MARKER" in (skill_root / "owner-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "OLD_MARKER" in (skill_root / "other-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
