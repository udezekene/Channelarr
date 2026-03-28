"""Transforms a ChangeSet into structured diff data.

`build_rows` returns a list of DiffRow objects consumed by ui/console.py.
`format_diff` is a plain-text fallback used by tests and non-Rich environments.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from core.models import ChangeSet, ChangeType, SkipReason, StreamMatch


@dataclass
class DiffRow:
    change_type: str            # "UPDATE" | "CREATE" | "DELETE" | "SKIP"
    name: str                   # display name (normalised stream name or channel name)
    stream_count: int = 0
    skip_reason: str | None = None
    match_type: str | None = None
    candidates: list[StreamMatch] = field(default_factory=list)


def build_rows(changeset: ChangeSet, verbose: bool = False) -> list[DiffRow]:
    """Return one DiffRow per ChannelChange, preserving changeset order.

    Already-correct channels are hidden unless verbose=True — they're noise.
    """
    rows: list[DiffRow] = []
    for change in changeset.changes:
        if not verbose and change.skip_reason == SkipReason.ALREADY_CORRECT:
            continue
        if change.winning_match:
            name = change.winning_match.normalized_stream_name
        elif change.channel:
            name = change.channel.name
        elif change.stream:
            name = change.stream.name
        else:
            name = "?"

        rows.append(DiffRow(
            change_type=change.change_type.value.upper(),
            name=name,
            stream_count=len(change.candidates),
            skip_reason=change.skip_reason.value if change.skip_reason else None,
            match_type=change.winning_match.match_type.value if change.winning_match else None,
            candidates=change.candidates,
        ))
    return rows


def format_diff(changeset: ChangeSet) -> str:
    """Plain-text fallback. ui/console.py supersedes this in the main pipeline."""
    lines: list[str] = []
    for row in build_rows(changeset):
        if row.change_type == "SKIP":
            lines.append(f"  SKIP    {row.name!r}  [{row.skip_reason}]")
        elif row.change_type == "DELETE":
            lines.append(f"  DELETE  {row.name!r}")
        else:
            lines.append(f"  {row.change_type:<7} {row.name!r}  ({row.stream_count} stream(s))")

    summary = (
        f"\n{len(changeset.creates)} to create, "
        f"{len(changeset.updates)} to update, "
        f"{len(changeset.deletes)} to delete, "
        f"{len(changeset.skips)} skipped."
    )
    return "\n".join(lines) + summary
