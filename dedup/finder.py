"""Finds groups of duplicate channels — channels that share the same normalized name.

A duplicate group is 2+ channels whose names collapse to the same string after
normalization (e.g. "DSTV | SS La Liga HD" and "DSTV | SS La Liga FHD" both
normalize to "DSTV | SS La Liga"). Only one channel should exist; the others
are noise created by quality-suffix variants in stream names being promoted to
full channels.
"""

from __future__ import annotations
import re
from collections import defaultdict
from dataclasses import dataclass, field
from core.models import Channel
from core import normalizer as norm
from core.brands import apply_brands

# Dedup-only key transforms — applied on top of normalizer output for grouping
# purposes only. Never used for rename proposals.
_FC_RE     = re.compile(r'\s+F\.?C\.?$', re.IGNORECASE)   # strip trailing FC variants
_SPORTS_RE = re.compile(r'\bsports\b', re.IGNORECASE)      # normalise "Sports" → "Sport"


def _dedup_key(name: str, mode: str) -> str:
    """Normalise a channel name into a stable bucket key for duplicate detection.

    Applies the standard normaliser then adds dedup-specific collapsing:
      - Trailing FC/F.C/FC./F.C. stripped  → "Crystal Palace FC" == "Crystal Palace"
      - "Sports" → "sport"                 → "Premier Sports 1" == "Premier Sport 1"
    """
    key = norm.normalize(name, mode)
    key = _FC_RE.sub('', key)
    key = _SPORTS_RE.sub('sport', key)
    return key.lower()


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
    """Return one DedupGroup per set of channels that share a normalized name
    within the same channel_group_id.

    Channels in different groups are never merged — having CNN in a UK group
    and a DSTV group is intentional. Only duplicates within the same group
    (same channel_group_id) are flagged.

    Groups with only one channel are not duplicates and are excluded.
    Results are sorted by group then name for stable, readable output.
    """
    buckets: dict[tuple, list[Channel]] = defaultdict(list)
    for channel in channels:
        key_name = _dedup_key(channel.name, normalizer_mode)
        if key_name:
            buckets[(channel.channel_group_id, key_name)].append(channel)

    groups: list[DedupGroup] = []
    for (_, key), bucket in sorted(buckets.items(), key=lambda x: (str(x[0][0] or ""), x[0][1])):
        if len(bucket) < 2:
            continue

        winner = _pick_winner(bucket)
        duplicates = [c for c in bucket if c.id != winner.id]
        merged = _merge_stream_ids(winner, duplicates)
        confidence = "auto" if all(len(d.stream_ids) <= 1 for d in duplicates) else "review"

        groups.append(DedupGroup(
            normalized_name=apply_brands(key),
            winner=winner,
            duplicates=duplicates,
            merged_stream_ids=merged,
            confidence=confidence,
        ))

    return groups


# ──────────────────────────────────────────────── internals

def _pick_winner(channels: list[Channel]) -> Channel:
    """Pick the channel to keep.

    Priority order:
      1. Already-clean name (normalized + brand-cased == current name) — avoids
         leaving a prefixed name like 'UK-CNN' as the survivor.
      2. Most streams attached.
      3. Lowest channel ID (created earliest in Dispatcharr).
    """
    from core import normalizer as norm
    from core.brands import apply_brands

    def _is_clean(c: Channel) -> bool:
        return apply_brands(norm.normalize(c.name, "aggressive")) == c.name

    return min(channels, key=lambda c: (not _is_clean(c), -len(c.stream_ids), c.id))


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
