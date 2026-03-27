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
class ProviderPriority:
    name: str
    rank: int                       # lower number = higher priority


@dataclass
class ConflictResolutionConfig:
    strategy: str = "highest_priority"  # highest_priority | most_recent | first_match


@dataclass
class LockConfig:
    channel_name: str
    reason: str = ""


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
    provider_priority: list[ProviderPriority] = field(default_factory=list)
    conflict_resolution: ConflictResolutionConfig = field(default_factory=ConflictResolutionConfig)
    allow_new_channels_default: bool = False
    allow_delete_default: bool = False
    locks: list[LockConfig] = field(default_factory=list)
    allowlist: list[str] = field(default_factory=list)
    blocklist: list[str] = field(default_factory=list)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    web: WebConfig = field(default_factory=WebConfig)
