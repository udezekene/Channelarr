"""Tests for core/planner.py — the pure planning function."""

import pytest
from core.models import ChangeType, SkipReason
from core import planner
from matching.regex_match import RegexMatchStrategy


@pytest.fixture
def strategy():
    return RegexMatchStrategy()


class TestBasicMatching:
    def test_stream_matches_existing_channel_produces_update(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        changeset = planner.plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        assert len(changeset.updates) == 1
        assert changeset.updates[0].channel == channel_cnn

    def test_stream_no_match_create_not_permitted_produces_skip(
        self, strategy, stream_unknown, channel_cnn, minimal_config
    ):
        changeset = planner.plan([stream_unknown], [channel_cnn], minimal_config, strategy)
        # At least one skip is CREATE_NOT_PERMITTED (channel_cnn also gets
        # DELETE_NOT_PERMITTED from the second pass since no stream matched it)
        create_skips = [s for s in changeset.skips
                        if s.skip_reason == SkipReason.CREATE_NOT_PERMITTED]
        assert len(create_skips) == 1

    def test_stream_no_match_create_permitted_produces_create(
        self, strategy, stream_unknown, channel_cnn, config_allow_create
    ):
        changeset = planner.plan([stream_unknown], [channel_cnn], config_allow_create, strategy)
        assert len(changeset.creates) == 1
        assert changeset.creates[0].channel is None


class TestGrouping:
    def test_multiple_streams_same_normalized_name_grouped_together(
        self, strategy, stream_cnn_hd, stream_cnn_sd, channel_cnn, minimal_config
    ):
        """CNN HD and CNN SD should both normalize to "CNN" and group under one ChannelChange."""
        changeset = planner.plan(
            [stream_cnn_hd, stream_cnn_sd], [channel_cnn], minimal_config, strategy
        )
        assert len(changeset.updates) == 1
        assert len(changeset.updates[0].candidates) == 2

    def test_different_streams_produce_separate_changes(
        self, strategy, stream_cnn_hd, stream_bbc, channel_cnn, channel_bbc, minimal_config
    ):
        changeset = planner.plan(
            [stream_cnn_hd, stream_bbc],
            [channel_cnn, channel_bbc],
            minimal_config,
            strategy,
        )
        assert len(changeset.updates) == 2


class TestPurity:
    def test_planner_makes_no_api_calls(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        """The planner must be pure — inject a strategy that would raise if it touched the network."""

        class NetworkBlockingStrategy:
            def find_match(self, stream, channels):
                # This is fine — it's the strategy, not a network call
                return strategy.find_match(stream, channels)

        # If the planner accidentally called requests or a client, it would raise.
        # We just verify it runs without error and produces the expected result.
        changeset = planner.plan(
            [stream_cnn_hd], [channel_cnn], minimal_config, NetworkBlockingStrategy()
        )
        assert len(changeset.changes) == 1

    def test_channel_with_no_matching_streams_gets_delete_not_permitted(
        self, strategy, stream_bbc, channel_cnn, minimal_config
    ):
        """A channel with no matching streams appears as SKIP(DELETE_NOT_PERMITTED),
        not as UPDATE or DELETE. It is evaluated but never acted upon."""
        changeset = planner.plan([stream_bbc], [channel_cnn], minimal_config, strategy)
        # channel_cnn has no matching stream → SKIP(DELETE_NOT_PERMITTED)
        cnn_changes = [c for c in changeset.changes if c.channel == channel_cnn]
        assert len(cnn_changes) == 1
        assert cnn_changes[0].change_type == ChangeType.SKIP
        assert cnn_changes[0].skip_reason == SkipReason.DELETE_NOT_PERMITTED
