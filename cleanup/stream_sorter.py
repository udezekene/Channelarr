"""Sorts the stream_ids list on each channel by (quality tier, provider rank).

Sort key per stream:
  1. Quality tier  — detected from the stream name  (lower = better)
       0  4K / UHD
       1  FHD / HDR
       2  HD
       3  SD
       4  unknown / no quality token
  2. Provider rank — position in config.provider_priority  (lower = better)
       unlisted providers come after all listed ones
       streams with no provider come last
  3. Stream ID     — stable tiebreaker within the same tier + provider

Only channels where the proposed order differs from the current order are
included in the results.  Only runs when provider_priority is configured.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from core.models import Channel, Stream
from api import endpoints


# Quality tier patterns — checked in order, first match wins
_TIER_PATTERNS = [
    (0, re.compile(r'\b(?:4K|UHD)\b',        re.IGNORECASE)),
    (1, re.compile(r'\b(?:FHD|HDR)\b',        re.IGNORECASE)),
    (2, re.compile(r'\bHD\b',                 re.IGNORECASE)),
    (3, re.compile(r'\bSD\b',                 re.IGNORECASE)),
]
_UNKNOWN_TIER = 4


def stream_quality_tier(name: str) -> int:
    """Return the quality tier for a stream name (lower = higher quality)."""
    for tier, pattern in _TIER_PATTERNS:
        if pattern.search(name):
            return tier
    return _UNKNOWN_TIER


@dataclass
class StreamReorderProposal:
    channel: Channel
    current_stream_ids: list[int]
    proposed_stream_ids: list[int]


@dataclass
class StreamReorderStats:
    proposals: list[StreamReorderProposal]
    already_optimal: int   # 2+ streams, order already correct
    single_stream: int     # skipped — only 1 stream, nothing to sort


def find_reorders(
    channels: list[Channel],
    stream_lookup: dict[int, Stream],
    provider_priority: list[str],
) -> StreamReorderStats:
    """Return proposals for channels whose stream order would change, plus counts.

    Sort key: (quality_tier, provider_rank, stream_id)
    """
    priority_map = {name.lower(): i for i, name in enumerate(provider_priority)}
    unlisted_rank = len(priority_map)
    no_provider_rank = unlisted_rank + 1

    proposals: list[StreamReorderProposal] = []
    already_optimal = 0
    single_stream = 0

    for channel in channels:
        if len(channel.stream_ids) < 2:
            single_stream += 1
            continue

        def _sort_key(sid: int) -> tuple:
            stream = stream_lookup.get(sid)
            if stream is None:
                return (_UNKNOWN_TIER, no_provider_rank, sid)
            tier = stream_quality_tier(stream.name)
            if stream.provider is None:
                rank = no_provider_rank
            else:
                rank = priority_map.get(stream.provider.lower(), unlisted_rank)
            return (tier, rank, sid)

        sorted_ids = sorted(channel.stream_ids, key=_sort_key)
        if sorted_ids != list(channel.stream_ids):
            proposals.append(StreamReorderProposal(
                channel=channel,
                current_stream_ids=list(channel.stream_ids),
                proposed_stream_ids=sorted_ids,
            ))
        else:
            already_optimal += 1

    return StreamReorderStats(
        proposals=proposals,
        already_optimal=already_optimal,
        single_stream=single_stream,
    )


def apply_reorders(
    proposals: list[StreamReorderProposal],
    client,
) -> tuple[list[StreamReorderProposal], list[tuple[StreamReorderProposal, str]]]:
    """Write the reordered stream lists via the API."""
    succeeded: list[StreamReorderProposal] = []
    failed: list[tuple[StreamReorderProposal, str]] = []

    for proposal in proposals:
        try:
            payload = {**proposal.channel.raw, "streams": proposal.proposed_stream_ids}
            client.put(f"{endpoints.CHANNELS}{proposal.channel.id}/", json=payload)
            succeeded.append(proposal)
        except Exception as exc:
            failed.append((proposal, str(exc)))

    return succeeded, failed
