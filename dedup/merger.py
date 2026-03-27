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


def apply_dedup(groups: list[DedupGroup], client: APIClient) -> DedupResult:
    """Merge each duplicate group via the API. Returns a summary of outcomes."""
    result = DedupResult()

    for group in groups:
        try:
            # Update winner with all combined streams
            payload = {**group.winner.raw, "streams": group.merged_stream_ids}
            client.put(f"{endpoints.CHANNELS}{group.winner.id}/", json=payload)

            # Delete each duplicate
            for dup in group.duplicates:
                client.delete(f"{endpoints.CHANNELS}{dup.id}/")

            result.merged.append(group)

        except Exception as exc:
            result.failed.append((group, str(exc)))

    return result
