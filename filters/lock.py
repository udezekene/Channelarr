"""Lock filter — protects named channels from any automated changes.

A locked channel is completely hands off. The filter marks UPDATE, CREATE, and
DELETE changes as SKIP(LOCKED). The only exceptions are:
  - A saved lock-override approval in the pairing store (user confirmed via wizard)
  - A channel name passed via --unlock (one-run override, not persisted)
"""

from __future__ import annotations
import dataclasses
from typing import Optional
from core.models import ChangeSet, ChannelChange, ChangeType, SkipReason
from core import normalizer as norm
from pairings.store import PairingStore


def apply(
    changeset: ChangeSet,
    locked_names: list[str],
    unlocked_names: list[str] | None = None,
    pairing_store: PairingStore | None = None,
) -> ChangeSet:
    """Return a new ChangeSet with locked changes marked SKIP(LOCKED)."""
    if not locked_names:
        return changeset

    normalized_locks = {norm.normalize(name) for name in locked_names}
    normalized_unlocks = {norm.normalize(n) for n in (unlocked_names or [])}

    new_changes = []
    for change in changeset.changes:
        if change.change_type == ChangeType.SKIP:
            new_changes.append(change)
            continue

        effective = _effective_name(change)

        if effective not in normalized_locks:
            new_changes.append(change)
            continue

        # --unlock flag: one-run pass-through
        if effective in normalized_unlocks:
            new_changes.append(change)
            continue

        # Pairing store approval: permanent pass-through
        if pairing_store and pairing_store.get_lock_approval(effective):
            new_changes.append(change)
            continue

        new_changes.append(dataclasses.replace(
            change,
            change_type=ChangeType.SKIP,
            skip_reason=SkipReason.LOCKED,
            skip_detail=(
                f"'{effective}' is locked. "
                "Run with --pair to approve via wizard, or --unlock to override once."
            ),
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
