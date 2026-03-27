"""Blocklist filter — permanently excludes named channels from any changes.

Blocked channels are marked SKIP(BLOCKED). They appear in the ChangeSet (so
you can see they were evaluated) but the executor will never act on them.
In verbose mode they're visible; the default diff view hides BLOCKED items
(Phase 3 concern — for now they show like any other SKIP).
"""

from __future__ import annotations
import dataclasses
from core.models import ChangeSet, ChannelChange, ChangeType, SkipReason
from core import normalizer as norm


def apply(changeset: ChangeSet, blocklist: list[str]) -> ChangeSet:
    """Return a new ChangeSet with blocked changes marked SKIP(BLOCKED)."""
    if not blocklist:
        return changeset

    normalized_block = {norm.normalize(name) for name in blocklist}

    new_changes = []
    for change in changeset.changes:
        if change.change_type == ChangeType.SKIP:
            new_changes.append(change)
            continue

        if _effective_name(change) in normalized_block:
            new_changes.append(dataclasses.replace(
                change,
                change_type=ChangeType.SKIP,
                skip_reason=SkipReason.BLOCKED,
                skip_detail="On the blocklist. Remove from config blocklist to process.",
            ))
        else:
            new_changes.append(change)

    return ChangeSet(changes=new_changes)


def _effective_name(change: ChannelChange) -> str:
    if change.channel:
        return norm.normalize(change.channel.name)
    if change.winning_match:
        return change.winning_match.normalized_stream_name
    if change.stream:
        return norm.normalize(change.stream.name)
    return ""
