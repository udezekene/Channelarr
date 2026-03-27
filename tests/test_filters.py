"""Tests for filters/lock.py, filters/allowlist.py, filters/blocklist.py."""

import pytest
from core.models import ChangeType, SkipReason, ChannelChange, ChangeSet
from core import planner
from matching.regex_match import RegexMatchStrategy
from filters import lock as lock_filter
from filters import allowlist as allowlist_filter
from filters import blocklist as blocklist_filter


@pytest.fixture
def strategy():
    return RegexMatchStrategy()


def _plan(streams, channels, config, strategy):
    return planner.plan(streams, channels, config, strategy)


# ══════════════════════════════════════════════════════════════════ Lock filter

class TestLockFilter:
    def test_locked_update_becomes_skip(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        assert cs.updates[0].change_type == ChangeType.UPDATE
        cs = lock_filter.apply(cs, locked_names=["CNN"])
        assert cs.skips[0].skip_reason == SkipReason.LOCKED

    def test_locked_create_becomes_skip(
        self, strategy, stream_unknown, channel_cnn, config_allow_create
    ):
        cs = _plan([stream_unknown], [channel_cnn], config_allow_create, strategy)
        assert cs.creates[0].change_type == ChangeType.CREATE
        cs = lock_filter.apply(cs, locked_names=["UnknownChannel"])
        assert cs.skips[0].skip_reason == SkipReason.LOCKED

    def test_locked_delete_becomes_skip(
        self, strategy, stream_bbc, channel_cnn, channel_bbc, minimal_config
    ):
        # channel_cnn has no matching stream → DELETE_NOT_PERMITTED by default
        # switch to allow_delete so planner emits DELETE, then lock it
        from config.schema import Config
        cfg = Config(endpoint="x", username="u", password="p", allow_delete_default=True)
        cs = _plan([stream_bbc], [channel_bbc, channel_cnn], cfg, strategy)
        deletes = [c for c in cs.changes if c.change_type == ChangeType.DELETE]
        assert len(deletes) == 1
        cs = lock_filter.apply(cs, locked_names=["CNN"])
        locked = [c for c in cs.changes if c.skip_reason == SkipReason.LOCKED]
        assert len(locked) == 1

    def test_non_locked_channel_untouched(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs = lock_filter.apply(cs, locked_names=["BBC One"])  # different name
        assert cs.updates[0].change_type == ChangeType.UPDATE

    def test_unlock_flag_bypasses_lock(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs = lock_filter.apply(cs, locked_names=["CNN"], unlocked_names=["CNN"])
        assert cs.updates[0].change_type == ChangeType.UPDATE

    def test_pairing_store_approval_bypasses_lock(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        from unittest.mock import MagicMock
        from core.models import SavedPairing
        store = MagicMock()
        store.get_lock_approval.return_value = SavedPairing(
            normalized_stream_name="CNN", channel_group=5,
            channel_id=10, channel_name="CNN",
            confirmed_at="2026-03-27", active=True, override_lock=True,
        )
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs = lock_filter.apply(cs, locked_names=["CNN"], pairing_store=store)
        assert cs.updates[0].change_type == ChangeType.UPDATE

    def test_empty_lock_list_is_noop(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs2 = lock_filter.apply(cs, locked_names=[])
        assert cs2.changes == cs.changes

    def test_already_skipped_change_not_overwritten(
        self, strategy, stream_unknown, channel_cnn, minimal_config
    ):
        # CREATE_NOT_PERMITTED skip should not be overwritten by lock filter
        cs = _plan([stream_unknown], [channel_cnn], minimal_config, strategy)
        assert cs.skips[0].skip_reason == SkipReason.CREATE_NOT_PERMITTED
        cs = lock_filter.apply(cs, locked_names=["UnknownChannel"])
        assert cs.skips[0].skip_reason == SkipReason.CREATE_NOT_PERMITTED


# ════════════════════════════════════════════════════════════ Allowlist filter

class TestAllowlistFilter:
    def test_channel_in_allowlist_passes_through(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs = allowlist_filter.apply(cs, allowlist=["CNN"])
        assert cs.updates[0].change_type == ChangeType.UPDATE

    def test_channel_not_in_allowlist_becomes_skip(
        self, strategy, stream_bbc, channel_bbc, minimal_config
    ):
        cs = _plan([stream_bbc], [channel_bbc], minimal_config, strategy)
        cs = allowlist_filter.apply(cs, allowlist=["CNN"])  # BBC not allowed
        assert cs.skips[0].skip_reason == SkipReason.NOT_IN_ALLOWLIST

    def test_empty_allowlist_is_noop(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs2 = allowlist_filter.apply(cs, allowlist=[])
        assert cs2.changes == cs.changes


# ════════════════════════════════════════════════════════════ Blocklist filter

class TestBlocklistFilter:
    def test_blocked_channel_becomes_skip(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs = blocklist_filter.apply(cs, blocklist=["CNN"])
        assert cs.skips[0].skip_reason == SkipReason.BLOCKED

    def test_non_blocked_channel_untouched(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs = blocklist_filter.apply(cs, blocklist=["BBC One"])
        assert cs.updates[0].change_type == ChangeType.UPDATE

    def test_empty_blocklist_is_noop(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs2 = blocklist_filter.apply(cs, blocklist=[])
        assert cs2.changes == cs.changes


# ══════════════════════════════════════════════════════════════ Filter ordering

class TestFilterOrder:
    def test_lock_runs_before_blocklist(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        """A SKIP(LOCKED) from the lock filter should not be overwritten by blocklist."""
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs = lock_filter.apply(cs, locked_names=["CNN"])
        cs = blocklist_filter.apply(cs, blocklist=["CNN"])
        # First skip reason (LOCKED) must be preserved
        assert cs.skips[0].skip_reason == SkipReason.LOCKED

    def test_blocklist_runs_before_allowlist(
        self, strategy, stream_cnn_hd, channel_cnn, minimal_config
    ):
        """A SKIP(BLOCKED) should not be overwritten by allowlist filter."""
        cs = _plan([stream_cnn_hd], [channel_cnn], minimal_config, strategy)
        cs = blocklist_filter.apply(cs, blocklist=["CNN"])
        cs = allowlist_filter.apply(cs, allowlist=["CNN"])
        assert cs.skips[0].skip_reason == SkipReason.BLOCKED
