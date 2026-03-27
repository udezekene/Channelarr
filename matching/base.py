"""MatchStrategy protocol — the interface every matching strategy must satisfy.

A strategy takes a single stream and the full list of channels, and returns
a StreamMatch describing the best channel found (or no channel if none matched).
"""

from typing import Protocol
from core.models import Stream, Channel, StreamMatch


class MatchStrategy(Protocol):
    def find_match(self, stream: Stream, channels: list[Channel]) -> StreamMatch:
        """Return a StreamMatch for stream against channels.

        If no channel matches, return a StreamMatch with channel=None and
        match_type=MatchType.NONE.
        """
        ...
