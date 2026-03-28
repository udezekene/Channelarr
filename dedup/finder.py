"""Finds groups of duplicate channels — channels that share the same normalized name.

A duplicate group is 2+ channels whose names collapse to the same string after
normalization (e.g. "DSTV | SS La Liga HD" and "DSTV | SS La Liga FHD" both
normalize to "DSTV | SS La Liga"). Only one channel should exist; the others
are noise created by quality-suffix variants in stream names being promoted to
full channels.
"""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from core.models import Channel
from core import normalizer as norm


@dataclass
class DedupGroup:
    normalized_name: str
    winner: Channel              # channel to keep; receives all combined streams
    duplicates: list[Channel]    # channels to delete after the merge
    merged_stream_ids: list[int] # deduplicated union of all stream_ids, winner's first
    confidence: str = "review"   # "auto" if all losers have ≤1 stream; "review" otherwise


def find_groups(
    channels: list[Channel],
    normalizer_mode: str = "default",
) -> list[DedupGroup]:
    """Return one DedupGroup per set of channels that share a normalized name.

    Groups with only one channel are not duplicates and are excluded.
    Results are sorted by normalized name for stable, readable output.
    """
    buckets: dict[str, list[Channel]] = defaultdict(list)
    for channel in channels:
        key = norm.normalize(channel.name, normalizer_mode).lower()
        if key:
            buckets[key].append(channel)

    groups: list[DedupGroup] = []
    for normalized_name, bucket in sorted(buckets.items()):
        if len(bucket) < 2:
            continue

        winner = _pick_winner(bucket)
        duplicates = [c for c in bucket if c.id != winner.id]
        merged = _merge_stream_ids(winner, duplicates)
        confidence = "auto" if all(len(d.stream_ids) <= 1 for d in duplicates) else "review"

        groups.append(DedupGroup(
            normalized_name=normalized_name,
            winner=winner,
            duplicates=duplicates,
            merged_stream_ids=merged,
            confidence=confidence,
        ))

    return groups


# ──────────────────────────────────────────────── internals

def _pick_winner(channels: list[Channel]) -> Channel:
    """Pick the channel to keep.

    Prefers the channel with the most streams already attached.
    Ties broken by lowest channel ID (created earliest in Dispatcharr).
    """
    return min(channels, key=lambda c: (-len(c.stream_ids), c.id))


def _merge_stream_ids(winner: Channel, duplicates: list[Channel]) -> list[int]:
    """Return a deduplicated stream_ids list: winner's streams first, then extras."""
    seen: set[int] = set()
    merged: list[int] = []
    for channel in [winner, *duplicates]:
        for sid in channel.stream_ids:
            if sid not in seen:
                seen.add(sid)
                merged.append(sid)
    return merged
