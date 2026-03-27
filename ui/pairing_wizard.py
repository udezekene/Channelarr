"""Pairing wizard — interactive dry-run UI for resolving ambiguous matches and
approving changes to locked channels.

Phase 2: plain text prompts via input().
Phase 3 will upgrade this to Rich-formatted tables.

Two sections
------------
1. Ambiguous matches — changes with multiple candidates and no saved pairing.
   User picks the correct channel from a ranked list.

2. Locked channel approvals — SKIP(LOCKED) changes the user wants to approve
   permanently. Approval is saved to the pairing store with override_lock=True.
   Future runs will proceed without prompting.
"""

from __future__ import annotations
from datetime import date
from core.models import ChangeSet, ChangeType, SkipReason, SavedPairing, StreamMatch
from pairings.store import PairingStore


def run(changeset: ChangeSet, store: PairingStore) -> None:
    """Run the wizard against the given ChangeSet. Modifies the pairing store in place."""
    ambiguous = _ambiguous_changes(changeset)
    locked = _locked_changes(changeset)

    if not ambiguous and not locked:
        print("Nothing to review — all matches are confirmed.")
        return

    if ambiguous:
        print(f"\n── Ambiguous matches ({len(ambiguous)}) ──────────────────────────")
        print("These streams matched multiple channels. Pick the correct one.\n")
        _handle_ambiguous(ambiguous, store)

    if locked:
        print(f"\n── Locked channels ({len(locked)}) ──────────────────────────────")
        print("These channels are locked. Approving saves to your pairing store;")
        print("future runs will proceed automatically without prompting.\n")
        _handle_locked(locked, store)


def has_pending(changeset: ChangeSet) -> bool:
    """Return True if the wizard has anything to show."""
    return bool(_ambiguous_changes(changeset) or _locked_changes(changeset))


# ------------------------------------------------------------------ internals

def _ambiguous_changes(changeset: ChangeSet):
    return [
        c for c in changeset.changes
        if c.change_type in (ChangeType.UPDATE, ChangeType.CREATE)
        and len(c.candidates) > 1
        and c.winning_match and c.winning_match.match_type.value != "saved"
    ]


def _locked_changes(changeset: ChangeSet):
    return [
        c for c in changeset.changes
        if c.change_type == ChangeType.SKIP
        and c.skip_reason == SkipReason.LOCKED
    ]


def _handle_ambiguous(changes, store: PairingStore) -> None:
    for change in changes:
        stream_name = change.winning_match.normalized_stream_name if change.winning_match else "?"
        print(f"  Stream: {stream_name!r}  ({len(change.candidates)} candidates)")

        # Sort: same-group candidates first, then by score descending
        ranked = sorted(
            change.candidates,
            key=lambda m: (
                0 if (change.stream and m.channel and
                      m.channel.channel_group_id == change.stream.channel_group) else 1,
                -m.score,
            ),
        )

        for i, m in enumerate(ranked, start=1):
            ch = m.channel
            group_note = f" [group {ch.channel_group_id}]" if ch and ch.channel_group_id else ""
            print(f"    [{i}] {ch.name if ch else '?'}{group_note}")

        print(f"    [s] Skip — decide later")

        choice = input("  Pick: ").strip().lower()
        if choice == "s" or not choice:
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ranked):
                selected = ranked[idx]
                if selected.channel:
                    pairing = SavedPairing(
                        normalized_stream_name=stream_name,
                        channel_group=change.stream.channel_group if change.stream else None,
                        channel_id=selected.channel.id,
                        channel_name=selected.channel.name,
                        confirmed_at=str(date.today()),
                        active=True,
                        override_lock=False,
                    )
                    store.save(pairing)
                    print(f"  Saved: {stream_name!r} → {selected.channel.name!r}\n")
        except (ValueError, IndexError):
            print("  Invalid choice, skipping.\n")


def _handle_locked(changes, store: PairingStore) -> None:
    for change in changes:
        channel_name = change.channel.name if change.channel else (
            change.winning_match.normalized_stream_name if change.winning_match else "?"
        )
        n = len(change.candidates)
        print(f"  Channel: {channel_name!r}  ({n} stream(s) pending)")

        choice = input("  Approve for all future runs? [y/N]: ").strip().lower()
        if choice == "y":
            pairing = SavedPairing(
                normalized_stream_name=channel_name,
                channel_group=change.channel.channel_group_id if change.channel else None,
                channel_id=change.channel.id if change.channel else 0,
                channel_name=channel_name,
                confirmed_at=str(date.today()),
                active=True,
                override_lock=True,
            )
            store.save(pairing)
            print(f"  Approved. '{channel_name}' will be updated on future runs.\n")
        else:
            print(f"  Skipped. '{channel_name}' remains locked.\n")
