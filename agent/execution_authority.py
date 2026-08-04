"""Per-turn authority derived from trusted runtime session context.

The model never supplies these values. Gateway and TUI hosts bind immutable
origin metadata into ``gateway.session_context`` before an agent turn; this
module reduces that metadata plus operator config into narrowly-scoped
capabilities that enforcement seams can query.
"""

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet


class TurnCapability(str, Enum):
    """Capabilities granted to the current agent turn."""

    SKILL_WRITE = "skill_write"


@dataclass(frozen=True)
class ExecutionAuthority:
    """Immutable capability verdict for one runtime turn."""

    capabilities: FrozenSet[TurnCapability]
    surface: str
    reason: str

    def allows(self, capability: TurnCapability) -> bool:
        return capability in self.capabilities


_SKILL_WRITER = frozenset({TurnCapability.SKILL_WRITE})
_NO_CAPABILITIES: FrozenSet[TurnCapability] = frozenset()


def _authority(capabilities: FrozenSet[TurnCapability], surface: str, reason: str):
    return ExecutionAuthority(
        capabilities=capabilities,
        surface=surface,
        reason=reason,
    )


def _teams_mtk_control_owner(chat_id: str, user_id: str) -> bool:
    """Match the exact configured Teams MTK conversation/owner pair.

    ``groups`` and ``home_channel`` deliberately do not participate: they are
    routing/access policy, not owner execution authority.
    """
    if not chat_id or not user_id:
        return False
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly()
    except Exception:
        return False

    try:
        entries = config["gateway"]["teams_mtk"]["control_conversations"]
    except (KeyError, TypeError):
        return False
    if not isinstance(entries, dict):
        return False

    entry = entries.get(chat_id)
    if not isinstance(entry, dict):
        return False
    owner_user_ids = entry.get("owner_user_ids")
    if not isinstance(owner_user_ids, list):
        return False

    return user_id in {
        candidate.strip()
        for candidate in owner_user_ids
        if isinstance(candidate, str) and candidate.strip()
    }


def current_execution_authority() -> ExecutionAuthority:
    """Resolve authority for this turn, failing closed for hosted surfaces."""
    from gateway.session_context import (
        get_bound_session_env,
        get_session_env,
        session_context_engaged,
    )

    if session_context_engaged():
        platform_bound, platform = get_bound_session_env("HERMES_SESSION_PLATFORM")
        source_bound, source = get_bound_session_env("HERMES_SESSION_SOURCE")
        _, chat_id = get_bound_session_env("HERMES_SESSION_CHAT_ID")
        _, user_id = get_bound_session_env("HERMES_SESSION_USER_ID")
        # A gateway process between turns, or a newly-spawned task before its
        # own source is bound, is not a local CLI merely because fields are
        # empty. This is the fail-closed half of the ContextVar isolation.
        if not platform_bound and not source_bound:
            return _authority(
                _NO_CAPABILITIES,
                "unbound_hosted_runtime",
                "hosted runtime has no turn origin bound",
            )
    else:
        # Classic CLI processes do not engage gateway session ContextVars.
        platform = get_session_env("HERMES_SESSION_PLATFORM", "").strip()
        source = get_session_env("HERMES_SESSION_SOURCE", "").strip()
        chat_id = get_session_env("HERMES_SESSION_CHAT_ID", "").strip()
        user_id = get_session_env("HERMES_SESSION_USER_ID", "").strip()
        if not platform and not source:
            return _authority(
                _SKILL_WRITER,
                "local_cli",
                "direct local owner session",
            )

    platform = (platform or "").strip()
    source = (source or "").strip()
    chat_id = (chat_id or "").strip()
    user_id = (user_id or "").strip()

    if platform == "local" or source == "tui":
        return _authority(
            _SKILL_WRITER,
            "local_tui",
            "trusted local TUI owner session",
        )

    if platform == "teams_mtk" and _teams_mtk_control_owner(chat_id, user_id):
        return _authority(
            _SKILL_WRITER,
            "teams_mtk_control_owner",
            "exact Teams MTK control conversation and owner identity matched",
        )

    return _authority(
        _NO_CAPABILITIES,
        "untrusted_runtime",
        "turn is not a trusted local TUI or configured Teams MTK owner control pair",
    )
