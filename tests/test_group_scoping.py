"""Tests for group-scoped matching in matching/regex_match.py."""

import pytest
import warnings
from matching.regex_match import RegexMatchStrategy
from core.models import MatchType


class TestScopedMatching:
    def test_same_group_matches(self, stream_cnn_hd, channel_cnn):
        """stream_cnn_hd (group 5) should match channel_cnn (group 5)."""
        strategy = RegexMatchStrategy(scope_to_group=True)
        result = strategy.find_match(stream_cnn_hd, [channel_cnn])
        assert result.channel == channel_cnn

    def test_different_group_does_not_match(self, stream_my_cnn, channel_cnn):
        """stream_my_cnn (group 10) must not match channel_cnn (group 5)."""
        strategy = RegexMatchStrategy(scope_to_group=True)
        result = strategy.find_match(stream_my_cnn, [channel_cnn])
        assert result.channel is None
        assert result.match_type == MatchType.NONE

    def test_cnn_hd_matches_correct_group_when_two_cnn_channels_exist(
        self, channel_cnn, channel_my_cnn
    ):
        """CNN HD (group 10) should match CNN in group 10, not CNN in group 5.

        Note: "MY | CNN" cannot auto-match "CNN" with the default normalizer —
        the "MY | " prefix is not stripped until the aggressive normalizer (Phase 4).
        This test uses a stream that shares a normalized name with its channel.
        """
        from core.models import Stream
        # A stream that normalizes to "CNN" and belongs to the Malaysian group (10)
        stream_cnn_hd_my = Stream(
            id=11, name="CNN HD", provider="ProviderMY", channel_group=10,
            raw={"id": 11, "name": "CNN HD", "channel_group": 10},
        )
        strategy = RegexMatchStrategy(scope_to_group=True)
        result = strategy.find_match(stream_cnn_hd_my, [channel_cnn, channel_my_cnn])
        assert result.channel == channel_my_cnn   # group 10
        assert result.channel != channel_cnn       # group 5

    def test_my_cnn_prefix_requires_aggressive_normalizer(self, stream_my_cnn, channel_my_cnn):
        """With the default normalizer, MY|CNN does not match a channel named CNN.
        This is expected — prefix stripping arrives in Phase 4."""
        strategy = RegexMatchStrategy(scope_to_group=True)
        result = strategy.find_match(stream_my_cnn, [channel_my_cnn])
        # "MY | CNN" != "CNN" after default normalization
        assert result.channel is None

    def test_fallback_to_unscoped_when_no_same_group_channels(
        self, stream_my_cnn, channel_cnn
    ):
        """If scope_to_group=True but no channels in stream's group, fall back."""
        # stream_my_cnn is group 10, channel_cnn is group 5 — no group-10 channels
        strategy = RegexMatchStrategy(scope_to_group=True)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = strategy.find_match(stream_my_cnn, [channel_cnn])
        assert any("Falling back to unscoped" in str(warning.message) for warning in w)
        # After fallback, normalized "MY | CNN" != "CNN", so still no match
        assert result.channel is None

    def test_scoped_false_matches_across_groups(self, stream_my_cnn, channel_cnn):
        """scope_to_group=False (default) — group is ignored, name-only match."""
        strategy = RegexMatchStrategy(scope_to_group=False)
        # MY|CNN normalized = "MY | CNN", channel_cnn name = "CNN" — no name match anyway
        result = strategy.find_match(stream_my_cnn, [channel_cnn])
        assert result.channel is None   # names differ even without scoping

    def test_unscoped_finds_match_regardless_of_group(self, stream_cnn_hd, channel_cnn):
        """Without scoping, group is irrelevant."""
        # Give stream a different group from channel
        from core.models import Stream
        stream = Stream(id=1, name="CNN HD", provider=None, channel_group=99,
                        raw={"id": 1, "name": "CNN HD"})
        strategy = RegexMatchStrategy(scope_to_group=False)
        result = strategy.find_match(stream, [channel_cnn])
        assert result.channel == channel_cnn

    def test_stream_with_no_group_skips_scoping(self, channel_cnn):
        """A stream with channel_group=None bypasses group filtering entirely."""
        from core.models import Stream
        stream = Stream(id=1, name="CNN HD", provider=None, channel_group=None,
                        raw={"id": 1, "name": "CNN HD"})
        strategy = RegexMatchStrategy(scope_to_group=True)
        result = strategy.find_match(stream, [channel_cnn])
        assert result.channel == channel_cnn
