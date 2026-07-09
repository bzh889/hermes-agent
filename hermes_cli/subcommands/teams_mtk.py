"""``hermes teams-mtk`` subcommand parser.

Currently only exposes the ``group`` subcommand for managing the TeamsMTK
per-group whitelist (gateway.teams_mtk.groups in config.yaml). Follows the
same parser-builder + injected-handler pattern as
``hermes_cli/subcommands/pairing.py``.
"""

from __future__ import annotations

from typing import Callable


def build_teams_mtk_parser(subparsers, *, cmd_teams_mtk_group: Callable) -> None:
    """Attach the ``teams-mtk`` subcommand (with ``group`` sub-subcommand) to *subparsers*."""
    teams_mtk_parser = subparsers.add_parser(
        "teams-mtk",
        help="Manage the MTK internal Teams adapter (group whitelist, policy)",
        description="Configure gateway.teams_mtk settings such as the per-group whitelist",
    )
    teams_mtk_sub = teams_mtk_parser.add_subparsers(dest="teams_mtk_action")

    group_parser = teams_mtk_sub.add_parser(
        "group", help="Manage the group whitelist (gateway.teams_mtk.groups)"
    )
    group_sub = group_parser.add_subparsers(dest="teams_mtk_group_action")

    add_parser = group_sub.add_parser(
        "add", help="Add a group conversation to the whitelist"
    )
    add_parser.add_argument(
        "conv_id", help="Teams conversation id (e.g. 19:xxx@thread.v2)"
    )
    add_parser.add_argument("--name", help="Human-readable label for this group")
    add_parser.add_argument(
        "--require-mention",
        action="store_true",
        default=False,
        help="Require @hermes mention in this group (default: not required)",
    )

    group_sub.add_parser("list", help="List all whitelisted groups and their effective policy")

    set_parser = group_sub.add_parser("set", help="Update a whitelisted group's policy")
    set_parser.add_argument("conv_id", help="Teams conversation id to update")
    set_parser.add_argument("--name", help="Update the human-readable label")
    set_parser.add_argument(
        "--require-mention",
        choices=["true", "false"],
        default=None,
        help="Override whether @hermes mention is required in this group",
    )
    set_parser.add_argument(
        "--block-toolset",
        action="append",
        dest="block_toolset",
        metavar="NAME",
        help="Disable a toolset for this group (repeatable)",
    )
    set_parser.add_argument(
        "--block-keyword",
        action="append",
        dest="block_keyword",
        metavar="PATTERN",
        help="Add a regex pattern to blocked_keywords (repeatable)",
    )
    set_parser.add_argument(
        "--user",
        dest="user",
        metavar="OID",
        help="Scope --block-toolset to this sender's OID instead of the whole group",
    )

    remove_parser = group_sub.add_parser("remove", help="Remove a group from the whitelist")
    remove_parser.add_argument("conv_id", help="Teams conversation id to remove")

    teams_mtk_parser.set_defaults(func=cmd_teams_mtk_group)
