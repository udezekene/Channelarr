"""Channelarr — entry point.

Wires all modules together and runs the pipeline:
    load config → load pairings → authenticate → fetch → plan
    → filter (lock → blocklist → allowlist) → diff
    → [interactive] → [pairing wizard] → [apply] → log

Usage
-----
    python3 channelarr.py                               # dry-run
    python3 channelarr.py --apply                       # commit changes
    python3 channelarr.py --apply --allow-new-channels  # also permit creation
    python3 channelarr.py -i --apply                    # interactive approval then apply
    python3 channelarr.py --pair                        # review + confirm pairings
    python3 channelarr.py --unlock "BBC One" --apply    # one-run unlock
"""

import signal
import sys
import time

from utils import cli_args
from config import loader, wizard
from config.loader import load as load_config
from api.client import APIClient
from api import endpoints
from core.models import Stream, Channel
from core import planner, executor
from matching.regex_match import RegexMatchStrategy
from matching.exact import ExactMatchStrategy
from matching.fuzzy import FuzzyMatchStrategy
from priority import resolver as priority_resolver
from pairings.store import PairingStore
from filters import lock as lock_filter
from filters import blocklist as blocklist_filter
from filters import allowlist as allowlist_filter
from ui.pairing_wizard import run as run_wizard, has_pending
from ui import console
from ui import interactive
from logging_ import run_logger, history as run_history
from dedup import finder as dedup_finder
from dedup.merger import apply_dedup
from cleanup.renamer import find_renames, apply_renames
from cleanup.stream_sorter import find_reorders, apply_reorders
from epg import matcher as epg_matcher
from audit.checker import run_audit


def _build_strategy(config, strategy_override: str | None = None):
    """Instantiate the correct matching strategy from config (or a CLI override)."""
    name = strategy_override or config.matching.strategy
    mode = config.matching.normalizer
    scope = config.matching.scope_to_group

    match name:
        case "exact":
            return ExactMatchStrategy(scope_to_group=scope)
        case "fuzzy":
            return FuzzyMatchStrategy(
                normalizer_mode=mode,
                scope_to_group=scope,
                threshold=config.matching.fuzzy_threshold,
            )
        case _:  # "regex" or any unknown value
            return RegexMatchStrategy(normalizer_mode=mode, scope_to_group=scope)


def _graceful_exit(signum, frame):
    console.print_info("\nOperation cancelled. Exiting.")
    sys.exit(0)


def _fetch_m3u_accounts(client: APIClient) -> dict[int, str]:
    """Return a mapping of M3U account ID → account name."""
    try:
        data = client.get(endpoints.M3U_ACCOUNTS)
        raw_list = data["results"] if isinstance(data, dict) and "results" in data else data
        if isinstance(raw_list, list):
            return {a["id"]: a["name"] for a in raw_list if "id" in a and "name" in a}
    except Exception:
        pass
    return {}


def _fetch_streams(client: APIClient, refresh: bool) -> list[Stream]:
    if refresh:
        console.print_info("Triggering M3U refresh...")
        client.post(endpoints.M3U_REFRESH)
        time.sleep(10)
        console.print_info("Refresh complete.")

    account_names = _fetch_m3u_accounts(client)

    raw_list, total = client.get_all_pages(endpoints.STREAMS, params={"page_size": 2500})
    if total and len(raw_list) < total:
        console.print_info(f"  [yellow]Warning: fetched {len(raw_list)} of {total} streams — some may be missing.[/yellow]")

    return [
        Stream(
            id=s["id"],
            name=s["name"],
            provider=account_names.get(s["m3u_account"]) if s.get("m3u_account") is not None else None,
            channel_group=s.get("channel_group"),
            raw=s,
        )
        for s in raw_list
        if isinstance(s, dict) and "id" in s and "name" in s
    ]


def _fetch_channel_groups(client: APIClient) -> dict[str, int]:
    """Return a name→id map of channel groups from the Dispatcharr API.

    Tries several known endpoint patterns; returns empty dict if none respond.
    """
    candidates = [
        "/api/channels/channelgroups/",
        "/api/channels/groups/",
        "/api/channels/channel-groups/",
    ]
    for path in candidates:
        try:
            data = client.get(path, params={"page_size": 200})
            raw = data.get("results", data) if isinstance(data, dict) else data
            if isinstance(raw, list) and raw:
                return {
                    g["name"]: g["id"]
                    for g in raw
                    if isinstance(g, dict) and "id" in g and "name" in g
                }
        except Exception:
            continue
    return {}


def _apply_group_filter(channels: list[Channel], args, client: "APIClient | None" = None) -> list[Channel]:
    """Filter channels to a single group if --group or --group-id was passed.

    For --group NAME, fetches group names from the API.
    For --group-id, filters directly by id without an API call.
    Returns channels unchanged if neither flag was set.
    """
    group_id: int | None = getattr(args, "group_id", None)
    group_name: str | None = getattr(args, "group", None)

    if not group_id and not group_name:
        return channels

    if group_id:
        filtered = [ch for ch in channels if ch.channel_group_id == group_id]
        console.print_info(f"  Scoped to group id={group_id}: {len(filtered)} channel(s).")
        return filtered

    # --group NAME: fetch names from the API
    name_to_id = _fetch_channel_groups(client) if client else {}

    for gname, gid in name_to_id.items():
        if gname.lower() == group_name.lower():
            filtered = [ch for ch in channels if ch.channel_group_id == gid]
            console.print_info(f"  Scoped to group {gname!r}: {len(filtered)} channel(s).")
            return filtered

    # Build a hint from what IDs are actually present in the channel data
    present_ids = sorted({ch.channel_group_id for ch in channels if ch.channel_group_id is not None})
    if name_to_id:
        names = ", ".join(f"{n!r} (id={i})" for n, i in sorted(name_to_id.items(), key=lambda x: x[0]))
        console.print_error(f"Unknown group {group_name!r}. Available groups: {names}")
    else:
        ids_hint = ", ".join(f"--group-id {i}" for i in present_ids[:10])
        console.print_error(
            f"Unknown group {group_name!r}. Could not fetch group names from the API.\n"
            f"  Use --group-id instead. Group IDs present in your channels: {ids_hint}"
        )
    sys.exit(1)


def _fetch_channels(client: APIClient) -> list[Channel]:
    raw_list, total = client.get_all_pages(endpoints.CHANNELS, params={"page_size": 2500})
    if total and len(raw_list) < total:
        console.print_info(f"  [yellow]Warning: fetched {len(raw_list)} of {total} channels — some may be missing.[/yellow]")

    return [
        Channel(
            id=c["id"],
            name=c["name"],
            stream_ids=[
                s if isinstance(s, int) else s.get("id")
                for s in c.get("streams", [])
                if isinstance(s, (int, dict))
            ],
            channel_group_id=c.get("channel_group_id"),
            epg_data_id=c.get("epg_data_id"),
            tvg_id=c.get("tvg_id") or None,
            raw=c,
        )
        for c in raw_list
        if isinstance(c, dict) and "id" in c and "name" in c
    ]


def main() -> None:
    signal.signal(signal.SIGINT, _graceful_exit)
    signal.signal(signal.SIGTERM, _graceful_exit)

    args = cli_args.parse_args()

    # ── config ──────────────────────────────────────────────────────────────
    if args.reconfigure:
        config = wizard.run(args.config)
    else:
        try:
            config = loader.load(args.config)
        except FileNotFoundError:
            console.print_info("No config found. Running setup wizard...")
            config = wizard.run(args.config)

    # CLI flags override config defaults for this run only — never persisted
    if args.allow_new_channels:
        config.allow_new_channels_default = True
    if args.allow_delete:
        config.allow_delete_default = True

    # ── pairing store ────────────────────────────────────────────────────────
    pairing_store = PairingStore()
    pairing_store.load()

    # ── client + auth ────────────────────────────────────────────────────────
    client = APIClient(config.endpoint, config.username, config.password)
    try:
        client.authenticate()
    except Exception as e:
        console.print_error(f"Authentication failed: {e}")
        sys.exit(1)

    # ── debug-channel: show sort keys for a channel's streams ────────────────
    if args.debug_channel:
        from cleanup.stream_sorter import stream_quality_tier
        search = args.debug_channel.lower()
        all_streams = _fetch_streams(client, False)
        all_channels = _fetch_channels(client)
        stream_lookup = {s.id: s for s in all_streams}
        priority_map = {name.lower(): i for i, name in enumerate(config.provider_priority)}
        unlisted_rank = len(priority_map)

        matches = [c for c in all_channels if search in c.name.lower()]
        if not matches:
            console.print_error(f"No channel found matching {args.debug_channel!r}")
            return
        for channel in matches[:3]:
            console.print_info(f"\n[bold]{channel.name}[/bold]  (id={channel.id}, {len(channel.stream_ids)} streams)")
            console.print_info(f"  {'SID':<8} {'TIER':<6} {'PROV_RANK':<10} {'PROVIDER':<12} STREAM NAME")
            for sid in channel.stream_ids:
                s = stream_lookup.get(sid)
                if s is None:
                    console.print_info(f"  {sid:<8} {'?':<6} {'?':<10} {'NOT FOUND':<12} —")
                    continue
                tier = stream_quality_tier(s.name)
                rank = priority_map.get((s.provider or '').lower(), unlisted_rank)
                console.print_info(f"  {sid:<8} {tier:<6} {rank:<10} {(s.provider or '—'):<12} {s.name}")
        return

    # ── inspect-epg: probe EPG API shape and dump sample entries ─────────────
    if args.inspect_epg:
        import json
        # First get the EPG root to find sub-endpoints
        root = client.get("/api/epg/")
        console.print_info(f"EPG root: {json.dumps(root, indent=2, default=str)}")
        # Probe each sub-endpoint listed in the root
        if isinstance(root, dict):
            for key, url in root.items():
                if not isinstance(url, str) or not url.startswith("http"):
                    continue
                # Convert absolute URL to path
                from urllib.parse import urlparse
                path = urlparse(url).path
                try:
                    data = client.get(path, params={"page_size": 3})
                    count = data.get("count", "?") if isinstance(data, dict) else len(data) if isinstance(data, list) else "?"
                    console.print_info(f"\n[green]✓ {path}[/green]  (total={count})")
                    raw = data.get("results", data) if isinstance(data, dict) else data
                    entries = raw[:3] if isinstance(raw, list) else [raw]
                    for entry in entries:
                        console.print_info(json.dumps(entry, indent=2, default=str))
                except Exception as e:
                    console.print_info(f"  [dim]{path}  → {e}[/dim]")
        return

    # ── inspect-channel: find channel by name and dump raw API response ───────
    if args.inspect_channel:
        import json
        search = args.inspect_channel.lower()
        all_channels = client.get(endpoints.CHANNELS, params={"page_size": 2500})
        raw_list = all_channels["results"] if isinstance(all_channels, dict) and "results" in all_channels else all_channels
        matches = [c for c in (raw_list or []) if search in c.get("name", "").lower()]
        if not matches:
            console.print_error(f"No channel found matching {args.inspect_channel!r}")
            return
        for c in matches[:3]:  # show up to 3 matches
            console.print_info(f"\n--- channel id={c['id']}  name={c['name']!r}  channel_number={c.get('channel_number')} ---")
            console.print_info(json.dumps(c, indent=2, default=str))
        return

    # ── inspect-streams: dump raw API fields for a sample and exit ───────────
    if args.inspect_streams:
        import json

        # Try to resolve m3u_account IDs → names
        account_names: dict[int, str] = {}
        for candidate in ("/api/m3u/accounts/", "/api/m3u/m3uaccounts/"):
            try:
                acc_data = client.get(candidate)
                acc_list = acc_data["results"] if isinstance(acc_data, dict) and "results" in acc_data else acc_data
                if isinstance(acc_list, list) and acc_list:
                    account_names = {a["id"]: a.get("name", str(a["id"])) for a in acc_list if "id" in a}
                    console.print_info(f"M3U accounts ({candidate}):")
                    for aid, aname in account_names.items():
                        console.print_info(f"  id={aid}  name={aname!r}")
                    break
            except Exception:
                pass
        if not account_names:
            console.print_info("[dim]Could not resolve M3U account names — showing raw IDs.[/dim]")

        console.print_info(f"\nFetching {args.inspect_count} stream(s) for inspection...")
        data = client.get(endpoints.STREAMS, params={"page_size": args.inspect_count})
        raw_list = data["results"] if isinstance(data, dict) and "results" in data else data
        for s in (raw_list or [])[:args.inspect_count]:
            acc_id   = s.get("m3u_account")
            acc_name = account_names.get(acc_id, "unknown") if acc_id is not None else "none"
            console.print_info(f"\n--- stream id={s.get('id')}  name={s.get('name')!r}  m3u_account={acc_id} ({acc_name!r}) ---")
            console.print_info(json.dumps(s, indent=2, default=str))
        return

    # ── audit: read-only health scan ──────────────────────────────────────────
    if args.audit:
        from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

        try:
            with console.status("Fetching channels..."):
                channels = _fetch_channels(client)
        except Exception as e:
            console.print_error(f"Failed to fetch channels: {e}")
            sys.exit(1)
        console.print_info(f"  {len(channels)} channels found.")
        channels = _apply_group_filter(channels, args, client)

        try:
            with console.status("Fetching streams..."):
                streams = _fetch_streams(client, False)
        except Exception as e:
            console.print_error(f"Failed to fetch streams: {e}")
            sys.exit(1)

        epg_entries: list = []
        try:
            with console.status("Fetching EPG data (needed for stale-ref check)..."):
                epg_entries = epg_matcher.fetch_epg_entries(client)
        except Exception as e:
            console.print_error(f"Failed to fetch EPG data: {e}")
            sys.exit(1)

        report = run_audit(channels, streams, epg_entries)
        group_label = None
        if getattr(args, "group", None):
            group_label = f"group {args.group!r}"
        elif getattr(args, "group_id", None):
            group_label = f"group id={args.group_id}"
        group_count = len({ch.channel_group_id for ch in channels if ch.channel_group_id is not None})
        console.print_audit_report(
            report,
            channel_count=len(channels),
            group_count=group_count,
            group_label=group_label,
        )
        return

    # ── assign-epg: auto-assign EPG to channels that have none ────────────────
    if args.assign_epg:
        from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

        try:
            with console.status("Fetching channels..."):
                channels = _fetch_channels(client)
        except Exception as e:
            console.print_error(f"Failed to fetch channels: {e}")
            sys.exit(1)
        console.print_info(f"  {len(channels)} channels found.")
        channels = _apply_group_filter(channels, args, client)

        try:
            with console.status("Fetching streams..."):
                streams = _fetch_streams(client, False)
        except Exception as e:
            console.print_error(f"Failed to fetch streams: {e}")
            sys.exit(1)
        stream_lookup = {s.id: s for s in streams}

        with console.status("Fetching EPG sources..."):
            sources = epg_matcher.fetch_epg_sources(client)
        provider_names = list({s.provider for s in streams if s.provider})
        provider_source_map = epg_matcher.build_provider_source_map(sources, provider_names)
        console.print_info(f"  {len(sources)} source(s): " + ", ".join(
            f"{s['name']} ({s.get('epg_data_count', '?')} entries)" for s in sources
            if isinstance(s, dict)
        ))

        epg_entries: list = []
        total_epg = sum(
            s.get("epg_data_count", 0) for s in sources
            if isinstance(s, dict)
        ) or None
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                transient=True,
            ) as progress:
                task = progress.add_task("Fetching EPG data...", total=total_epg)
                for batch, reported_total in epg_matcher.iter_epg_entries(client):
                    epg_entries.extend(batch)
                    if reported_total:
                        progress.update(task, total=reported_total)
                    progress.update(task, completed=len(epg_entries))
        except Exception as e:
            console.print_error(f"Failed to fetch EPG data: {e}")
            sys.exit(1)
        console.print_info(f"  {len(epg_entries)} EPG entries loaded.")

        unassigned_count = sum(1 for ch in channels if not ch.epg_data_id)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("Matching channels...", total=unassigned_count)
            proposals, already_assigned = epg_matcher.find_proposals(
                channels,
                stream_lookup,
                epg_entries,
                provider_source_map,
                progress_callback=lambda n: progress.advance(task, n),
            )

        # Confidence threshold: CLI flag overrides config, config overrides default (0.0)
        min_conf = args.epg_min_confidence if args.epg_min_confidence is not None else config.epg_min_confidence
        source_names = {s["id"]: s["name"] for s in sources if isinstance(s, dict)}
        all_proposals = proposals
        proposals = [p for p in all_proposals if p.confidence >= min_conf] if min_conf > 0 else all_proposals
        hidden = len(all_proposals) - len(proposals)

        console.print_epg_proposals(
            proposals, already_assigned, len(channels),
            source_names=source_names,
            min_confidence=min_conf,
            hidden_count=hidden,
        )

        if proposals and args.apply:
            console.print_info("\nWriting EPG assignments...")
            succeeded = []
            failed = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                transient=True,
            ) as progress:
                task = progress.add_task("Writing...", total=len(proposals))
                for p in proposals:
                    try:
                        payload = {
                            **p.channel.raw,
                            "epg_data_id": p.epg_entry.id,
                            "tvg_id": p.epg_entry.tvg_id,
                        }
                        client.put(f"{endpoints.CHANNELS}{p.channel.id}/", json=payload)
                        succeeded.append(p)
                    except Exception as exc:
                        failed.append((p.channel.name, str(exc)))
                    progress.advance(task)
            console.print_epg_apply_result(succeeded, failed)
        elif proposals:
            console.print_info("[dim]Dry-run. Pass --apply to write these assignments.[/dim]")
        return

    # ── fetch ─────────────────────────────────────────────────────────────────
    try:
        with console.status("Fetching streams..."):
            streams = _fetch_streams(client, args.refresh)
    except Exception as e:
        console.print_error(f"Failed to fetch streams: {e}")
        sys.exit(1)
    console.print_info(f"  {len(streams)} streams found.")

    try:
        with console.status("Fetching channels..."):
            channels = _fetch_channels(client)
    except Exception as e:
        console.print_error(f"Failed to fetch channels: {e}")
        sys.exit(1)
    console.print_info(f"  {len(channels)} channels found.")
    channels = _apply_group_filter(channels, args, client)

    # ── cleanup path: merge duplicates within each group, then rename ─────────
    if args.cleanup:
        initial_count = len(channels)

        # Step 1: dedup (skip if --rename-only)
        if not args.rename_only:
            groups = dedup_finder.find_groups(channels, "aggressive")
            console.print_dedup_groups(groups)

            if groups and args.apply:
                console.print_info("\nMerging duplicates...")
                dedup_result = apply_dedup(groups, client)
                console.print_dedup_result(len(dedup_result.merged), len(dedup_result.failed))
                for group, error in dedup_result.failed:
                    console.print_error(f"{group.normalized_name!r} — {error}")

                # Re-fetch so rename step works on current state
                if dedup_result.merged:
                    try:
                        with console.status("Refreshing channel list..."):
                            channels = _fetch_channels(client)
                    except Exception as e:
                        console.print_error(f"Failed to refresh channels: {e}")
                        return
            elif groups:
                console.print_info(
                    "[dim]Dry-run. Pass --apply to merge these groups.[/dim]\n"
                )

        # Step 2: rename
        proposals = find_renames(channels)
        console.print_rename_proposals(proposals)

        if proposals and args.apply:
            console.print_info("\nRenaming channels...")
            succeeded, failed = apply_renames(proposals, client)
            console.print_rename_result(len(succeeded), len(failed))
            for proposal, error in failed:
                console.print_error(f"{proposal.current_name!r} — {error}")
        elif proposals:
            console.print_info(
                "[dim]Dry-run. Pass --apply to apply all changes.[/dim]"
            )

        # Step 3: sort streams by (quality tier, provider rank)
        reorder_count = 0
        if config.provider_priority:
            stream_lookup = {s.id: s for s in streams}
            reorder_stats = find_reorders(channels, stream_lookup, config.provider_priority)
            console.print_stream_reorder_proposals(reorder_stats, stream_lookup, verbose=args.verbose)

            if reorder_stats.proposals and args.apply:
                console.print_info("\nReordering streams...")
                succeeded, failed = apply_reorders(reorder_stats.proposals, client)
                console.print_stream_reorder_result(succeeded, failed, stream_lookup)
                reorder_count = len(succeeded)
            elif reorder_stats.proposals:
                console.print_info(
                    "[dim]Dry-run. Pass --apply to apply reordering.[/dim]"
                )
                reorder_count = len(reorder_stats.proposals)

        console.print_cleanup_summary(
            initial_count=initial_count,
            groups=groups if not args.rename_only else [],
            proposals=proposals,
            applied=args.apply,
            reorder_count=reorder_count,
            provider_priority_configured=bool(config.provider_priority),
        )
        return

    # ── strategy + resolver ───────────────────────────────────────────────────
    strategy = _build_strategy(config, strategy_override=args.strategy)

    # ── plan ──────────────────────────────────────────────────────────────────
    changeset = planner.plan(
        streams, channels, config, strategy,
        resolver=priority_resolver,
        pairing_store=pairing_store,
    )

    # ── filter pipeline: lock → blocklist → allowlist ─────────────────────────
    locked_names = [lock.channel_name for lock in config.locks]
    changeset = lock_filter.apply(
        changeset,
        locked_names=locked_names,
        unlocked_names=args.unlock,
        pairing_store=pairing_store,
    )
    changeset = blocklist_filter.apply(changeset, config.blocklist)
    changeset = allowlist_filter.apply(changeset, config.allowlist)

    # ── diff output ───────────────────────────────────────────────────────────
    if args.quiet:
        console.print_summary(changeset)
    else:
        console.print_diff(changeset, verbose=args.verbose)

    # ── interactive mode ──────────────────────────────────────────────────────
    if args.interactive:
        changeset = interactive.run(changeset)
        if not args.quiet:
            console.print_info("[bold]After review:[/bold]")
            console.print_summary(changeset)

    # ── pairing wizard ────────────────────────────────────────────────────────
    if args.pair or (not args.apply and has_pending(changeset)):
        run_wizard(changeset, pairing_store)

    # ── apply (executor is only ever called here) ─────────────────────────────
    if args.apply:
        console.print_info("\nApplying changes...")
        result = executor.apply(changeset, client)
        console.print_apply_result(
            applied=len(result.actually_applied),
            skipped=len(result.skipped),
            failed=len(result.failed),
        )

        if result.failed:
            for applied in result.failed:
                name = (
                    applied.change.stream.name if applied.change.stream
                    else applied.change.channel.name if applied.change.channel
                    else "unknown"
                )
                console.print_error(f"FAILED: {name!r} — {applied.error}")

        run_history.append(run_logger.build_entry(changeset, result, dry_run=False))
    else:
        console.print_info("\n[dim]Dry-run complete. Pass --apply to commit these changes.[/dim]")
        run_history.append(run_logger.build_entry(changeset, None, dry_run=True))


if __name__ == "__main__":
    main()
