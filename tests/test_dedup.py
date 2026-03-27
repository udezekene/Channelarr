"""Tests for dedup/finder.py and dedup/merger.py."""

import pytest
import responses as resp_lib
from core.models import Channel
from dedup.finder import find_groups, DedupGroup
from dedup.merger import apply_dedup
from api.client import APIClient

BASE = "http://test.local"
CHANNELS_URL = f"{BASE}/api/channels/channels/"


def _channel(id, name, stream_ids=None):
    return Channel(
        id=id, name=name,
        stream_ids=stream_ids or [],
        channel_group_id=None,
        raw={"id": id, "name": name, "streams": stream_ids or []},
    )


def _client():
    c = APIClient(BASE, "u", "p", max_retries=1, retry_delay=0)
    c._token = "test-token"
    return c


# ──────────────────────────────────────────────── finder

class TestFindGroups:
    def test_finds_hd_fhd_variants_as_duplicates(self):
        channels = [
            _channel(64, "DSTV | SS La Liga FHD", stream_ids=[1, 2]),
            _channel(65, "DSTV | SS La Liga HD",  stream_ids=[3, 4]),
        ]
        groups = find_groups(channels)
        assert len(groups) == 1
        assert groups[0].normalized_name == "dstv | ss la liga"

    def test_unique_channels_not_flagged(self):
        channels = [
            _channel(1, "CNN"),
            _channel(2, "BBC One"),
            _channel(3, "ESPN"),
        ]
        assert find_groups(channels) == []

    def test_winner_is_channel_with_most_streams(self):
        channels = [
            _channel(1, "CNN HD",  stream_ids=[10, 11, 12]),  # 3 streams
            _channel(2, "CNN FHD", stream_ids=[20]),           # 1 stream
        ]
        groups = find_groups(channels)
        assert groups[0].winner.id == 1   # most streams wins

    def test_winner_tiebreak_is_lowest_id(self):
        channels = [
            _channel(5, "CNN HD",  stream_ids=[10, 11]),
            _channel(3, "CNN FHD", stream_ids=[20, 21]),
        ]
        groups = find_groups(channels)
        assert groups[0].winner.id == 3   # same stream count, lower id wins

    def test_merged_stream_ids_combines_all_without_duplicates(self):
        channels = [
            _channel(1, "CNN HD",  stream_ids=[10, 11]),
            _channel(2, "CNN FHD", stream_ids=[11, 12]),  # 11 is shared
        ]
        groups = find_groups(channels)
        assert sorted(groups[0].merged_stream_ids) == [10, 11, 12]

    def test_merged_stream_ids_winner_streams_come_first(self):
        channels = [
            _channel(1, "CNN HD",  stream_ids=[10, 11]),  # winner (more streams... tie, lower id)
            _channel(2, "CNN FHD", stream_ids=[20, 21]),
        ]
        groups = find_groups(channels)
        merged = groups[0].merged_stream_ids
        # Winner's streams should appear before duplicates' streams
        assert merged[:2] == [10, 11]
        assert set(merged[2:]) == {20, 21}

    def test_three_way_duplicate(self):
        channels = [
            _channel(1, "ESPN HD",  stream_ids=[1]),
            _channel(2, "ESPN FHD", stream_ids=[2]),
            _channel(3, "ESPN SD",  stream_ids=[3]),
        ]
        groups = find_groups(channels)
        assert len(groups) == 1
        assert len(groups[0].duplicates) == 2
        assert len(groups[0].merged_stream_ids) == 3

    def test_aggressive_normalizer_strips_prefix(self):
        channels = [
            _channel(1, "Region | Premier Sports HD",  stream_ids=[1]),
            _channel(2, "Region | Premier Sports FHD", stream_ids=[2]),
        ]
        groups = find_groups(channels, normalizer_mode="aggressive")
        assert len(groups) == 1
        assert groups[0].normalized_name == "premier sports"

    def test_multiple_independent_groups(self):
        channels = [
            _channel(1, "CNN HD",      stream_ids=[1]),
            _channel(2, "CNN FHD",     stream_ids=[2]),
            _channel(3, "BBC One HD",  stream_ids=[3]),
            _channel(4, "BBC One FHD", stream_ids=[4]),
            _channel(5, "ESPN",        stream_ids=[5]),  # no duplicate
        ]
        groups = find_groups(channels)
        assert len(groups) == 2
        names = {g.normalized_name for g in groups}
        assert "cnn" in names
        assert "bbc one" in names


# ──────────────────────────────────────────────── merger

class TestApplyDedup:
    @resp_lib.activate
    def test_puts_winner_with_merged_streams(self):
        channels = [
            _channel(1, "CNN HD",  stream_ids=[10, 11]),
            _channel(2, "CNN FHD", stream_ids=[12]),
        ]
        groups = find_groups(channels)

        resp_lib.add(resp_lib.PUT, f"{CHANNELS_URL}1/",
                     json={"id": 1, "name": "CNN HD", "streams": [10, 11, 12]}, status=200)
        resp_lib.add(resp_lib.DELETE, f"{CHANNELS_URL}2/", status=204)

        result = apply_dedup(groups, _client())
        assert len(result.merged) == 1
        assert len(result.failed) == 0

        import json
        put_body = json.loads(resp_lib.calls[0].request.body)
        assert set(put_body["streams"]) == {10, 11, 12}

    @resp_lib.activate
    def test_deletes_each_duplicate(self):
        channels = [
            _channel(1, "CNN HD",  stream_ids=[10]),
            _channel(2, "CNN FHD", stream_ids=[11]),
            _channel(3, "CNN SD",  stream_ids=[12]),
        ]
        groups = find_groups(channels)

        resp_lib.add(resp_lib.PUT,    f"{CHANNELS_URL}1/", json={}, status=200)
        resp_lib.add(resp_lib.DELETE, f"{CHANNELS_URL}2/", status=204)
        resp_lib.add(resp_lib.DELETE, f"{CHANNELS_URL}3/", status=204)

        result = apply_dedup(groups, _client())
        assert len(result.merged) == 1

        methods = [c.request.method for c in resp_lib.calls]
        assert methods.count("DELETE") == 2

    @resp_lib.activate
    def test_api_error_captured_and_continues(self):
        channels_a = [_channel(1, "CNN HD", stream_ids=[1]), _channel(2, "CNN FHD", stream_ids=[2])]
        channels_b = [_channel(3, "BBC One HD", stream_ids=[3]), _channel(4, "BBC One FHD", stream_ids=[4])]
        groups = find_groups(channels_a + channels_b)

        # CNN merge fails, BBC succeeds
        resp_lib.add(resp_lib.PUT, f"{CHANNELS_URL}1/", json={"detail": "error"}, status=500)
        resp_lib.add(resp_lib.PUT, f"{CHANNELS_URL}3/", json={}, status=200)
        resp_lib.add(resp_lib.DELETE, f"{CHANNELS_URL}4/", status=204)

        result = apply_dedup(groups, _client())
        assert len(result.failed) == 1
        assert len(result.merged) == 1
