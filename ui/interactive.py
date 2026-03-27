"""Interactive per-change approval mode (--interactive / -i).

Presents each actionable change one at a time and lets the user approve,
skip, or quit. User-skipped changes are marked SKIP(USER_SKIPPED) in the
returned ChangeSet so the executor never sees them.
"""

from __future__ import annotations
import dataclasses
from rich.console import Console
from rich.prompt import Prompt
from core.models import ChangeSet, ChangeType, SkipReason, ChannelChange

_console = Console()


def run(changeset: ChangeSet) -> ChangeSet:
    """Return a new ChangeSet with user decisions applied.

    - Approved changes are kept as-is.
    - User-skipped changes become SKIP(USER_SKIPPED).
    - Already-SKIP changes pass through unchanged.
    - If the user quits early, all remaining unanswered changes are skipped.
    """
    actionable = [c for c in changeset.changes if c.change_type != ChangeType.SKIP]

    if not actionable:
        _console.print("[dim]No actionable changes to review.[/dim]")
        return changeset

    _console.print(f"\n[bold]Interactive review — {len(actionable)} change(s)[/bold]")
    _console.print("[dim]y = approve  ·  s = skip  ·  q = quit (skip rest)[/dim]\n")

    skipped_ids: set[int] = set()

    for i, change in enumerate(actionable):
        name = _display_name(change)
        ct = change.change_type.value.upper()
        _console.print(f"[bold]{i + 1}/{len(actionable)}[/bold]  [{ct}] [bold]{name}[/bold]")

        if change.candidates:
            for cand in change.candidates:
                provider = cand.stream.provider or "unknown"
                _console.print(f"         [dim]↳ {cand.stream.name!r}  ({provider})[/dim]")

        answer = Prompt.ask(
            "  Approve?",
            choices=["y", "s", "q"],
            default="y",
            show_choices=False,
            show_default=False,
        )
        _console.print("")

        if answer == "q":
            # Skip this change and all remaining
            for remaining in actionable[i:]:
                skipped_ids.add(id(remaining))
            _console.print("[yellow]Quit — remaining changes will be skipped.[/yellow]\n")
            break
        elif answer == "s":
            skipped_ids.add(id(change))

    # Rebuild changeset, substituting SKIP(USER_SKIPPED) where needed
    final: list[ChannelChange] = []
    for change in changeset.changes:
        if id(change) in skipped_ids:
            final.append(_as_user_skipped(change))
        else:
            final.append(change)

    result = ChangeSet()
    result.changes = final
    return result


# ──────────────────────────────────────────────── helpers

def _display_name(change: ChannelChange) -> str:
    if change.winning_match:
        return change.winning_match.normalized_stream_name
    if change.channel:
        return change.channel.name
    if change.stream:
        return change.stream.name
    return "?"


def _as_user_skipped(change: ChannelChange) -> ChannelChange:
    return dataclasses.replace(
        change,
        change_type=ChangeType.SKIP,
        skip_reason=SkipReason.USER_SKIPPED,
    )
