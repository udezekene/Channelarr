"""Fuzzy match strategy backed by rapidfuzz.

Normalizes both stream and channel names using the configured normalizer,
then scores them with rapidfuzz.fuzz.ratio (0–100, scaled to 0.0–1.0).
A match is accepted when the score meets or exceeds fuzzy_threshold.

The highest-scoring channel wins; ties go to the first one found.
"""

from __future__ import annotations
import warnings
from core.models import Stream, Channel, StreamMatch, MatchType
from core import normalizer as norm

try:
    from rapidfuzz import fuzz as _fuzz
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The fuzzy matching strategy requires rapidfuzz. "
        "Install it with: pip install rapidfuzz"
    ) from exc


class FuzzyMatchStrategy:
    """Fuzzy name match using rapidfuzz.fuzz.ratio."""

    def __init__(
        self,
        normalizer_mode: str = "default",
        scope_to_group: bool = False,
        threshold: float = 0.85,
    ) -> None:
        self.normalizer_mode = normalizer_mode
        self.scope_to_group = scope_to_group
        self.threshold = threshold

    def find_match(self, stream: Stream, channels: list[Channel]) -> StreamMatch:
        normalized_stream = norm.normalize(stream.name, self.normalizer_mode)
        candidates = self._candidate_channels(stream, channels)

        best_channel: Channel | None = None
        best_score: float = 0.0
        best_normalized_channel: str | None = None

        for channel in candidates:
            normalized_channel = norm.normalize(channel.name, self.normalizer_mode)
            raw_score = _fuzz.ratio(
                normalized_stream.lower(), normalized_channel.lower()
            )
            score = raw_score / 100.0

            if score >= self.threshold and score > best_score:
                best_score = score
                best_channel = channel
                best_normalized_channel = normalized_channel

        if best_channel is not None:
            return StreamMatch(
                stream=stream,
                channel=best_channel,
                match_type=MatchType.FUZZY,
                score=best_score,
                normalized_stream_name=normalized_stream,
                normalized_channel_name=best_normalized_channel,
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
