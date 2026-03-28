"""Applies dedup groups to the Dispatcharr API.

For each group:
  1. PUT the winner channel with the merged stream_ids list.
  2. DELETE each duplicate channel.

This module is the only place that writes API changes for the dedup operation.
It is never called during a dry-run — that gate lives in channelarr.py.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from dedup.finder import DedupGroup
from api.client import APIClient
from api import endpoints


@dataclass
class DedupResult:
    merged: list[DedupGroup] = field(default_factory=list)
    failed: list[tuple[DedupGroup, str]] = field(default_factory=list)


def _best_epg_from_duplicates(winner: "Channel", duplicates: list["Channel"]) -> str | None:
    """Return the most common non-empty tvg_id found in duplicates if winner has none."""
    if (winner.raw.get("tvg_id") or "").strip():
        return None  # winner already has an EPG — don't override

    counts: dict[str, int] = {}
    for dup in duplicates:
        epg = (dup.raw.get("tvg_id") or "").strip()
        if epg:
            counts[epg] = counts.get(epg, 0) + 1

    return max(counts, key=counts.__getitem__) if counts else None


def apply_dedup(groups: list[DedupGroup], client: APIClient) -> DedupResult:
    """Merge each duplicate group via the API. Returns a summary of outcomes."""
    result = DedupResult()

    for group in groups:
        try:
            # Update winner with all combined streams
            payload = {**group.winner.raw, "streams": group.merged_stream_ids}

            # If winner has no EPG, inherit the most common one from the duplicates
            fallback_epg = _best_epg_from_duplicates(group.winner, group.duplicates)
            if fallback_epg:
                payload["tvg_id"] = fallback_epg

            client.put(f"{endpoints.CHANNELS}{group.winner.id}/", json=payload)

            # Delete each duplicate
            for dup in group.duplicates:
                client.delete(f"{endpoints.CHANNELS}{dup.id}/")

            result.merged.append(group)

        except Exception as exc:
            result.failed.append((group, str(exc)))

    return result
