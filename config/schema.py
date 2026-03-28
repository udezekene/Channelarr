"""Authoritative Config dataclass — defines the shape of config.yaml.

Sub-configs mirror each top-level YAML key. Defaults here match config.example.yaml.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class MatchingConfig:
    strategy: str = "regex"         # regex | exact | fuzzy
    normalizer: str = "default"     # default | aggressive | none
    fuzzy_threshold: float = 0.85   # 0.0–1.0, only used by fuzzy strategy
    scope_to_group: bool = False    # if True, streams only match channels in the same channel_group


@dataclass
class ConflictResolutionConfig:
    strategy: str = "highest_priority"  # highest_priority | most_recent | first_match


@dataclass
class LockConfig:
    channel_name: str
    reason: str = ""


@dataclass
class GroupRegion:
    """Maps a logical region/country name to a set of Dispatcharr channel_group IDs.

    When configured, streams from the same region are considered compatible for
    attachment matching. Streams from different regions with the same normalized
    name (e.g. MY|CNN and UK|CNN) are kept separate.
    """
    name: str
    groups: list[int] = field(default_factory=list)


@dataclass
class LoggingConfig:
    log_file: str = "~/.local/share/channelarr/channelarr.log"
    history_file: str = "~/.local/share/channelarr/history.jsonl"
    level: str = "INFO"


@dataclass
class WebConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 5000
    allow_apply: bool = False
    auto_open: bool = False


@dataclass
class Config:
    endpoint: str
    username: str
    password: str
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    provider_priority: list[str] = field(default_factory=list)  # M3U account names, first = highest priority
    epg_min_confidence: float = 0.0  # minimum match confidence for --assign-epg (0.0 = show all, 0.8 = 80%+)
    conflict_resolution: ConflictResolutionConfig = field(default_factory=ConflictResolutionConfig)
    allow_new_channels_default: bool = False
    allow_delete_default: bool = False
    locks: list[LockConfig] = field(default_factory=list)
    group_regions: list[GroupRegion] = field(default_factory=list)
    allowlist: list[str] = field(default_factory=list)
    blocklist: list[str] = field(default_factory=list)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    web: WebConfig = field(default_factory=WebConfig)
