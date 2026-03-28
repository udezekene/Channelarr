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
    rows = build_rows(changeset, verbose=verbose)

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
    if not groups:
        _console.print("[dim]No duplicate channels found.[/dim]")
        return

    auto = [g for g in groups if g.confidence == "auto"]
    review = [g for g in groups if g.confidence == "review"]

    _console.print(f"\nFound [bold]{len(groups)}[/bold] duplicate channel group(s):"
                   f"  [green]{len(auto)} auto[/green]  [yellow]{len(review)} need review[/yellow]\n")

    for group in groups:
        confidence_tag = (
            "[green][auto][/green]" if group.confidence == "auto"
            else "[yellow][review][/yellow]"
        )
        _console.print(f"  {confidence_tag} [bold]{group.normalized_name}[/bold]")
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


def print_rename_proposals(proposals: list) -> None:
    """Display channel rename proposals before a --cleanup apply."""
    if not proposals:
        _console.print("[dim]No channel renames needed.[/dim]")
        return

    _console.print(f"\nFound [bold]{len(proposals)}[/bold] channel(s) to rename:\n")
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("ID", width=6, no_wrap=True)
    table.add_column("CURRENT NAME")
    table.add_column("PROPOSED NAME", style="cyan")

    for p in proposals:
        table.add_row(str(p.channel.id), p.current_name, p.proposed_name)

    _console.print(table)


def print_rename_result(succeeded: int, failed: int) -> None:
    parts: list[str] = []
    if succeeded:
        parts.append(f"[green]{succeeded} renamed[/green]")
    if failed:
        parts.append(f"[red]{failed} failed[/red]")
    if not parts:
        parts.append("[dim]nothing to rename[/dim]")
    _console.print("  " + "  ·  ".join(parts))


def print_stream_reorder_proposals(stats, stream_lookup: dict, verbose: bool = False) -> None:
    """Display stream reorder proposals before a --cleanup apply."""
    proposals = stats.proposals
    _console.print(
        f"\nStream ordering:  "
        f"[bold]{len(proposals)}[/bold] to reorder  ·  "
        f"[dim]{stats.already_optimal} already optimal  ·  "
        f"{stats.single_stream} single-stream (skipped)[/dim]"
    )
    if not proposals:
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("CHANNEL")
    table.add_column("NEW #1 STREAM", style="cyan")
    table.add_column("PROVIDER", style="green")
    table.add_column("WAS #1 STREAM", style="dim")

    for p in proposals:
        new_top_id = p.proposed_stream_ids[0]
        old_top_id = p.current_stream_ids[0]
        new_stream = stream_lookup.get(new_top_id)
        old_stream = stream_lookup.get(old_top_id)
        new_name   = new_stream.name     if new_stream else str(new_top_id)
        new_prov   = new_stream.provider if new_stream else "—"
        old_name   = old_stream.name     if old_stream else str(old_top_id)
        was_col    = old_name if old_top_id != new_top_id else "[dim]—[/dim]"
        table.add_row(p.channel.name, new_name, new_prov or "—", was_col)

    _console.print(table)


def print_stream_reorder_result(
    succeeded: list,
    failed: list,
    stream_lookup: dict,
) -> None:
    """Print a per-channel report of what changed after stream reordering."""
    if failed:
        for proposal, error in failed:
            _console.print(f"  [red]FAILED[/red] {proposal.channel.name!r} — {error}")

    if not succeeded:
        _console.print("  [dim]nothing to reorder[/dim]")
        return

    _console.print(f"  [green]{len(succeeded)} reordered[/green]\n")

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("CHANNEL")
    table.add_column("NEW #1 STREAM", style="cyan")
    table.add_column("PROVIDER", style="green")
    table.add_column("WAS #1 STREAM", style="dim")

    for proposal in succeeded:
        new_top_id  = proposal.proposed_stream_ids[0]
        old_top_id  = proposal.current_stream_ids[0]
        new_stream  = stream_lookup.get(new_top_id)
        old_stream  = stream_lookup.get(old_top_id)
        new_name    = new_stream.name     if new_stream else str(new_top_id)
        new_prov    = new_stream.provider if new_stream else "—"
        old_name    = old_stream.name     if old_stream else str(old_top_id)
        # Only show "was" if it actually changed
        was_col     = old_name if old_top_id != new_top_id else "[dim]unchanged[/dim]"
        table.add_row(proposal.channel.name, new_name, new_prov or "—", was_col)

    _console.print(table)


def print_cleanup_summary(
    initial_count: int,
    groups: list,
    proposals: list,
    applied: bool,
    reorder_count: int = 0,
    provider_priority_configured: bool = True,
) -> None:
    """Single end-of-run summary for the --cleanup path."""
    dupes_removed = sum(len(g.duplicates) for g in groups)
    after_dedup   = initial_count - dupes_removed
    renames       = len(proposals)
    verb          = "" if applied else " [dim](dry-run)[/dim]"

    _console.print()
    _console.rule("[bold]Cleanup Summary[/bold]")
    _console.print(f"  Channels at start :  [bold]{initial_count}[/bold]")
    if groups:
        _console.print(
            f"  Duplicate groups  :  [bold]{len(groups)}[/bold]"
            f"  [dim]({dupes_removed} channel(s) merged away)[/dim]"
        )
        _console.print(f"  After dedup       :  [bold]{after_dedup}[/bold]")
    else:
        _console.print("  Duplicate groups  :  [dim]none[/dim]")
    if renames:
        _console.print(f"  Renames           :  [bold]{renames}[/bold]{verb}")
    else:
        _console.print("  Renames           :  [dim]none needed[/dim]")
    if provider_priority_configured:
        if reorder_count:
            _console.print(f"  Stream ordering   :  [bold]{reorder_count}[/bold] channel(s){verb}")
        else:
            _console.print("  Stream ordering   :  [dim]already optimal[/dim]")
    else:
        _console.print(
            "  Stream ordering   :  [dim]skipped — add [bold]provider_priority[/bold]"
            " to config.yaml to enable automatic stream quality sorting[/dim]"
        )
    _console.rule()


def print_epg_proposals(
    proposals: list,
    already_assigned: int,
    total: int,
    source_names: dict[int, str] | None = None,
    min_confidence: float = 0.0,
    hidden_count: int = 0,
) -> None:
    """Display EPG assignment proposals from --assign-epg."""
    unassigned = total - already_assigned
    _console.print(
        f"\nEPG assignments:  "
        f"[bold]{len(proposals)}[/bold] proposals  ·  "
        f"[dim]{already_assigned} already assigned  ·  "
        f"{unassigned - len(proposals) - hidden_count} no match found[/dim]"
        + (f"  ·  [dim]{hidden_count} below {min_confidence:.0%} threshold[/dim]" if hidden_count else "")
    )
    if not proposals:
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("CHANNEL")
    table.add_column("EPG NAME", style="cyan")
    table.add_column("TVG ID")
    table.add_column("SOURCE", style="dim")
    table.add_column("CONF")
    table.add_column("METHOD", style="dim")

    for p in proposals:
        conf = p.confidence
        if conf >= 0.85:
            conf_str = f"[green]{conf:.0%}[/green]"
        elif conf >= 0.65:
            conf_str = f"[yellow]{conf:.0%}[/yellow]"
        else:
            conf_str = f"[red]{conf:.0%}[/red]"
        src_name = (source_names or {}).get(p.epg_entry.epg_source, str(p.epg_entry.epg_source))
        table.add_row(
            p.channel.name,
            p.epg_entry.name,
            p.epg_entry.tvg_id,
            src_name,
            Text.from_markup(conf_str),
            p.method,
        )

    _console.print(table)


def print_epg_apply_result(succeeded: list, failed: list) -> None:
    """Print outcome after --assign-epg --apply."""
    if succeeded:
        _console.print(f"  [green]{len(succeeded)} EPG assignments written[/green]")
    if failed:
        for channel_name, error in failed:
            _console.print(f"  [red]FAILED[/red] {channel_name!r} — {error}")
    if not succeeded and not failed:
        _console.print("  [dim]nothing to assign[/dim]")


def print_audit_report(report: "AuditReport", channel_count: int = 0, group_count: int = 0, group_label: str | None = None) -> None:
    """Print four Rich tables — one per audit category — then a summary line."""
    from core.models import AuditReport  # avoid circular at module level

    scope = f" ({group_label})" if group_label else ""
    counts = f"{channel_count} channel(s) across {group_count} group(s)"

    def _section(title: str, color: str, rows: list, col1: str, col2: str, get_row) -> None:
        table = Table(
            title=f"{title}{scope}",
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold",
            title_style=f"bold {color}",
            padding=(0, 1),
        )
        table.add_column(col1)
        table.add_column(col2, justify="right", width=8)
        for item in rows:
            c1, c2 = get_row(item)
            table.add_row(c1, c2)
        _console.print(table)

    if report.no_epg:
        _section(
            f"Channels without EPG  ({len(report.no_epg)})", "yellow",
            report.no_epg, "Channel", "ID",
            lambda ch: (ch.name, str(ch.id)),
        )

    if report.no_streams:
        _section(
            f"Channels without streams  ({len(report.no_streams)})", "red",
            report.no_streams, "Channel", "ID",
            lambda ch: (ch.name, str(ch.id)),
        )

    if report.orphan_streams:
        _section(
            f"Orphan streams  ({len(report.orphan_streams)})", "magenta",
            report.orphan_streams, "Stream", "ID",
            lambda s: (s.name, str(s.id)),
        )

    if report.stale_epg:
        _section(
            f"Stale EPG references  ({len(report.stale_epg)})", "red",
            report.stale_epg, "Channel", "EPG ID",
            lambda ch: (ch.name, str(ch.epg_data_id)),
        )

    no_epg_color     = "yellow"  if report.no_epg         else "green"
    no_streams_color = "red"     if report.no_streams     else "green"
    orphans_color    = "magenta" if report.orphan_streams else "green"
    stale_color      = "red"     if report.stale_epg      else "green"

    _console.print(f"\n[bold]Audit complete{scope}[/bold]")
    _console.print(f"  Channels scanned:          {channel_count}")
    _console.print(f"  Groups scanned:            {group_count}")
    _console.print(f"  [{no_epg_color}]Channels without EPG:      {len(report.no_epg)}[/{no_epg_color}]")
    _console.print(f"  [{no_streams_color}]Channels without streams:  {len(report.no_streams)}[/{no_streams_color}]")
    _console.print(f"  [{orphans_color}]Orphan streams:            {len(report.orphan_streams)}[/{orphans_color}]")
    _console.print(f"  [{stale_color}]Channels with stale EPG:   {len(report.stale_epg)}[/{stale_color}]")


def print_error(message: str) -> None:
    _console.print(f"[red]Error:[/red] {message}")


def print_info(message: str) -> None:
    _console.print(message)


def status(message: str):
    """Return a Rich spinner context manager for long-running fetches.

    Usage::
        with console.status("Fetching channels..."):
            channels = _fetch_channels(client)
    The spinner is transient — it disappears once the block exits.
    """
    return _console.status(message)


# ──────────────────────────────────────────────── internal

def _print_summary(changeset: ChangeSet) -> None:
    parts: list[str] = []
    if changeset.creates:
        parts.append(f"[cyan]{len(changeset.creates)} to create[/cyan]")
    if changeset.updates:
        parts.append(f"[green]{len(changeset.updates)} to update[/green]")
    if changeset.deletes:
        parts.append(f"[red]{len(changeset.deletes)} to delete[/red]")
    other_skips = [s for s in changeset.skips
                   if s not in changeset.already_correct]
    if other_skips:
        parts.append(f"[dim]{len(other_skips)} skipped[/dim]")
    if changeset.already_correct:
        parts.append(f"[dim]{len(changeset.already_correct)} already correct[/dim]")

    if parts:
        _console.print("  " + "  ·  ".join(parts))
    else:
        _console.print("[dim]Nothing to do.[/dim]")
