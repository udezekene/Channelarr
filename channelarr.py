"""Channelarr — entry point.

Wires all modules together and runs the pipeline:
    load config → load pairings → authenticate → fetch → plan
    → filter (lock → blocklist → allowlist) → diff
    → [pairing wizard] → [apply]

Usage
-----
    python3 channelarr.py                               # dry-run
    python3 channelarr.py --apply                       # commit changes
    python3 channelarr.py --apply --allow-new-channels  # also permit creation
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
from core.differ import format_diff
from matching.regex_match import RegexMatchStrategy
from priority import resolver as priority_resolver
from pairings.store import PairingStore
from filters import lock as lock_filter
from filters import blocklist as blocklist_filter
from filters import allowlist as allowlist_filter
from ui.pairing_wizard import run as run_wizard, has_pending


def _graceful_exit(signum, frame):
    print("\nOperation cancelled. Exiting.")
    sys.exit(0)


def _fetch_streams(client: APIClient, refresh: bool) -> list[Stream]:
    if refresh:
        print("Triggering M3U refresh...")
        client.post(endpoints.M3U_REFRESH)
        time.sleep(10)
        print("Refresh complete.")

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
            print("No config found. Running setup wizard...")
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
        print(f"Authentication failed: {e}")
        sys.exit(1)

    # ── fetch ─────────────────────────────────────────────────────────────────
    print("Fetching streams...")
    try:
        streams = _fetch_streams(client, args.refresh)
    except Exception as e:
        print(f"Failed to fetch streams: {e}")
        sys.exit(1)
    print(f"  {len(streams)} streams found.")

    print("Fetching channels...")
    try:
        channels = _fetch_channels(client)
    except Exception as e:
        print(f"Failed to fetch channels: {e}")
        sys.exit(1)
    print(f"  {len(channels)} channels found.")

    # ── strategy + resolver ───────────────────────────────────────────────────
    strategy = RegexMatchStrategy(
        normalizer_mode=config.matching.normalizer,
        scope_to_group=config.matching.scope_to_group,
    )

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

    # ── diff ──────────────────────────────────────────────────────────────────
    if not args.quiet:
        print()
        print(format_diff(changeset))

    # ── pairing wizard ────────────────────────────────────────────────────────
    if args.pair or (not args.apply and has_pending(changeset)):
        run_wizard(changeset, pairing_store)

    # ── apply (executor is only ever called here) ─────────────────────────────
    if args.apply:
        print("\nApplying changes...")
        result = executor.apply(changeset, client)
        succeeded = len(result.succeeded)
        failed = len(result.failed)
        print(f"Done. {succeeded} succeeded, {failed} failed.")
        if failed:
            for applied in result.failed:
                name = (
                    applied.change.stream.name if applied.change.stream
                    else applied.change.channel.name if applied.change.channel
                    else "unknown"
                )
                print(f"  FAILED: {name!r} — {applied.error}")
    else:
        print("\nDry-run complete. Pass --apply to commit these changes.")


if __name__ == "__main__":
    main()
