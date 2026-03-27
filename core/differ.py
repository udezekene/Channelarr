"""Formats a ChangeSet into diff output.

Phase 1: plain text lines.
Phase 3 will replace this with structured data rendered by ui/console.py (Rich tables).
"""

from core.models import ChangeSet, ChangeType


def format_diff(changeset: ChangeSet) -> str:
    """Return a human-readable diff string from a ChangeSet."""
    lines: list[str] = []

    for change in changeset.changes:
        # Derive a display name; DELETE changes have no stream or winning_match
        if change.winning_match:
            name = change.winning_match.normalized_stream_name
        elif change.channel:
            name = change.channel.name
        elif change.stream:
            name = change.stream.name
        else:
            name = "?"

        n = len(change.candidates)

        match change.change_type:
            case ChangeType.UPDATE:
                lines.append(f"  UPDATE  {name!r}  ({n} stream(s))")
            case ChangeType.CREATE:
                lines.append(f"  CREATE  {name!r}  ({n} stream(s))")
            case ChangeType.DELETE:
                lines.append(f"  DELETE  {name!r}")
            case ChangeType.SKIP:
                reason = change.skip_reason.value if change.skip_reason else "unknown"
                lines.append(f"  SKIP    {name!r}  [{reason}]")

    summary = (
        f"\n{len(changeset.creates)} to create, "
        f"{len(changeset.updates)} to update, "
        f"{len(changeset.deletes)} to delete, "
        f"{len(changeset.skips)} skipped."
    )
    return "\n".join(lines) + summary
