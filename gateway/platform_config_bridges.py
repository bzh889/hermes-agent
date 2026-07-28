"""Lightweight YAML bridges for disabled, deferred platform plugins."""

import os
from typing import Callable, Optional


def apply_discord_yaml_config(
    yaml_cfg: dict,
    discord_cfg: dict,
) -> Optional[dict]:
    env_values = {
        "require_mention": "DISCORD_REQUIRE_MENTION",
        "thread_require_mention": "DISCORD_THREAD_REQUIRE_MENTION",
        "bots_require_inline_mention": "DISCORD_BOTS_REQUIRE_INLINE_MENTION",
        "auto_thread": "DISCORD_AUTO_THREAD",
        "reactions": "DISCORD_REACTIONS",
        "history_backfill": "DISCORD_HISTORY_BACKFILL",
        "history_backfill_limit": "DISCORD_HISTORY_BACKFILL_LIMIT",
    }
    for config_key, env_key in env_values.items():
        if config_key in discord_cfg and not os.getenv(env_key):
            os.environ[env_key] = str(discord_cfg[config_key]).lower()

    platforms_cfg = yaml_cfg.get("platforms")
    platform_extra_cfg = {}
    if isinstance(platforms_cfg, dict):
        discord_platform_cfg = platforms_cfg.get("discord")
        if isinstance(discord_platform_cfg, dict):
            candidate_extra = discord_platform_cfg.get("extra")
            if isinstance(candidate_extra, dict):
                platform_extra_cfg = candidate_extra

    scalar_or_list_values = {
        "allow_from": "DISCORD_ALLOWED_USERS",
        "free_response_channels": "DISCORD_FREE_RESPONSE_CHANNELS",
        "ignored_channels": "DISCORD_IGNORED_CHANNELS",
        "allowed_channels": "DISCORD_ALLOWED_CHANNELS",
        "no_thread_channels": "DISCORD_NO_THREAD_CHANNELS",
    }
    for config_key, env_key in scalar_or_list_values.items():
        value = (
            discord_cfg[config_key]
            if config_key in discord_cfg
            else platform_extra_cfg.get(config_key)
        )
        if value is None or os.getenv(env_key):
            continue
        if isinstance(value, list):
            value = ",".join(str(item) for item in value)
        os.environ[env_key] = str(value)

    approval_mentions = (
        discord_cfg["approval_mentions"]
        if "approval_mentions" in discord_cfg
        else platform_extra_cfg.get("approval_mentions")
    )
    if approval_mentions is not None and not os.getenv("DISCORD_APPROVAL_MENTIONS"):
        os.environ["DISCORD_APPROVAL_MENTIONS"] = str(approval_mentions).lower()

    allow_mentions = discord_cfg.get("allow_mentions")
    if isinstance(allow_mentions, dict):
        for config_key, env_key in (
            ("everyone", "DISCORD_ALLOW_MENTION_EVERYONE"),
            ("roles", "DISCORD_ALLOW_MENTION_ROLES"),
            ("users", "DISCORD_ALLOW_MENTION_USERS"),
            ("replied_user", "DISCORD_ALLOW_MENTION_REPLIED_USER"),
        ):
            if config_key in allow_mentions and not os.getenv(env_key):
                os.environ[env_key] = str(allow_mentions[config_key]).lower()

    discord_extra = (
        discord_cfg.get("extra")
        if isinstance(discord_cfg.get("extra"), dict)
        else {}
    )
    reply_to_mode = (
        discord_cfg["reply_to_mode"]
        if "reply_to_mode" in discord_cfg
        else discord_extra.get("reply_to_mode")
    )
    if reply_to_mode is not None and not os.getenv("DISCORD_REPLY_TO_MODE"):
        os.environ["DISCORD_REPLY_TO_MODE"] = (
            "off" if reply_to_mode is False else str(reply_to_mode).lower()
        )

    seeded_extra = {}
    missed_message_backfill = discord_cfg.get("missed_message_backfill")
    if isinstance(missed_message_backfill, dict):
        seeded_extra["missed_message_backfill"] = dict(missed_message_backfill)

    websocket_config = {**discord_extra, **discord_cfg}
    for primary_key, legacy_key, env_key in (
        (
            "websocket_liveness_interval_seconds",
            "liveness_interval_seconds",
            "HERMES_DISCORD_LIVENESS_INTERVAL_SECONDS",
        ),
        (
            "websocket_liveness_failure_threshold",
            "liveness_failure_threshold",
            "HERMES_DISCORD_LIVENESS_FAILURE_THRESHOLD",
        ),
        ("websocket_heartbeat_ack_max_age_seconds", None, None),
        ("websocket_max_latency_seconds", None, None),
    ):
        value = websocket_config.get(primary_key)
        if value is None and legacy_key:
            value = websocket_config.get(legacy_key)
        if value is None:
            continue
        seeded_extra[primary_key] = value
        if env_key and not os.getenv(env_key):
            os.environ[env_key] = str(value)

    return seeded_extra or None


def apply_feishu_yaml_config(
    _yaml_cfg: dict,
    feishu_cfg: dict,
) -> None:
    if "allow_bots" in feishu_cfg and not os.getenv("FEISHU_ALLOW_BOTS"):
        os.environ["FEISHU_ALLOW_BOTS"] = str(feishu_cfg["allow_bots"]).lower()
    return None


LIGHTWEIGHT_PLATFORM_CONFIG_BRIDGES: dict[
    str,
    Callable[[dict, dict], Optional[dict]],
] = {
    "discord": apply_discord_yaml_config,
    "feishu": apply_feishu_yaml_config,
}
