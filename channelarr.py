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


def _fetch_streams(client: APIClient, refresh: bool) -> list[Stream]:
    if refresh:
        console.print_info("Triggering M3U refresh...")
        client.post(endpoints.M3U_REFRESH)
        time.sleep(10)
        console.print_info("Refresh complete.")

    data = client.get(endpoints.STREAMS, params={"page_size": 2500})
    raw_list = data["results"] if isinstance(data, dict) and "results" in data else data
    if not isinstance(raw_list, list):
        raw_list = []

    return [
        Stream(
            id=s["id"],
            name=s["name"],
            provider=s.get("m3u_account"),
            channel_group=s.get("channel_group"),
            raw=s,
        )
        for s in raw_list
        if isinstance(s, dict) and "id" in s and "name" in s
    ]


def _fetch_channels(client: APIClient) -> list[Channel]:
    data = client.get(endpoints.CHANNELS, params={"page_size": 2500})
    raw_list = data["results"] if isinstance(data, dict) and "results" in data else data
    if not isinstance(raw_list, list):
        raw_list = []

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

    # ── fetch ─────────────────────────────────────────────────────────────────
    console.print_info("Fetching streams...")
    try:
        streams = _fetch_streams(client, args.refresh)
    except Exception as e:
        console.print_error(f"Failed to fetch streams: {e}")
        sys.exit(1)
    console.print_info(f"  {len(streams)} streams found.")

    console.print_info("Fetching channels...")
    try:
        channels = _fetch_channels(client)
    except Exception as e:
        console.print_error(f"Failed to fetch channels: {e}")
        sys.exit(1)
    console.print_info(f"  {len(channels)} channels found.")

    # ── cleanup path: propose channel renames ─────────────────────────────────
    if args.cleanup:
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
                "[dim]Dry-run. Pass --apply to rename these channels.[/dim]"
            )
        return

    # ── dedup path (separate from stream-matching pipeline) ───────────────────
    if args.dedup:
        groups = dedup_finder.find_groups(channels, config.matching.normalizer)
        console.print_dedup_groups(groups)

        if groups and args.apply:
            console.print_info("\nMerging duplicates...")
            result = apply_dedup(groups, client)
            console.print_dedup_result(len(result.merged), len(result.failed))
            for group, error in result.failed:
                console.print_error(f"{group.normalized_name!r} — {error}")
        elif groups:
            console.print_info(
                "[dim]Dry-run. Pass --apply to merge these groups.[/dim]"
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
