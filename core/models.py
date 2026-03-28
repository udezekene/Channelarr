"""All runtime dataclasses for Channelarr.

Every other module imports its data types from here. No logic lives here — pure data only.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class ChangeType(Enum):
    CREATE = "create"   # new channel will be created
    UPDATE = "update"   # existing channel will have streams updated
    DELETE = "delete"   # channel will be deleted (requires --allow-delete)
    SKIP   = "skip"     # evaluated but will not be applied


class SkipReason(Enum):
    LOCKED               = "locked"
    BLOCKED              = "blocked"
    NOT_IN_ALLOWLIST     = "not_in_allowlist"
    CREATE_NOT_PERMITTED = "create_not_permitted"
    DELETE_NOT_PERMITTED = "delete_not_permitted"
    NO_MATCH             = "no_match"
    CONFLICT_UNRESOLVED  = "conflict_unresolved"
    USER_SKIPPED         = "user_skipped"   # interactive mode
    ALREADY_CORRECT      = "already_correct"  # channel already has exactly the right streams


class MatchType(Enum):
    EXACT      = "exact"
    REGEX      = "regex"
    FUZZY      = "fuzzy"
    SAVED      = "saved"       # match came from pairing store, not the live strategy
    ATTACHMENT = "attachment"  # match came from a stream already attached to the channel
    NONE       = "none"


@dataclass
class Stream:
    id: int
    name: str
    provider: Optional[str]
    channel_group: Optional[int]      # Dispatcharr channel_group FK; used for group-scoped matching
    raw: dict[str, Any]               # original API dict; used when constructing PUT payloads


@dataclass
class Channel:
    id: int
    name: str
    stream_ids: list[int]
    channel_group_id: Optional[int]   # Dispatcharr channel_group FK
    raw: dict[str, Any]
    epg_data_id: Optional[int] = None  # FK to EpgEntry; None = no EPG assigned
    tvg_id: Optional[str] = None       # XMLTV channel ID string (e.g. "SABC1.za")


@dataclass
class EpgEntry:
    id: int
    tvg_id: str     # e.g. "SkySportsF1.uk"
    name: str       # display name from XMLTV source, e.g. "UK-Sky Sports F1 HD"
    epg_source: int  # FK to EPG source feed


@dataclass
class EpgProposal:
    channel: Channel
    epg_entry: EpgEntry
    confidence: float  # 0.0–1.0
    method: str        # "provider+suffix" | "provider" | "suffix" | "name_only"


@dataclass
class StreamMatch:
    stream: Stream
    channel: Optional[Channel]
    match_type: MatchType
    score: float                        # 1.0 for exact/saved, 0.0–1.0 for fuzzy
    normalized_stream_name: str
    normalized_channel_name: Optional[str]


@dataclass
class ChannelChange:
    change_type: ChangeType
    channel: Optional[Channel]
    winning_match: Optional[StreamMatch]
    stream: Optional[Stream] = None     # None for DELETE changes (no stream triggered them)
    candidates: list[StreamMatch] = field(default_factory=list)
    skip_reason: Optional[SkipReason] = None
    skip_detail: Optional[str] = None


@dataclass
class AuditReport:
    """Results of a --audit run, grouped by issue category."""
    no_epg: list[Channel] = field(default_factory=list)           # epg_data_id is None
    no_streams: list[Channel] = field(default_factory=list)        # stream_ids is empty
    orphan_streams: list[Stream] = field(default_factory=list)     # stream not attached to any channel
    stale_epg: list[Channel] = field(default_factory=list)         # epg_data_id points to a deleted EPG entry

    @property
    def is_clean(self) -> bool:
        return not (self.no_epg or self.no_streams or self.orphan_streams or self.stale_epg)


@dataclass
class SavedPairing:
    """A user-confirmed stream→channel pairing, persisted in pairings.json."""
    normalized_stream_name: str
    channel_group: Optional[int]        # stream's channel_group at time of confirmation
    channel_id: int
    channel_name: str
    confirmed_at: str                   # ISO date string e.g. "2026-03-27"
    active: bool = True                 # set False to disable without deleting
    override_lock: bool = False         # True if this approval came from the pairing wizard for a locked channel


@dataclass
class ChangeSet:
    changes: list[ChannelChange] = field(default_factory=list)

    @property
    def creates(self) -> list[ChannelChange]:
        return [c for c in self.changes if c.change_type == ChangeType.CREATE]

    @property
    def updates(self) -> list[ChannelChange]:
        return [c for c in self.changes if c.change_type == ChangeType.UPDATE]

    @property
    def deletes(self) -> list[ChannelChange]:
        return [c for c in self.changes if c.change_type == ChangeType.DELETE]

    @property
    def skips(self) -> list[ChannelChange]:
        return [c for c in self.changes if c.change_type == ChangeType.SKIP]

    @property
    def already_correct(self) -> list[ChannelChange]:
        return [c for c in self.changes
                if c.skip_reason == SkipReason.ALREADY_CORRECT]


@dataclass
class AppliedChange:
    change: ChannelChange
    success: bool
    api_response: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class RunResult:
    applied: list[AppliedChange] = field(default_factory=list)
    dry_run: bool = True
    total_evaluated: int = 0

    @property
    def succeeded(self) -> list[AppliedChange]:
        return [a for a in self.applied if a.success]

    @property
    def failed(self) -> list[AppliedChange]:
        return [a for a in self.applied if not a.success]

    @property
    def actually_applied(self) -> list[AppliedChange]:
        """Changes that were genuinely written to the API (not just recorded skips)."""
        return [
            a for a in self.applied
            if a.success and a.change.change_type != ChangeType.SKIP
        ]

    @property
    def skipped(self) -> list[AppliedChange]:
        return [a for a in self.applied if a.change.change_type == ChangeType.SKIP]
