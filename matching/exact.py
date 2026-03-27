"""Exact match strategy.

Compares stream and channel names with only whitespace trimmed — no quality
token stripping, no prefix removal.  The comparison is case-insensitive.

Use this when your stream names and channel names are already clean and
consistent, and you want zero tolerance for partial matches.
"""

from __future__ import annotations
import warnings
from core.models import Stream, Channel, StreamMatch, MatchType
from core import normalizer as norm


class ExactMatchStrategy:
    """Case-insensitive exact match on whitespace-trimmed names (no normalisation)."""

    def __init__(
        self,
        scope_to_group: bool = False,
    ) -> None:
        self.scope_to_group = scope_to_group

    def find_match(self, stream: Stream, channels: list[Channel]) -> StreamMatch:
        stream_name = stream.name.strip()
        candidates = self._candidate_channels(stream, channels)

        for channel in candidates:
            channel_name = channel.name.strip()
            if stream_name.lower() == channel_name.lower():
                return StreamMatch(
                    stream=stream,
                    channel=channel,
                    match_type=MatchType.EXACT,
                    score=1.0,
                    normalized_stream_name=stream_name,
                    normalized_channel_name=channel_name,
                )

        return StreamMatch(
            stream=stream,
            channel=None,
            match_type=MatchType.NONE,
            score=0.0,
            normalized_stream_name=stream_name,
            normalized_channel_name=None,
        )

    def _candidate_channels(
        self, stream: Stream, channels: list[Channel]
    ) -> list[Channel]:
        if not self.scope_to_group or stream.channel_group is None:
            return channels

        same_group = [c for c in channels if c.channel_group_id == stream.channel_group]
        if not same_group:
            warnings.warn(
                f"scope_to_group=True but no channels found in group {stream.channel_group} "
                f"for stream '{stream.name}'. Falling back to unscoped matching.",
                stacklevel=2,
            )
            return channels

        return same_group
