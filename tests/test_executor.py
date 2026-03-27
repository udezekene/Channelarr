"""Tests for core/executor.py — API write behavior."""

import pytest
import responses as resp_lib
from core import executor
from core.models import ChangeSet, ChannelChange, ChangeType, SkipReason
from api.client import APIClient
from matching.regex_match import RegexMatchStrategy
from core import planner


BASE = "http://test.local"
TOKEN_URL   = f"{BASE}/api/accounts/token/"
CHANNELS_URL = f"{BASE}/api/channels/channels/"
FROM_STREAM_URL = f"{BASE}/api/channels/channels/from-stream/"


def _client():
    c = APIClient(BASE, "user", "pass", max_retries=1, retry_delay=0)
    c._token = "test-token"   # skip auth for executor tests
    return c


def _mock_put(rsps, channel_id):
    rsps.add(resp_lib.PUT, f"{CHANNELS_URL}{channel_id}/",
             json={"id": channel_id, "name": "CNN", "streams": [1, 2]}, status=200)


def _make_update_changeset(stream_cnn_hd, stream_cnn_sd, channel_cnn):
    strategy = RegexMatchStrategy()
    from config.schema import Config
    config = Config(endpoint=BASE, username="u", password="p")
    return planner.plan([stream_cnn_hd, stream_cnn_sd], [channel_cnn], config, strategy)


class TestUpdateChange:
    @resp_lib.activate
    def test_update_calls_put_and_returns_success(
        self, stream_cnn_hd, stream_cnn_sd, channel_cnn
    ):
        _mock_put(resp_lib, channel_cnn.id)
        changeset = _make_update_changeset(stream_cnn_hd, stream_cnn_sd, channel_cnn)

        result = executor.apply(changeset, _client())

        assert len(result.succeeded) == 1
        assert result.succeeded[0].success is True

    @resp_lib.activate
    def test_update_payload_contains_all_stream_ids(
        self, stream_cnn_hd, stream_cnn_sd, channel_cnn
    ):
        _mock_put(resp_lib, channel_cnn.id)
        changeset = _make_update_changeset(stream_cnn_hd, stream_cnn_sd, channel_cnn)
        executor.apply(changeset, _client())

        import json
        body = json.loads(resp_lib.calls[0].request.body)
        assert set(body["streams"]) == {stream_cnn_hd.id, stream_cnn_sd.id}


class TestCreateChange:
    @resp_lib.activate
    def test_create_posts_to_from_stream_then_puts(
        self, stream_unknown, channel_cnn, config_allow_create
    ):
        resp_lib.add(resp_lib.POST, FROM_STREAM_URL,
                     json={"id": 99, "name": "UnknownChannel", "streams": []}, status=201)
        resp_lib.add(resp_lib.PUT, f"{CHANNELS_URL}99/",
                     json={"id": 99, "name": "UnknownChannel", "streams": [99]}, status=200)

        strategy = RegexMatchStrategy()
        changeset = planner.plan([stream_unknown], [channel_cnn], config_allow_create, strategy)
        assert len(changeset.creates) == 1

        result = executor.apply(changeset, _client())
        assert result.succeeded[0].success is True
        # Verify both POST and PUT were called
        methods = [c.request.method for c in resp_lib.calls]
        assert "POST" in methods
        assert "PUT" in methods


class TestSkipChange:
    @resp_lib.activate
    def test_skip_makes_no_api_call(self, stream_unknown, channel_cnn, minimal_config):
        strategy = RegexMatchStrategy()
        changeset = planner.plan([stream_unknown], [channel_cnn], minimal_config, strategy)
        # Planner emits CREATE_NOT_PERMITTED for stream_unknown AND
        # DELETE_NOT_PERMITTED for channel_cnn (no match found)
        assert len(changeset.skips) >= 1

        result = executor.apply(changeset, _client())

        # No HTTP calls should have been made for any SKIP
        assert len(resp_lib.calls) == 0
        # All skips are recorded in the result
        assert len(result.applied) == len(changeset.skips)


class TestErrorHandling:
    @resp_lib.activate
    def test_api_error_on_update_captured_and_execution_continues(
        self, stream_cnn_hd, stream_bbc, channel_cnn, channel_bbc, minimal_config
    ):
        # CNN update fails, BBC update succeeds
        resp_lib.add(resp_lib.PUT, f"{CHANNELS_URL}{channel_cnn.id}/",
                     json={"detail": "server error"}, status=500)
        resp_lib.add(resp_lib.PUT, f"{CHANNELS_URL}{channel_bbc.id}/",
                     json={"id": 11, "name": "BBC One", "streams": [3]}, status=200)

        strategy = RegexMatchStrategy()
        changeset = planner.plan(
            [stream_cnn_hd, stream_bbc], [channel_cnn, channel_bbc], minimal_config, strategy
        )
        result = executor.apply(changeset, _client())

        assert len(result.failed) == 1
        assert len(result.succeeded) == 1
