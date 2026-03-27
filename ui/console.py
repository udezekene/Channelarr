"""Rich-formatted terminal output for Channelarr.

All terminal rendering lives here. No other module should import `rich` directly.
"""

from __future__ import annotations
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box
from core.differ import build_rows
from core.models import ChangeSet

_console = Console()

_COLORS: dict[str, str] = {
    "UPDATE": "green",
    "CREATE": "cyan",
    "DELETE": "red",
    "SKIP":   "dim",
}


def print_diff(changeset: ChangeSet, verbose: bool = False) -> None:
    """Print a color-coded diff table, then a summary line."""
    rows = build_rows(changeset)

    if not rows:
        _console.print("[dim]No changes planned.[/dim]")
        _print_summary(changeset)
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("CHANGE",  width=8,  no_wrap=True)
    table.add_column("CHANNEL / STREAM")
    table.add_column("STREAMS", justify="right", width=8,  no_wrap=True)
    table.add_column("DETAIL",  style="dim")

    for row in rows:
        color = _COLORS.get(row.change_type, "white")
        ct_cell = Text(row.change_type, style=color)

        streams_cell = (
            str(row.stream_count)
            if row.change_type in ("UPDATE", "CREATE")
            else ""
        )
        detail_cell = row.skip_reason or (row.match_type or "")

        table.add_row(ct_cell, row.name, streams_cell, detail_cell)

        if verbose and row.candidates:
            for i, cand in enumerate(row.candidates):
                connector = "└─" if i == len(row.candidates) - 1 else "├─"
                provider = cand.stream.provider or "unknown"
                table.add_row(
                    "",
                    Text(f"  {connector} {cand.stream.name}  ({provider})", style="dim"),
                    "",
                    Text(cand.match_type.value, style="dim"),
                )

    _console.print(table)
    _print_summary(changeset)


def print_summary(changeset: ChangeSet) -> None:
    """One-line summary — used by --quiet mode."""
    _print_summary(changeset)


def print_apply_result(applied: int, skipped: int, failed: int) -> None:
    parts: list[str] = []
    if applied:
        parts.append(f"[green]{applied} applied[/green]")
    if skipped:
        parts.append(f"[dim]{skipped} skipped[/dim]")
    if failed:
        parts.append(f"[red]{failed} failed[/red]")
    if not parts:
        parts.append("[dim]nothing to apply[/dim]")
    _console.print("  " + "  ·  ".join(parts))


def print_dedup_groups(groups: list) -> None:
    """Display duplicate channel groups before a dedup apply."""
    from dedup.finder import DedupGroup
    if not groups:
        _console.print("[dim]No duplicate channels found.[/dim]")
        return

    _console.print(f"\nFound [bold]{len(groups)}[/bold] duplicate channel group(s):\n")
    for group in groups:
        _console.print(f"  [bold]{group.normalized_name}[/bold]")
        _console.print(
            f"    [green]KEEP [/green]  [{group.winner.id}] {group.winner.name}"
            f"  [dim]({len(group.winner.stream_ids)} stream(s))[/dim]"
        )
        for dup in group.duplicates:
            _console.print(
                f"    [red]MERGE[/red]  [{dup.id}] {dup.name}"
                f"  [dim]({len(dup.stream_ids)} stream(s))[/dim]"
            )
        _console.print(
            f"    [dim]→ {len(group.merged_stream_ids)} stream(s) total after merge[/dim]\n"
        )


def print_dedup_result(merged: int, failed: int) -> None:
    parts: list[str] = []
    if merged:
        parts.append(f"[green]{merged} merged[/green]")
    if failed:
        parts.append(f"[red]{failed} failed[/red]")
    if not parts:
        parts.append("[dim]nothing to merge[/dim]")
    _console.print("  " + "  ·  ".join(parts))


def print_error(message: str) -> None:
    _console.print(f"[red]Error:[/red] {message}")


def print_info(message: str) -> None:
    _console.print(message)


# ──────────────────────────────────────────────── internal

def _print_summary(changeset: ChangeSet) -> None:
    parts: list[str] = []
    if changeset.creates:
        parts.append(f"[cyan]{len(changeset.creates)} to create[/cyan]")
    if changeset.updates:
        parts.append(f"[green]{len(changeset.updates)} to update[/green]")
    if changeset.deletes:
        parts.append(f"[red]{len(changeset.deletes)} to delete[/red]")
    if changeset.skips:
        parts.append(f"[dim]{len(changeset.skips)} skipped[/dim]")

    if parts:
        _console.print("  " + "  ·  ".join(parts))
    else:
        _console.print("[dim]Nothing to do.[/dim]")
