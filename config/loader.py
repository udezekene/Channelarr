"""Reads and writes ~/.config/channelarr/config.yaml.

Always returns a typed Config dataclass — no raw dicts leave this module.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from config.schema import (
    Config,
    MatchingConfig,
    ProviderPriority,
    ConflictResolutionConfig,
    LockConfig,
    GroupRegion,
    LoggingConfig,
    WebConfig,
)

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "channelarr" / "config.yaml"


def load(path: Path | None = None) -> Config:
    """Read config.yaml and return a Config instance.

    Raises FileNotFoundError if the file does not exist (caller should
    offer to run the wizard).
    """
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found at {config_path}. "
            "Run with --reconfigure to set up Channelarr."
        )
    with open(config_path) as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    return _parse(data)


def write(config: Config, path: Path | None = None) -> None:
    """Serialise config to YAML and write it to disk, creating directories as needed."""
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(_serialise(config), f, default_flow_style=False, allow_unicode=True)


# ------------------------------------------------------------------- parsing

def _parse(data: dict[str, Any]) -> Config:
    if "endpoint" not in data:
        raise ValueError(
            "Config is missing required field 'endpoint'. "
            "Run with --reconfigure to fix your config."
        )

    m = data.get("matching", {})
    matching = MatchingConfig(
        strategy=m.get("strategy", "regex"),
        normalizer=m.get("normalizer", "default"),
        fuzzy_threshold=float(m.get("fuzzy_threshold", 0.85)),
        scope_to_group=bool(m.get("scope_to_group", False)),
    )

    provider_priority = [
        ProviderPriority(name=p["name"], rank=int(p["rank"]))
        for p in data.get("provider_priority", [])
    ]

    cr = data.get("conflict_resolution", {})
    conflict = ConflictResolutionConfig(strategy=cr.get("strategy", "highest_priority"))

    locks = [
        LockConfig(channel_name=lock["channel_name"], reason=lock.get("reason", ""))
        for lock in data.get("locks", [])
    ]

    group_regions = [
        GroupRegion(
            name=r["name"],
            groups=[int(g) for g in r.get("groups", [])],
        )
        for r in data.get("group_regions", [])
    ]

    lg = data.get("logging", {})
    logging_cfg = LoggingConfig(
        log_file=lg.get("log_file", "~/.local/share/channelarr/channelarr.log"),
        history_file=lg.get("history_file", "~/.local/share/channelarr/history.jsonl"),
        level=lg.get("level", "INFO"),
    )

    w = data.get("web", {})
    web = WebConfig(
        enabled=bool(w.get("enabled", False)),
        host=w.get("host", "127.0.0.1"),
        port=int(w.get("port", 5000)),
        allow_apply=bool(w.get("allow_apply", False)),
        auto_open=bool(w.get("auto_open", False)),
    )

    return Config(
        endpoint=data["endpoint"],
        username=data.get("username", ""),
        password=data.get("password", ""),
        matching=matching,
        provider_priority=provider_priority,
        conflict_resolution=conflict,
        allow_new_channels_default=bool(data.get("allow_new_channels_default", False)),
        allow_delete_default=bool(data.get("allow_delete_default", False)),
        locks=locks,
        group_regions=group_regions,
        allowlist=list(data.get("allowlist", [])),
        blocklist=list(data.get("blocklist", [])),
        logging=logging_cfg,
        web=web,
    )


def _serialise(config: Config) -> dict[str, Any]:
    return {
        "endpoint": config.endpoint,
        "username": config.username,
        "password": config.password,
        "matching": {
            "strategy": config.matching.strategy,
            "normalizer": config.matching.normalizer,
            "fuzzy_threshold": config.matching.fuzzy_threshold,
            "scope_to_group": config.matching.scope_to_group,
        },
        "provider_priority": [
            {"name": p.name, "rank": p.rank} for p in config.provider_priority
        ],
        "conflict_resolution": {"strategy": config.conflict_resolution.strategy},
        "allow_new_channels_default": config.allow_new_channels_default,
        "allow_delete_default": config.allow_delete_default,
        "locks": [
            {"channel_name": lock.channel_name, "reason": lock.reason}
            for lock in config.locks
        ],
        "group_regions": [
            {"name": r.name, "groups": r.groups}
            for r in config.group_regions
        ],
        "allowlist": config.allowlist,
        "blocklist": config.blocklist,
        "logging": {
            "log_file": config.logging.log_file,
            "history_file": config.logging.history_file,
            "level": config.logging.level,
        },
        "web": {
            "enabled": config.web.enabled,
            "host": config.web.host,
            "port": config.web.port,
            "allow_apply": config.web.allow_apply,
            "auto_open": config.web.auto_open,
        },
    }
