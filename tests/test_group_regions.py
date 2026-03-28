"""Tests for group-aware attachment matching using group_regions config.

When group_regions is configured, a stream only matches a channel via the
attachment index if the stream's channel_group shares a region with the
channel's attached streams' groups. This prevents MY|CNN matching a UK|CNN
channel even though both normalize to "CNN".
"""

import pytest
from core.models import Stream, Channel, MatchType
from core import planner
from core.planner import _groups_compatible, _find_compatible_channel
from matching.regex_match import RegexMatchStrategy
from config.schema import Config, MatchingConfig, GroupRegion


# ──────────────────────────────────────────────── helpers

def _config_with_regions():
    return Config(
        endpoint="http://test.local",
        username="u",
        password="p",
        group_regions=[
            GroupRegion(name="MY", groups=[1, 2]),
            GroupRegion(name="UK", groups=[3, 4]),
        ],
    )

def _config_no_regions():
    return Config(endpoint="http://test.local", username="u", password="p")

def _stream(id, name, provider=None, group=None):
    return Stream(id=id, name=name, provider=provider, channel_group=group, raw={})

def _channel(id, name, stream_ids=None, group=None):
    return Channel(id=id, name=name, stream_ids=stream_ids or [], channel_group_id=group, raw={})


# ──────────────────────────────────────────────── _groups_compatible unit tests

class TestGroupsCompatible:
    def test_same_region_compatible(self):
        regions = [GroupRegion(name="MY", groups=[1, 2])]
        assert _groups_compatible(1, frozenset([2]), regions) is True

    def test_different_regions_incompatible(self):
        regions = [
            GroupRegion(name="MY", groups=[1, 2]),
            GroupRegion(name="UK", groups=[3, 4]),
        ]
        assert _groups_compatible(1, frozenset([3]), regions) is False

    def test_empty_attached_groups_is_compatible(self):
        """If the channel has no group info, allow the match — no evidence of conflict."""
        regions = [GroupRegion(name="MY", groups=[1, 2])]
        assert _groups_compatible(1, frozenset(), regions) is True

    def test_stream_group_not_in_any_region_allows_match(self):
        """If we can't find the stream's group in any region, we can't confirm
        incompatibility — allow the match."""
        regions = [GroupRegion(name="MY", groups=[1, 2])]
        assert _groups_compatible(99, frozenset([1]), regions) is True


# ──────────────────────────────────────────────── planner integration

class TestGroupRegionsPlanner:
    def test_same_region_streams_match_via_attachment(self):
        """MY stream finds MY channel via attachment when both are in MY region."""
        existing = _stream(id=1, name="CNN HD", provider="ProviderA", group=1)
        new      = _stream(id=2, name="CNN HD", provider="ProviderB", group=2)  # same MY region
        my_channel = _channel(id=10, name="MY|CNN", stream_ids=[1])

        strategy = RegexMatchStrategy()
        config = _config_with_regions()
        cs = planner.plan([existing, new], [my_channel], config, strategy)

        assert len(cs.updates) == 1
        assert cs.updates[0].channel == my_channel
        assert len(cs.updates[0].candidates) == 2

    def test_different_region_stream_does_not_steal_channel(self):
        """UK stream does NOT match MY|CNN channel via attachment — different regions."""
        existing = _stream(id=1, name="CNN HD", provider="ProviderA", group=1)   # MY region
        uk_stream = _stream(id=2, name="CNN HD", provider="ProviderB", group=3)  # UK region
        my_channel = _channel(id=10, name="MY|CNN", stream_ids=[1])

        strategy = RegexMatchStrategy()
        config = _config_with_regions()
        cs = planner.plan([existing, uk_stream], [my_channel], config, strategy)

        # UK stream should NOT be grouped onto my_channel via attachment
        if cs.updates:
            update = cs.updates[0]
            candidate_providers = {m.stream.provider for m in update.candidates}
            # ProviderA (MY region) matched, ProviderB (UK region) should not
            assert "ProviderB" not in candidate_providers or update.channel != my_channel

    def test_two_channels_same_normalized_name_different_regions(self):
        """MY|CNN and UK|CNN are separate channels; each gets its own regional streams."""
        my_existing = _stream(id=1, name="CNN HD", provider="ProviderA", group=1)   # MY
        uk_existing = _stream(id=2, name="CNN HD", provider="ProviderA", group=3)   # UK
        my_new      = _stream(id=3, name="CNN HD", provider="ProviderB", group=2)   # MY
        uk_new      = _stream(id=4, name="CNN HD", provider="ProviderB", group=4)   # UK

        my_channel = _channel(id=10, name="MY|CNN", stream_ids=[1])
        uk_channel = _channel(id=20, name="UK|CNN", stream_ids=[2])

        strategy = RegexMatchStrategy()
        config = _config_with_regions()
        cs = planner.plan(
            [my_existing, uk_existing, my_new, uk_new],
            [my_channel, uk_channel],
            config, strategy,
        )

        updates = {u.channel.id: u for u in cs.updates}
        # MY new stream should go to MY channel
        assert 10 in updates
        my_candidates = {m.stream.id for m in updates[10].candidates}
        assert 3 in my_candidates  # my_new
        assert 4 not in my_candidates  # uk_new should NOT be in MY channel

    def test_no_group_regions_config_falls_back_to_first_entry(self):
        """Without group_regions configured, any attachment entry matches (original behaviour)."""
        existing = _stream(id=1, name="CNN HD", provider="ProviderA", group=1)
        new      = _stream(id=2, name="CNN HD", provider="ProviderB", group=99)  # unrelated group
        channel  = _channel(id=10, name="CNN", stream_ids=[1])

        strategy = RegexMatchStrategy()
        config = _config_no_regions()
        cs = planner.plan([existing, new], [channel], config, strategy)

        assert len(cs.updates) == 1
        assert cs.updates[0].channel == channel
