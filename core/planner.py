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

    # Build attachment index: normalized_stream_name → channel, derived from
    # streams already attached to each channel in Dispatcharr.
    # This is the primary match signal — more reliable than channel name comparison.
    attachment_index = _build_attachment_index(streams, channels, config.matching.normalizer)

    # Step 1 + 2: match streams, group by channel
    matches: list[StreamMatch] = []
    for stream in streams:
        match = _match_stream(stream, channels, config, strategy, pairing_store, attachment_index)
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


def _build_attachment_index(
    streams: list[Stream],
    channels: list[Channel],
    normalizer_mode: str,
) -> dict[str, Channel]:
    """Build a map of normalized_stream_name → channel from currently attached streams.

    For every channel, resolve its stream_ids to Stream objects and normalize
    each stream name. Any new stream whose normalized name appears in this index
    belongs to that channel — regardless of what the channel itself is named.

    Sanity guard: a stream is only added to the index if its normalized name
    shares at least one meaningful token (length ≥ 2, non-numeric) with the
    channel's own normalized name. This prevents a mis-assigned stream from a
    previous bad run from poisoning the index and pulling unrelated streams onto
    the wrong channel.
    """
    from core import normalizer as norm

    stream_by_id = {s.id: s for s in streams}
    index: dict[str, Channel] = {}

    for channel in channels:
        channel_normalized = norm.normalize(channel.name, normalizer_mode).lower()
        channel_tokens = _meaningful_tokens(channel_normalized)

        for stream_id in channel.stream_ids:
            attached = stream_by_id.get(stream_id)
            if not attached:
                continue
            stream_normalized = norm.normalize(attached.name, normalizer_mode)
            if not stream_normalized:
                continue
            stream_tokens = _meaningful_tokens(stream_normalized.lower())

            # Reject streams with no token overlap with the channel name —
            # they were most likely mis-assigned in a previous run.
            if stream_tokens & channel_tokens:
                index[stream_normalized] = channel

    return index


def _meaningful_tokens(text: str) -> set[str]:
    """Return the set of tokens that are at least 2 chars long and not purely numeric.

    Filters out single characters and bare numbers (e.g. "7", "1") that would
    create false-positive token overlaps between unrelated channel names.
    """
    return {t for t in text.split() if len(t) >= 2 and not t.isdigit()}


def _match_stream(
    stream: Stream,
    channels: list[Channel],
    config: Config,
    strategy: MatchStrategy,
    pairing_store,
    attachment_index: dict[str, Channel],
) -> StreamMatch:
    """Match a stream to a channel using three lookups in priority order:

    1. Pairing store  — user-confirmed pairings always win.
    2. Attachment index — if the stream name already exists on a channel, use that.
    3. Name strategy  — fall back to normalized name comparison (regex/exact/fuzzy).
    """
    from core import normalizer as norm

    normalized = norm.normalize(stream.name, config.matching.normalizer)

    # 1. Pairing store
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

    # 2. Attachment index
    if normalized in attachment_index:
        channel = attachment_index[normalized]
        return StreamMatch(
            stream=stream,
            channel=channel,
            match_type=MatchType.ATTACHMENT,
            score=1.0,
            normalized_stream_name=normalized,
            normalized_channel_name=norm.normalize(
                channel.name, config.matching.normalizer
            ),
        )

    # 3. Name-based strategy
    return strategy.find_match(stream, channels)
