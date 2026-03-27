"""Pure planning function: streams + channels + config → ChangeSet.

Zero side effects. No API calls, no file I/O, no console output.
All decisions about what to change live here — nothing else makes these decisions.

The executor is never called from here. Dry-run is trivially achieved by
simply not calling the executor after calling this function.
"""

from __future__ import annotations
from collections import defaultdict
from datetime import date
from typing import Optional

from core.models import (
    ChangeSet,
    ChannelChange,
    ChangeType,
    MatchType,
    SkipReason,
    StreamMatch,
    Stream,
    Channel,
)
from config.schema import Config
from matching.base import MatchStrategy


def plan(
    streams: list[Stream],
    channels: list[Channel],
    config: Config,
    strategy: MatchStrategy,
    resolver=None,
    pairing_store=None,
) -> ChangeSet:
    """Match every stream to a channel and return a ChangeSet.

    Steps
    -----
    1. For each stream, check the pairing store first; fall through to strategy.
    2. Group StreamMatch results by matched channel (or by normalized name for new).
    3. Use the resolver (if provided) to pick the winning_match within each group.
    4. Decide ChangeType: UPDATE / CREATE / SKIP(CREATE_NOT_PERMITTED).
    5. Second pass over channels: any channel with no matching stream →
       DELETE or SKIP(DELETE_NOT_PERMITTED).
    """
    channel_by_id = {c.id: c for c in channels}

    # Step 1 + 2: match streams, group by channel
    matches: list[StreamMatch] = []
    for stream in streams:
        match = _match_stream(stream, channels, config, strategy, pairing_store)
        matches.append(match)

    groups: dict[str, list[StreamMatch]] = defaultdict(list)
    for m in matches:
        key = str(m.channel.id) if m.channel else f"new::{m.normalized_stream_name}"
        groups[key].append(m)

    allow_create = config.allow_new_channels_default
    changes: list[ChannelChange] = []
    matched_channel_ids: set[int] = set()

    # Step 3 + 4: one ChannelChange per group
    for key, group_matches in groups.items():
        is_new = key.startswith("new::")
        winning = resolver.resolve(group_matches, config) if resolver else group_matches[0]

        if is_new:
            change_type = ChangeType.CREATE if allow_create else ChangeType.SKIP
            skip_reason = None if allow_create else SkipReason.CREATE_NOT_PERMITTED
            skip_detail = None if allow_create else "Pass --allow-new-channels to permit channel creation."
            changes.append(ChannelChange(
                change_type=change_type,
                stream=winning.stream,
                channel=None,
                winning_match=winning,
                candidates=group_matches,
                skip_reason=skip_reason,
                skip_detail=skip_detail,
            ))
        else:
            channel = group_matches[0].channel
            matched_channel_ids.add(channel.id)
            changes.append(ChannelChange(
                change_type=ChangeType.UPDATE,
                stream=winning.stream,
                channel=channel,
                winning_match=winning,
                candidates=group_matches,
            ))

    # Step 5: channels with no matching streams
    for channel in channels:
        if channel.id not in matched_channel_ids:
            if config.allow_delete_default:
                changes.append(ChannelChange(
                    change_type=ChangeType.DELETE,
                    stream=None,
                    channel=channel,
                    winning_match=None,
                    candidates=[],
                ))
            else:
                changes.append(ChannelChange(
                    change_type=ChangeType.SKIP,
                    stream=None,
                    channel=channel,
                    winning_match=None,
                    candidates=[],
                    skip_reason=SkipReason.DELETE_NOT_PERMITTED,
                    skip_detail="No matching streams found. Pass --allow-delete to remove.",
                ))

    return ChangeSet(changes=changes)


def _match_stream(
    stream: Stream,
    channels: list[Channel],
    config: Config,
    strategy: MatchStrategy,
    pairing_store,
) -> StreamMatch:
    """Check the pairing store first; fall through to the live strategy."""
    from core import normalizer as norm

    normalized = norm.normalize(stream.name, config.matching.normalizer)

    if pairing_store:
        saved = pairing_store.get(normalized, stream.channel_group)
        if saved:
            channel = next((c for c in channels if c.id == saved.channel_id), None)
            if channel:
                return StreamMatch(
                    stream=stream,
                    channel=channel,
                    match_type=MatchType.SAVED,
                    score=1.0,
                    normalized_stream_name=normalized,
                    normalized_channel_name=norm.normalize(
                        channel.name, config.matching.normalizer
                    ),
                )

    return strategy.find_match(stream, channels)
