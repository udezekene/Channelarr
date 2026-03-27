"""Tests for priority/resolver.py."""

import pytest
from core.models import StreamMatch, MatchType
from config.schema import Config, ProviderPriority, ConflictResolutionConfig
from priority.resolver import resolve


def _make_match(stream_id: int, provider: str | None, channel=None) -> StreamMatch:
    from core.models import Stream
    stream = Stream(id=stream_id, name="CNN", provider=provider, channel_group=5,
                    raw={"id": stream_id})
    return StreamMatch(
        stream=stream, channel=channel, match_type=MatchType.REGEX,
        score=1.0, normalized_stream_name="CNN", normalized_channel_name="CNN",
    )


def _config(strategy="highest_priority", providers=None) -> Config:
    return Config(
        endpoint="x", username="u", password="p",
        provider_priority=providers or [],
        conflict_resolution=ConflictResolutionConfig(strategy=strategy),
    )


class TestHighestPriority:
    def test_ranked_provider_wins(self):
        m1 = _make_match(1, "ProviderA")
        m2 = _make_match(2, "ProviderB")
        cfg = _config(providers=[
            ProviderPriority(name="ProviderA", rank=1),
            ProviderPriority(name="ProviderB", rank=2),
        ])
        assert resolve([m1, m2], cfg) == m1
        assert resolve([m2, m1], cfg) == m1   # order-independent

    def test_unranked_provider_loses_to_ranked(self):
        ranked = _make_match(1, "ProviderA")
        unranked = _make_match(2, "ProviderX")
        cfg = _config(providers=[ProviderPriority(name="ProviderA", rank=1)])
        assert resolve([unranked, ranked], cfg) == ranked

    def test_none_provider_treated_as_lowest(self):
        good = _make_match(1, "ProviderA")
        no_provider = _make_match(2, None)
        cfg = _config(providers=[ProviderPriority(name="ProviderA", rank=1)])
        assert resolve([no_provider, good], cfg) == good


class TestMostRecent:
    def test_highest_stream_id_wins(self):
        m1 = _make_match(1, "A")
        m2 = _make_match(5, "B")
        cfg = _config(strategy="most_recent")
        assert resolve([m1, m2], cfg) == m2

    def test_single_candidate_returned_as_is(self):
        m = _make_match(3, "A")
        cfg = _config(strategy="most_recent")
        assert resolve([m], cfg) == m


class TestFirstMatch:
    def test_first_candidate_wins(self):
        m1 = _make_match(1, "A")
        m2 = _make_match(2, "B")
        cfg = _config(strategy="first_match")
        assert resolve([m1, m2], cfg) == m1

    def test_unknown_strategy_falls_back_to_first(self):
        m1 = _make_match(1, "A")
        m2 = _make_match(2, "B")
        cfg = _config(strategy="nonexistent")
        assert resolve([m1, m2], cfg) == m1


class TestEdgeCases:
    def test_empty_candidates_returns_none(self):
        assert resolve([], _config()) is None

    def test_single_candidate_always_wins(self):
        m = _make_match(1, "A")
        for strategy in ["highest_priority", "most_recent", "first_match"]:
            assert resolve([m], _config(strategy=strategy)) == m
