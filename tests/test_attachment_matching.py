"""Tests for attachment-based matching in core/planner.py.

Attachment matching: a stream whose normalized name matches the normalized name
of a stream already attached to a channel → assigned to that channel, regardless
of the channel's own name.

Priority order tested here:
    pairing store > attachment index > name strategy
"""

import pytest
from core.models import Stream, Channel, MatchType
from core import planner
from matching.regex_match import RegexMatchStrategy
from config.schema import Config


# ──────────────────────────────────────────────── helpers

def _config():
    return Config(endpoint="http://test.local", username="u", password="p")

def _config_aggressive():
    from config.schema import MatchingConfig
    return Config(
        endpoint="http://test.local", username="u", password="p",
        matching=MatchingConfig(normalizer="aggressive"),
    )

def _stream(id, name, provider=None, group=None):
    return Stream(id=id, name=name, provider=provider, channel_group=group, raw={})

def _channel(id, name, stream_ids=None, group=None):
    return Channel(id=id, name=name, stream_ids=stream_ids or [], channel_group_id=group, raw={})


# ──────────────────────────────────────────────── attachment index

class TestAttachmentIndex:
    def test_new_stream_matches_via_attached_stream(self):
        """A new stream from a second provider matches a channel because a stream
        with the same normalized name is already attached to it."""
        existing_stream = _stream(id=1, name="CNN HD", provider="ProviderA")
        new_stream     = _stream(id=2, name="CNN HD", provider="ProviderB")
        channel        = _channel(id=10, name="CNN", stream_ids=[1])  # existing attached

        strategy = RegexMatchStrategy()
        cs = planner.plan([existing_stream, new_stream], [channel], _config(), strategy)

        update = cs.updates
        assert len(update) == 1
        assert update[0].channel == channel
        assert len(update[0].candidates) == 2  # both streams grouped together

    def test_attachment_match_type_is_attachment(self):
        """The winning match for an attachment-matched stream has MatchType.ATTACHMENT."""
        existing = _stream(id=1, name="CNN HD", provider="ProviderA")
        new      = _stream(id=2, name="CNN HD", provider="ProviderB")
        channel  = _channel(id=10, name="CNN", stream_ids=[1])

        strategy = RegexMatchStrategy()
        # Both streams must be in the list so the existing one is resolvable in the index
        cs = planner.plan([existing, new], [channel], _config(), strategy)

        assert cs.updates[0].winning_match.match_type == MatchType.ATTACHMENT

    def test_attachment_beats_channel_name_mismatch(self):
        """Even when the stream name doesn't match the channel name after normalization,
        attachment wins because the stream is already there."""
        # Channel is named "Premier League TV" — but the attached stream is
        # "Region | Premier League TV". A new stream "Region | Premier League TV" from
        # ProviderB should still find the right channel via attachment.
        existing = _stream(id=1, name="Region | Premier League TV", provider="ProviderA")
        new_provider_b  = _stream(id=2, name="Region | Premier League TV", provider="ProviderB")
        channel  = _channel(id=10, name="Premier League TV", stream_ids=[1])

        strategy = RegexMatchStrategy()  # default normalizer — "Region | PLT" ≠ "PLT"
        cs = planner.plan([existing, new_provider_b], [channel], _config(), strategy)

        assert len(cs.updates) == 1
        assert cs.updates[0].channel == channel
        assert len(cs.updates[0].candidates) == 2

    def test_aggressive_normalizer_in_attachment_index(self):
        """With the aggressive normalizer, 'Region | Channel X HD' and 'Channel X HD'
        both normalize to 'Channel X' and are grouped on the same channel."""
        existing = _stream(id=1, name="Region | Channel X HD", provider="ProviderA")
        new_provider_b  = _stream(id=2, name="Channel X HD",      provider="ProviderB")
        channel  = _channel(id=10, name="Channel X", stream_ids=[1])

        strategy = RegexMatchStrategy(normalizer_mode="aggressive")
        cs = planner.plan([existing, new_provider_b], [channel], _config_aggressive(), strategy)

        assert len(cs.updates) == 1
        assert cs.updates[0].channel == channel
        assert len(cs.updates[0].candidates) == 2

    def test_unattached_channel_falls_through_to_name_strategy(self):
        """A channel with no attached streams is not in the index — name matching
        still works as before."""
        stream  = _stream(id=1, name="CNN HD", provider="ProviderA")
        channel = _channel(id=10, name="CNN", stream_ids=[])  # nothing attached

        strategy = RegexMatchStrategy()
        cs = planner.plan([stream], [channel], _config(), strategy)

        assert len(cs.updates) == 1
        assert cs.updates[0].channel == channel
        assert cs.updates[0].winning_match.match_type == MatchType.REGEX

    def test_poisoned_index_rejected_by_token_overlap_guard(self):
        """A mis-assigned stream from a previous bad run does NOT poison the index.

        If 'UK-Sky Witness' was mistakenly attached to 'Now HK Premier Sports 7',
        the token overlap guard ('uk-sky'/'witness' vs 'now'/'hk'/'premier'/'sports')
        finds zero overlap and rejects that entry from the index. A new 'UK-Sky Witness'
        stream therefore does NOT get routed to the HK channel.
        """
        bad_stream   = _stream(id=1, name="UK-Sky Witness", provider="ProviderA")   # mis-attached
        new_stream   = _stream(id=2, name="UK-Sky Witness", provider="ProviderB")   # new stream
        hk_channel   = _channel(id=10, name="Now HK Premier Sports 7", stream_ids=[1])

        strategy = RegexMatchStrategy()
        cs = planner.plan([bad_stream, new_stream], [hk_channel], _config(), strategy)

        # Nothing should be an UPDATE for hk_channel with both streams
        # (names don't match the channel name, so they should be CREATE or SKIP)
        for change in cs.updates:
            assert change.channel != hk_channel, (
                "UK-Sky Witness should not be matched to Now HK Premier Sports 7"
            )

    def test_stream_not_in_global_list_skipped_in_index(self):
        """A stream_id in channel.stream_ids that doesn't exist in the global streams
        list is silently ignored — no error, no phantom entry in the index."""
        stream  = _stream(id=1, name="CNN HD", provider="ProviderA")
        # channel references stream id=999 which doesn't exist in the streams list
        channel = _channel(id=10, name="CNN", stream_ids=[999])

        strategy = RegexMatchStrategy()
        cs = planner.plan([stream], [channel], _config(), strategy)

        # Falls through to name matching — should still work
        assert len(cs.updates) == 1
        assert cs.updates[0].winning_match.match_type == MatchType.REGEX

    def test_two_providers_same_channel_both_added(self):
        """Streams from two different providers that both normalize to the same name
        are grouped onto the same channel as multiple candidates."""
        provider_a_stream = _stream(id=1, name="ESPN HD", provider="ProviderA")
        provider_b_stream = _stream(id=2, name="ESPN HD", provider="ProviderB")
        channel    = _channel(id=10, name="ESPN", stream_ids=[1])

        strategy = RegexMatchStrategy()
        cs = planner.plan([provider_a_stream, provider_b_stream], [channel], _config(), strategy)

        assert len(cs.updates) == 1
        assert len(cs.updates[0].candidates) == 2
        providers = {m.stream.provider for m in cs.updates[0].candidates}
        assert providers == {"ProviderA", "ProviderB"}


# ──────────────────────────────────────────────── priority order

class TestMatchPriority:
    def test_pairing_store_beats_attachment(self):
        """A saved pairing always wins, even if the attachment index would point elsewhere."""
        from pairings.store import PairingStore
        from datetime import date
        from core.models import SavedPairing
        import tempfile, pathlib

        existing = _stream(id=1, name="CNN HD", provider="ProviderA")
        new      = _stream(id=2, name="CNN HD", provider="ProviderB")
        channel_a = _channel(id=10, name="CNN",     stream_ids=[1])
        channel_b = _channel(id=20, name="CNN Copy", stream_ids=[])

        with tempfile.TemporaryDirectory() as tmp:
            store = PairingStore(path=pathlib.Path(tmp) / "pairings.json")
            store.save(SavedPairing(
                normalized_stream_name="CNN",  # "CNN HD" normalizes to "CNN"
                channel_group=None,
                channel_id=channel_b.id,       # pairing points to channel_b
                channel_name="CNN Copy",
                confirmed_at=str(date.today()),
            ))

            strategy = RegexMatchStrategy()
            cs = planner.plan(
                [new], [channel_a, channel_b], _config(), strategy,
                pairing_store=store,
            )

        # Pairing store wins over attachment index
        update = cs.updates
        assert len(update) == 1
        assert update[0].channel == channel_b
        assert update[0].winning_match.match_type == MatchType.SAVED
