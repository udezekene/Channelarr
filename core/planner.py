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
) -> dict[str, list[tuple[Channel, frozenset]]]:
    """Build a map of normalized_stream_name → [(channel, attached_groups), ...].

    For every channel, resolve its stream_ids to Stream objects, normalize each
    stream name, and record which channel_group IDs those attached streams belong to.

    A new stream matches a channel via this index when:
      - Its normalized name appears as a key, AND
      - Its channel_group is compatible with the channel's attached_groups
        (checked in _match_stream using group_regions config).

    Multiple channels can legitimately share the same normalized key if they
    serve different regions (e.g. MY|CNN and UK|CNN both normalize to "CNN").

    Sanity guard: entries with no token overlap between the stream name and the
    channel name are rejected — guards against poisoned index from bad past runs.
    """
    from core import normalizer as norm

    stream_by_id = {s.id: s for s in streams}
    # normalized_name → list of (channel, frozenset of channel_groups)
    index: dict[str, list[tuple[Channel, frozenset]]] = {}

    for channel in channels:
        channel_normalized = norm.normalize(channel.name, normalizer_mode).lower()
        channel_tokens = _meaningful_tokens(channel_normalized)

        # Collect channel_group IDs from all attached streams
        attached_groups: set[int] = {
            s.channel_group
            for sid in channel.stream_ids
            if (s := stream_by_id.get(sid)) and s.channel_group is not None
        }

        for stream_id in channel.stream_ids:
            attached = stream_by_id.get(stream_id)
            if not attached:
                continue
            stream_normalized = norm.normalize(attached.name, normalizer_mode)
            if not stream_normalized:
                continue
            stream_tokens = _meaningful_tokens(stream_normalized.lower())

            if not (stream_tokens & channel_tokens):
                continue  # token overlap guard

            entries = index.setdefault(stream_normalized, [])
            if not any(c.id == channel.id for c, _ in entries):
                entries.append((channel, frozenset(attached_groups)))

    return index


def _meaningful_tokens(text: str) -> set[str]:
    """Return the set of tokens that are at least 2 chars long and not purely numeric.

    Splits on whitespace AND common channel-name separators (|, :, -, –) so that
    'MY|CNN' and 'CNN HD' share the token 'cnn'. Filters out single characters
    and bare numbers (e.g. "7", "1") that would create false-positive overlaps.
    """
    import re
    raw_tokens = re.split(r'[\s|:\-–]+', text)
    return {t for t in raw_tokens if len(t) >= 2 and not t.isdigit()}


def _match_stream(
    stream: Stream,
    channels: list[Channel],
    config: Config,
    strategy: MatchStrategy,
    pairing_store,
    attachment_index: dict[str, list[tuple[Channel, frozenset]]],
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

    # 2. Attachment index — pick the entry whose groups are compatible with this stream
    entries = attachment_index.get(normalized)
    if entries:
        channel = _find_compatible_channel(entries, stream.channel_group, config)
        if channel:
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


def _find_compatible_channel(
    entries: list[tuple[Channel, frozenset]],
    stream_group: int | None,
    config: Config,
) -> Channel | None:
    """Return the first channel whose attached groups are compatible with stream_group.

    If group_regions is not configured, or the stream has no group, any entry matches
    (fall back to first entry — original single-channel behaviour).
    """
    if not config.group_regions or stream_group is None:
        return entries[0][0]

    for channel, attached_groups in entries:
        if _groups_compatible(stream_group, attached_groups, config.group_regions):
            return channel

    # No compatible entry found — don't match via attachment
    return None


def _groups_compatible(
    stream_group: int,
    attached_groups: frozenset,
    group_regions: list,
) -> bool:
    """Return True if stream_group and any member of attached_groups share a region.

    Two groups are compatible when they appear together in the same GroupRegion entry.
    If attached_groups is empty (channel had no group info), allow the match — we have
    no evidence of incompatibility.
    """
    if not attached_groups:
        return True

    # Find which regions contain the stream's group
    stream_regions = {
        r.name for r in group_regions if stream_group in r.groups
    }

    if not stream_regions:
        # Stream's group not in any configured region — can't confirm compatibility,
        # but also can't confirm incompatibility; allow the match
        return True

    for ag in attached_groups:
        ag_regions = {r.name for r in group_regions if ag in r.groups}
        if stream_regions & ag_regions:
            return True

    return False
