"""Shared pytest fixtures for all Channelarr tests."""

import pytest
from core.models import Stream, Channel
from config.schema import Config


# ── Streams ───────────────────────────────────────────────────────────────────

@pytest.fixture
def stream_cnn_hd():
    return Stream(id=1, name="CNN HD", provider="ProviderA", channel_group=5,
                  raw={"id": 1, "name": "CNN HD", "m3u_account": "ProviderA", "channel_group": 5})

@pytest.fixture
def stream_cnn_sd():
    return Stream(id=2, name="CNN SD", provider="ProviderB", channel_group=5,
                  raw={"id": 2, "name": "CNN SD", "m3u_account": "ProviderB", "channel_group": 5})

@pytest.fixture
def stream_bbc():
    return Stream(id=3, name="BBC One", provider="ProviderA", channel_group=5,
                  raw={"id": 3, "name": "BBC One", "m3u_account": "ProviderA", "channel_group": 5})

@pytest.fixture
def stream_unknown():
    """Stream whose name has no matching channel."""
    return Stream(id=99, name="UnknownChannel HD", provider=None, channel_group=99,
                  raw={"id": 99, "name": "UnknownChannel HD", "channel_group": 99})

@pytest.fixture
def stream_my_cnn():
    """Malaysian CNN stream — same normalized name as CNN but different group."""
    return Stream(id=10, name="MY | CNN", provider="ProviderMY", channel_group=10,
                  raw={"id": 10, "name": "MY | CNN", "m3u_account": "ProviderMY", "channel_group": 10})


# ── Channels ──────────────────────────────────────────────────────────────────

@pytest.fixture
def channel_cnn():
    return Channel(id=10, name="CNN", stream_ids=[], channel_group_id=5,
                   raw={"id": 10, "name": "CNN", "streams": [], "tvg_id": None, "channel_group_id": 5})

@pytest.fixture
def channel_bbc():
    return Channel(id=11, name="BBC One", stream_ids=[], channel_group_id=5,
                   raw={"id": 11, "name": "BBC One", "streams": [], "tvg_id": None, "channel_group_id": 5})

@pytest.fixture
def channel_my_cnn():
    """CNN channel in the Malaysian group."""
    return Channel(id=20, name="CNN", stream_ids=[], channel_group_id=10,
                   raw={"id": 20, "name": "CNN", "streams": [], "channel_group_id": 10})


# ── Configs ───────────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_config():
    return Config(endpoint="http://test.local", username="user", password="pass")

@pytest.fixture
def config_allow_create():
    return Config(
        endpoint="http://test.local", username="user", password="pass",
        allow_new_channels_default=True,
    )

@pytest.fixture
def config_scoped():
    """Config with scope_to_group enabled."""
    from config.schema import MatchingConfig
    return Config(
        endpoint="http://test.local", username="user", password="pass",
        matching=MatchingConfig(scope_to_group=True),
    )


# ── Raw API response dicts ────────────────────────────────────────────────────

@pytest.fixture
def raw_streams_response():
    return {
        "results": [
            {"id": 1, "name": "CNN HD",  "m3u_account": "ProviderA", "channel_group": 5},
            {"id": 2, "name": "CNN SD",  "m3u_account": "ProviderB", "channel_group": 5},
            {"id": 3, "name": "BBC One", "m3u_account": "ProviderA", "channel_group": 5},
        ]
    }

@pytest.fixture
def raw_channels_response():
    return [
        {"id": 10, "name": "CNN",     "streams": [], "channel_group_id": 5},
        {"id": 11, "name": "BBC One", "streams": [], "channel_group_id": 5},
    ]
