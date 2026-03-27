"""Tests for api/client.py — HTTP wrapper behavior."""

import pytest
import responses as resp_lib
from responses import matchers
from api.client import APIClient
from utils.exceptions import APIException


BASE = "http://test.local"
TOKEN_URL = f"{BASE}/api/accounts/token/"
STREAMS_URL = f"{BASE}/api/channels/streams/"
CHANNELS_URL = f"{BASE}/api/channels/channels/"
REFRESH_URL = f"{BASE}/api/m3u/refresh/"


def _client(max_retries=1, retry_delay=0):
    """Return a client configured for fast tests (no real sleep)."""
    return APIClient(BASE, "user", "pass", max_retries=max_retries, retry_delay=retry_delay)


def _mock_auth(rsps):
    rsps.add(resp_lib.POST, TOKEN_URL,
             json={"access": "test-token", "refresh": "refresh-token"}, status=200)


class TestAuthentication:
    @resp_lib.activate
    def test_successful_auth_stores_token(self):
        _mock_auth(resp_lib)
        client = _client()
        client.authenticate()
        assert client._token == "test-token"

    @resp_lib.activate
    def test_auth_sends_correct_credentials(self):
        resp_lib.add(resp_lib.POST, TOKEN_URL,
                     json={"access": "tok", "refresh": "ref"}, status=200)
        client = _client()
        client.authenticate()
        request_body = resp_lib.calls[0].request.body
        assert b"user" in request_body
        assert b"pass" in request_body

    @resp_lib.activate
    def test_auth_failure_raises_api_exception(self):
        resp_lib.add(resp_lib.POST, TOKEN_URL,
                     json={"detail": "No active account"}, status=401)
        client = _client()
        with pytest.raises(APIException):
            client.authenticate()


class TestGetRequest:
    @resp_lib.activate
    def test_successful_get_returns_parsed_json(self):
        _mock_auth(resp_lib)
        resp_lib.add(resp_lib.GET, STREAMS_URL,
                     json={"results": [{"id": 1, "name": "CNN"}]}, status=200)
        client = _client()
        data = client.get("/api/channels/streams/")
        assert data["results"][0]["id"] == 1

    @resp_lib.activate
    def test_non_2xx_raises_api_exception(self):
        _mock_auth(resp_lib)
        resp_lib.add(resp_lib.GET, STREAMS_URL, json={"detail": "forbidden"}, status=403)
        client = _client()
        with pytest.raises(APIException) as exc_info:
            client.get("/api/channels/streams/")
        assert "403" in str(exc_info.value)


class TestRetryBehavior:
    @resp_lib.activate
    def test_retries_on_500_and_succeeds_second_attempt(self):
        _mock_auth(resp_lib)
        # First call: 500, second call: 200
        resp_lib.add(resp_lib.GET, STREAMS_URL, json={}, status=500)
        resp_lib.add(resp_lib.GET, STREAMS_URL, json={"results": []}, status=200)
        client = _client(max_retries=2, retry_delay=0)
        data = client.get("/api/channels/streams/")
        assert data == {"results": []}

    @resp_lib.activate
    def test_raises_after_retries_exhausted(self):
        _mock_auth(resp_lib)
        resp_lib.add(resp_lib.GET, STREAMS_URL, json={}, status=500)
        resp_lib.add(resp_lib.GET, STREAMS_URL, json={}, status=500)
        client = _client(max_retries=2, retry_delay=0)
        with pytest.raises(APIException):
            client.get("/api/channels/streams/")
