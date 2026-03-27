"""Allowlist filter — scopes a run to a named subset of channels.

If the allowlist is non-empty, any change whose resolved channel name is NOT in
the list is marked SKIP(NOT_IN_ALLOWLIST). Channels already marked SKIP are
passed through unchanged (first SKIP reason wins).
"""

from __future__ import annotations
import dataclasses
from core.models import ChangeSet, ChannelChange, ChangeType, SkipReason
from core import normalizer as norm


def apply(changeset: ChangeSet, allowlist: list[str]) -> ChangeSet:
    """Return a new ChangeSet with out-of-allowlist changes marked as SKIP."""
    if not allowlist:
        return changeset

    normalized_allow = {norm.normalize(name) for name in allowlist}

    new_changes = []
    for change in changeset.changes:
        if change.change_type == ChangeType.SKIP:
            new_changes.append(change)
            continue

        if _effective_name(change) in normalized_allow:
            new_changes.append(change)
        else:
            new_changes.append(dataclasses.replace(
                change,
                change_type=ChangeType.SKIP,
                skip_reason=SkipReason.NOT_IN_ALLOWLIST,
                skip_detail="Not in allowlist. Add to config allowlist to include.",
            ))

    return ChangeSet(changes=new_changes)


def _effective_name(change: ChannelChange) -> str:
    if change.channel:
        return norm.normalize(change.channel.name)
    if change.winning_match:
        return change.winning_match.normalized_stream_name
    if change.stream:
        return norm.normalize(change.stream.name)
    return ""
