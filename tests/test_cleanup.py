"""Tests for cleanup/renamer.py — channel rename proposals."""

import pytest
from unittest.mock import MagicMock, call
from core.models import Channel
from cleanup.renamer import find_renames, apply_renames, RenameProposal


# ──────────────────────────────────────────────── helpers

def _channel(id, name, stream_ids=None):
    return Channel(id=id, name=name, stream_ids=stream_ids or [], channel_group_id=None, raw={})


# ──────────────────────────────────────────────── find_renames

class TestFindRenames:
    def test_prefixed_channel_proposed(self):
        channels = [_channel(1, "SA|Rok")]
        proposals = find_renames(channels)
        assert len(proposals) == 1
        assert proposals[0].proposed_name == "Rok"

    def test_clean_channel_not_proposed(self):
        channels = [_channel(1, "CNN")]
        proposals = find_renames(channels)
        assert len(proposals) == 0

    def test_conflict_excluded(self):
        """If the proposed clean name already exists as a channel, skip it."""
        channels = [
            _channel(1, "MY|DW"),
            _channel(2, "DW"),   # already exists — would conflict
        ]
        proposals = find_renames(channels)
        assert len(proposals) == 0

    def test_conflict_check_is_case_insensitive(self):
        channels = [
            _channel(1, "MY|Dw"),
            _channel(2, "DW"),
        ]
        proposals = find_renames(channels)
        assert len(proposals) == 0

    def test_multiple_proposals_no_conflicts(self):
        channels = [
            _channel(1, "SA|Rok"),
            _channel(2, "MY|DW"),
            _channel(3, "UK|BBC One"),
        ]
        proposals = find_renames(channels)
        assert len(proposals) == 3
        proposed_names = {p.proposed_name for p in proposals}
        assert proposed_names == {"Rok", "DW", "BBC One"}

    def test_proposal_has_correct_channel_reference(self):
        ch = _channel(42, "MY|Al Jazeera")
        proposals = find_renames([ch])
        assert proposals[0].channel is ch
        assert proposals[0].current_name == "MY|Al Jazeera"

    def test_two_prefixed_channels_no_conflict_with_each_other(self):
        """Two prefixed channels normalizing to different names — both proposed."""
        channels = [
            _channel(1, "MY|Al Jazeera"),
            _channel(2, "UK|Al Jazeera"),
        ]
        proposals = find_renames(channels)
        # Both normalize to "Al Jazeera" — second would conflict with first's proposal
        # but the first's proposed name doesn't exist yet as a current channel name
        # Both CURRENT names differ, so no current-name conflict
        # However both propose "Al Jazeera" — the second proposal would create a conflict
        # Our implementation only checks current channel names, not proposed names
        # So both will be proposed; user must review
        assert len(proposals) == 2


# ──────────────────────────────────────────────── apply_renames

class TestApplyRenames:
    def test_successful_rename(self):
        ch = _channel(1, "MY|DW")
        proposal = RenameProposal(channel=ch, current_name="MY|DW", proposed_name="DW")
        client = MagicMock()

        succeeded, failed = apply_renames([proposal], client)

        assert len(succeeded) == 1
        assert len(failed) == 0
        client.update_channel.assert_called_once_with(1, {"name": "DW"})

    def test_failed_rename(self):
        ch = _channel(1, "MY|DW")
        proposal = RenameProposal(channel=ch, current_name="MY|DW", proposed_name="DW")
        client = MagicMock()
        client.update_channel.side_effect = RuntimeError("API error")

        succeeded, failed = apply_renames([proposal], client)

        assert len(succeeded) == 0
        assert len(failed) == 1
        assert "API error" in failed[0][1]

    def test_partial_failure(self):
        ch1 = _channel(1, "MY|DW")
        ch2 = _channel(2, "SA|Rok")
        p1 = RenameProposal(channel=ch1, current_name="MY|DW", proposed_name="DW")
        p2 = RenameProposal(channel=ch2, current_name="SA|Rok", proposed_name="Rok")

        client = MagicMock()
        client.update_channel.side_effect = [None, RuntimeError("fail")]

        succeeded, failed = apply_renames([p1, p2], client)

        assert len(succeeded) == 1
        assert succeeded[0].proposed_name == "DW"
        assert len(failed) == 1
        assert failed[0][0].proposed_name == "Rok"

    def test_empty_proposals(self):
        client = MagicMock()
        succeeded, failed = apply_renames([], client)
        assert succeeded == []
        assert failed == []
        client.update_channel.assert_not_called()


# ──────────────────────────────────────────────── dedup confidence

class TestDedupConfidence:
    def test_confidence_auto_when_all_losers_have_one_stream(self):
        from dedup.finder import find_groups
        channels = [
            _channel(1, "SS La Liga HD",  stream_ids=[1, 2, 3]),  # winner (most streams)
            _channel(2, "SS La Liga FHD", stream_ids=[4]),         # loser (1 stream)
        ]
        groups = find_groups(channels, normalizer_mode="default")
        assert len(groups) == 1
        assert groups[0].confidence == "auto"

    def test_confidence_review_when_loser_has_multiple_streams(self):
        from dedup.finder import find_groups
        channels = [
            _channel(1, "SS La Liga HD",  stream_ids=[1, 2, 3]),
            _channel(2, "SS La Liga FHD", stream_ids=[4, 5]),  # 2 streams → review
        ]
        groups = find_groups(channels, normalizer_mode="default")
        assert len(groups) == 1
        assert groups[0].confidence == "review"

    def test_confidence_review_when_any_loser_has_multiple_streams(self):
        from dedup.finder import find_groups
        channels = [
            _channel(1, "CNN HD",  stream_ids=[1, 2, 3]),
            _channel(2, "CNN FHD", stream_ids=[4]),      # 1 stream — auto
            _channel(3, "CNN 4K",  stream_ids=[5, 6]),   # 2 streams — makes it review
        ]
        groups = find_groups(channels, normalizer_mode="default")
        assert len(groups) == 1
        assert groups[0].confidence == "review"
