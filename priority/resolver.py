"""Priority resolver — picks the winning StreamMatch from a group of candidates.

Called by the planner when multiple streams map to the same channel.
The winning match determines metadata (tvg_id, etc.) and stream ordering.
All candidates are still assigned to the channel; this just picks who leads.
"""

from __future__ import annotations
from core.models import StreamMatch
from config.schema import Config


def resolve(candidates: list[StreamMatch], config: Config) -> StreamMatch | None:
    """Return the winning StreamMatch according to conflict_resolution.strategy."""
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    match config.conflict_resolution.strategy:
        case "highest_priority":
            return _by_priority(candidates, config.provider_priority)
        case "most_recent":
            # Higher stream ID = more recently added in Dispatcharr
            return max(candidates, key=lambda m: m.stream.id)
        case "first_match" | _:
            return candidates[0]


def _by_priority(
    candidates: list[StreamMatch], provider_priority: list[str]
) -> StreamMatch:
    # Build rank from list position — first entry = rank 1 (best)
    priority_map = {name.lower(): i for i, name in enumerate(provider_priority)}

    def sort_key(m: StreamMatch) -> int:
        if m.stream.provider is None:
            return len(priority_map) + 1   # no provider = lowest priority
        return priority_map.get(m.stream.provider.lower(), len(priority_map))

    return min(candidates, key=sort_key)
