"""Regex/normalization match strategy.

Normalizes both the stream name and each channel name using the configured
normalizer, then does a case-insensitive exact comparison.  This ports the
matching behavior of the upstream dispatcharr-group-channel-streams tool.

Group scoping
-------------
When scope_to_group=True, the strategy only considers channels whose
channel_group_id matches the stream's channel_group.  If no same-group
channels exist, it falls back to the full channel list and logs a warning —
a no-match is still better than a silent wrong-group match.
"""

import warnings
from core.models import Stream, Channel, StreamMatch, MatchType
from core import normalizer as norm


class RegexMatchStrategy:
    """Match streams to channels by normalizing both names, then comparing exactly."""

    def __init__(
        self,
        normalizer_mode: str = "default",
        scope_to_group: bool = False,
    ) -> None:
        self.normalizer_mode = normalizer_mode
        self.scope_to_group = scope_to_group

    def find_match(self, stream: Stream, channels: list[Channel]) -> StreamMatch:
        normalized_stream = norm.normalize(stream.name, self.normalizer_mode)
        candidates = self._candidate_channels(stream, channels)

        for channel in candidates:
            normalized_channel = norm.normalize(channel.name, self.normalizer_mode)
            if normalized_stream.lower() == normalized_channel.lower():
                return StreamMatch(
                    stream=stream,
                    channel=channel,
                    match_type=MatchType.REGEX,
                    score=1.0,
                    normalized_stream_name=normalized_stream,
                    normalized_channel_name=normalized_channel,
                )

        return StreamMatch(
            stream=stream,
            channel=None,
            match_type=MatchType.NONE,
            score=0.0,
            normalized_stream_name=normalized_stream,
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
