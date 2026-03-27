"""Tests for pairings/store.py and planner integration with saved pairings."""

import json
import pytest
from pathlib import Path
from datetime import date
from core.models import SavedPairing
from pairings.store import PairingStore
from core import planner
from matching.regex_match import RegexMatchStrategy
from config.schema import Config


def _pairing(name="CNN", group=5, channel_id=10, channel_name="CNN",
             active=True, override_lock=False) -> SavedPairing:
    return SavedPairing(
        normalized_stream_name=name,
        channel_group=group,
        channel_id=channel_id,
        channel_name=channel_name,
        confirmed_at=str(date.today()),
        active=active,
        override_lock=override_lock,
    )


# ═══════════════════════════════════════════════════════════════ Store CRUD

class TestPairingStore:
    def test_save_and_load(self, tmp_path):
        store = PairingStore(path=tmp_path / "pairings.json")
        p = _pairing()
        store.save(p)

        store2 = PairingStore(path=tmp_path / "pairings.json")
        loaded = store2.load()
        assert len(loaded) == 1
        assert loaded[0].normalized_stream_name == "CNN"

    def test_save_same_key_updates_not_duplicates(self, tmp_path):
        store = PairingStore(path=tmp_path / "pairings.json")
        store.save(_pairing(channel_name="CNN v1"))
        store.save(_pairing(channel_name="CNN v2"))

        store2 = PairingStore(path=tmp_path / "pairings.json")
        loaded = store2.load()
        assert len(loaded) == 1
        assert loaded[0].channel_name == "CNN v2"

    def test_missing_file_returns_empty(self, tmp_path):
        store = PairingStore(path=tmp_path / "pairings.json")
        result = store.load()
        assert result == []

    def test_get_returns_active_pairing(self, tmp_path):
        store = PairingStore(path=tmp_path / "pairings.json")
        store.save(_pairing())
        assert store.get("CNN", 5) is not None

    def test_get_ignores_inactive_pairing(self, tmp_path):
        store = PairingStore(path=tmp_path / "pairings.json")
        store.save(_pairing(active=False))
        assert store.get("CNN", 5) is None

    def test_get_lock_approval_returns_override_pairing(self, tmp_path):
        store = PairingStore(path=tmp_path / "pairings.json")
        store.save(_pairing(override_lock=True))
        assert store.get_lock_approval("CNN") is not None

    def test_get_lock_approval_ignores_normal_pairings(self, tmp_path):
        store = PairingStore(path=tmp_path / "pairings.json")
        store.save(_pairing(override_lock=False))
        assert store.get_lock_approval("CNN") is None


# ═══════════════════════════════════════════════════════ Planner integration

class TestPlannerWithPairingStore:
    def test_saved_pairing_bypasses_strategy(
        self, tmp_path, stream_cnn_hd, channel_bbc, channel_cnn, minimal_config
    ):
        """Planner should use the saved pairing and NOT match CNN HD → BBC One."""
        store = PairingStore(path=tmp_path / "pairings.json")
        store.save(_pairing(name="CNN", group=5, channel_id=channel_cnn.id))

        strategy = RegexMatchStrategy()
        cs = planner.plan(
            [stream_cnn_hd], [channel_bbc, channel_cnn],
            minimal_config, strategy, pairing_store=store,
        )
        updates = cs.updates
        assert len(updates) == 1
        assert updates[0].channel == channel_cnn
        assert updates[0].winning_match.match_type.value == "saved"

    def test_inactive_pairing_falls_through_to_strategy(
        self, tmp_path, stream_cnn_hd, channel_cnn, minimal_config
    ):
        store = PairingStore(path=tmp_path / "pairings.json")
        store.save(_pairing(active=False))

        strategy = RegexMatchStrategy()
        cs = planner.plan(
            [stream_cnn_hd], [channel_cnn],
            minimal_config, strategy, pairing_store=store,
        )
        assert cs.updates[0].winning_match.match_type == from_value("regex")

    def test_no_pairings_file_runs_normally(
        self, tmp_path, stream_cnn_hd, channel_cnn, minimal_config
    ):
        store = PairingStore(path=tmp_path / "pairings.json")  # file doesn't exist yet
        strategy = RegexMatchStrategy()
        cs = planner.plan(
            [stream_cnn_hd], [channel_cnn],
            minimal_config, strategy, pairing_store=store,
        )
        assert len(cs.updates) == 1


def from_value(val):
    from core.models import MatchType
    return MatchType(val)
