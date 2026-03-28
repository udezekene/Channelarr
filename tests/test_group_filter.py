"""Tests for --group / --group-id channel scoping."""

from __future__ import annotations

import types
import pytest
from unittest.mock import MagicMock, patch

from core.models import Channel
import channelarr as app


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_channel(id: int, name: str, group_id: int | None) -> Channel:
    return Channel(
        id=id, name=name, stream_ids=[],
        channel_group_id=group_id, epg_data_id=None, tvg_id=None,
        raw={},
    )


def _make_args(group: str | None = None, group_id: int | None = None):
    return types.SimpleNamespace(group=group, group_id=group_id)


CHANNELS = [
    _make_channel(1, "BBC News",      group_id=20),
    _make_channel(2, "BBC Two",       group_id=10),
    _make_channel(3, "Al Jazeera",    group_id=20),
    _make_channel(4, "France 24",     group_id=30),
    _make_channel(5, "DW English",    group_id=10),
]

FAKE_GROUPS = {"Public UK": 10, "News": 20, "International": 30}


# ── tests ──────────────────────────────────────────────────────────────────────

def test_filter_by_group_id():
    """Channels outside the requested group id are excluded."""
    result = app._apply_group_filter(CHANNELS, _make_args(group_id=10))
    assert len(result) == 2
    assert all(ch.channel_group_id == 10 for ch in result)


def test_filter_by_group_name():
    """--group NAME is matched case-insensitively against the API group list."""
    client = MagicMock()
    with patch.object(app, "_fetch_channel_groups", return_value=FAKE_GROUPS):
        result = app._apply_group_filter(CHANNELS, _make_args(group="public uk"), client)
    assert len(result) == 2
    assert all(ch.channel_group_id == 10 for ch in result)


def test_no_filter_returns_all():
    """Without --group or --group-id, all channels pass through unchanged."""
    result = app._apply_group_filter(CHANNELS, _make_args())
    assert result is CHANNELS


def test_unknown_group_exits_with_error():
    """An unrecognised --group NAME prints an error and exits with code 1."""
    client = MagicMock()
    with patch.object(app, "_fetch_channel_groups", return_value=FAKE_GROUPS):
        with patch.object(app.console, "print_error") as mock_err:
            with pytest.raises(SystemExit) as exc_info:
                app._apply_group_filter(CHANNELS, _make_args(group="Documentaries"), client)

    assert exc_info.value.code == 1
    error_msg = mock_err.call_args[0][0]
    assert "Documentaries" in error_msg
