"""
CLI commands for TeamsMTK group whitelist management.

Usage:
    hermes teams-mtk group add <conv_id> [--name NAME] [--require-mention]
    hermes teams-mtk group list
    hermes teams-mtk group set <conv_id> [--require-mention {true,false}]
                                          [--block-toolset NAME]...
                                          [--block-keyword PATTERN]...
                                          [--user OID --block-toolset NAME]...
    hermes teams-mtk group remove <conv_id>

Writes to gateway.teams_mtk.groups in the active profile's config.yaml. Changes to a
running gateway require a restart to take effect (gateway/platforms/teams_mtk.py
and gateway/authz_mixin.py read this config fresh on each poll tick, but the
adapter's own long-lived state — e.g. TEAMS_MTK_REQUIRE_MENTION-derived
defaults — is only evaluated at process start).

See openspec/changes/teams-mtk-hermes-native-parity/ for the design rationale.
"""

RESTART_NOTICE = "  Note: restart the gateway for this change to take effect.\n"


def teams_mtk_groups_command(args):
    """Handle `hermes teams-mtk group` subcommands."""
    action = getattr(args, "teams_mtk_group_action", None)

    if action == "add":
        _cmd_add(args)
    elif action == "list":
        _cmd_list(args)
    elif action == "set":
        _cmd_set(args)
    elif action == "remove":
        _cmd_remove(args)
    else:
        print("Usage: hermes teams-mtk group {add|list|set|remove}")
        print("Run 'hermes teams-mtk group --help' for details.")


def _load_groups():
    """Return (config_dict, groups_dict) — groups_dict is a live reference into config_dict."""
    from hermes_cli.config import load_config

    config = load_config()
    gateway = config.setdefault("gateway", {})
    teams_mtk = gateway.setdefault("teams_mtk", {})
    groups = teams_mtk.setdefault("groups", {})
    return config, groups


def _save(config):
    from hermes_cli.config import save_config

    save_config(config)


def _cmd_add(args):
    conv_id = args.conv_id.strip()
    if not conv_id:
        print("Error: conv_id must not be empty.")
        return

    config, groups = _load_groups()
    if conv_id in groups:
        print(f"\n  Group '{conv_id}' is already whitelisted. Use 'group set' to change it.\n")
        return

    entry = {"require_mention": bool(args.require_mention)}
    if args.name:
        entry["name"] = args.name

    groups[conv_id] = entry
    _save(config)

    label = args.name or conv_id
    print(f"\n  Added group '{label}' ({conv_id}) to the whitelist.")
    print(f"  require_mention: {entry['require_mention']}")
    print(RESTART_NOTICE)


def _cmd_list(args):
    from hermes_cli.config import load_config

    config = load_config()
    groups = config.get("gateway", {}).get("teams_mtk", {}).get("groups", {})
    if not isinstance(groups, dict) or not groups:
        print("\n  No TeamsMTK groups configured. Use 'hermes teams-mtk group add <conv_id>'.\n")
        return

    global_require_mention = (
        str(__import__("os").getenv("TEAMS_MTK_REQUIRE_MENTION", "true")).lower()
        in ("true", "1", "yes", "on")
    )

    print(f"\n  TeamsMTK Whitelisted Groups ({len(groups)}):\n")
    for conv_id, entry in groups.items():
        if not isinstance(entry, dict):
            entry = {}
        name = entry.get("name") or "(unnamed)"
        rm = entry.get("require_mention")
        if rm is None:
            rm_display = f"{global_require_mention} (fallback: global default)"
        else:
            rm_display = f"{bool(rm)} (group override)"
        blocked_toolsets = entry.get("blocked_toolsets") or []
        blocked_keywords = entry.get("blocked_keywords") or []
        per_user = entry.get("per_user") or {}

        print(f"  {name}")
        print(f"    conv_id:          {conv_id}")
        print(f"    require_mention:  {rm_display}")
        print(f"    blocked_toolsets: {blocked_toolsets or '(none)'}")
        print(f"    blocked_keywords: {blocked_keywords or '(none)'}")
        if per_user:
            print(f"    per_user overrides: {len(per_user)} user(s)")
            for uid, ucfg in per_user.items():
                ubt = (ucfg or {}).get("blocked_toolsets") or []
                print(f"      {uid}: blocked_toolsets={ubt}")
        print()


def _cmd_set(args):
    conv_id = args.conv_id.strip()
    config, groups = _load_groups()
    entry = groups.get(conv_id)
    if not isinstance(entry, dict):
        print(f"\n  Group '{conv_id}' is not whitelisted yet. Use 'group add' first.\n")
        return

    changed = False

    if args.require_mention is not None:
        entry["require_mention"] = args.require_mention.lower() in ("true", "1", "yes", "on")
        changed = True

    if args.name:
        entry["name"] = args.name
        changed = True

    target_user = getattr(args, "user", None)
    block_toolsets = getattr(args, "block_toolset", None) or []
    block_keywords = getattr(args, "block_keyword", None) or []

    if block_toolsets and target_user:
        per_user = entry.setdefault("per_user", {})
        user_cfg = per_user.setdefault(target_user, {})
        existing = set(user_cfg.get("blocked_toolsets") or [])
        existing |= set(block_toolsets)
        user_cfg["blocked_toolsets"] = sorted(existing)
        changed = True
    elif block_toolsets:
        existing = set(entry.get("blocked_toolsets") or [])
        existing |= set(block_toolsets)
        entry["blocked_toolsets"] = sorted(existing)
        changed = True

    if block_keywords:
        existing = list(entry.get("blocked_keywords") or [])
        for kw in block_keywords:
            if kw not in existing:
                existing.append(kw)
        entry["blocked_keywords"] = existing
        changed = True

    if not changed:
        print("\n  No changes specified. See 'hermes teams-mtk group set --help'.\n")
        return

    groups[conv_id] = entry
    _save(config)

    print(f"\n  Updated group '{entry.get('name') or conv_id}'.")
    print(f"    require_mention:  {entry.get('require_mention', '(fallback to global)')}")
    print(f"    blocked_toolsets: {entry.get('blocked_toolsets') or '(none)'}")
    print(f"    blocked_keywords: {entry.get('blocked_keywords') or '(none)'}")
    if entry.get("per_user"):
        print(f"    per_user:         {entry['per_user']}")
    print(RESTART_NOTICE)


def _cmd_remove(args):
    conv_id = args.conv_id.strip()
    config, groups = _load_groups()

    if conv_id not in groups:
        print(f"\n  Group '{conv_id}' is not in the whitelist.\n")
        return

    removed = groups.pop(conv_id)
    _save(config)

    label = (removed or {}).get("name") or conv_id
    print(f"\n  Removed group '{label}' ({conv_id}) from the whitelist.")
    print("  It reverts to the individual GATEWAY_ALLOWED_USERS allowlist.")
    print(RESTART_NOTICE)
