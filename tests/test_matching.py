"""Tests for all three matching strategies and the aggressive normalizer."""

import pytest
from core.models import Stream, Channel, MatchType
from core import normalizer
from matching.regex_match import RegexMatchStrategy
from matching.exact import ExactMatchStrategy
from matching.fuzzy import FuzzyMatchStrategy


# ──────────────────────────────────────────────── shared fixtures

@pytest.fixture
def channel_cnn():
    return Channel(id=1, name="CNN", stream_ids=[], channel_group_id=None, raw={})

@pytest.fixture
def channel_bbc():
    return Channel(id=2, name="BBC One", stream_ids=[], channel_group_id=None, raw={})

@pytest.fixture
def stream_cnn_hd():
    return Stream(id=1, name="CNN HD", provider=None, channel_group=None, raw={})

@pytest.fixture
def stream_cnn_exact():
    return Stream(id=2, name="CNN", provider=None, channel_group=None, raw={})

@pytest.fixture
def stream_cnn_lower():
    return Stream(id=3, name="cnn", provider=None, channel_group=None, raw={})

@pytest.fixture
def stream_bbc_typo():
    # One character different — useful for fuzzy boundary tests
    return Stream(id=4, name="BBC On", provider=None, channel_group=None, raw={})

@pytest.fixture
def stream_bbc_exact():
    return Stream(id=5, name="BBC One", provider=None, channel_group=None, raw={})

@pytest.fixture
def stream_unrelated():
    return Stream(id=9, name="Sky Sports", provider=None, channel_group=None, raw={})


# ──────────────────────────────────────────────── aggressive normalizer

class TestAggressiveNormalizer:
    def test_strips_pipe_prefix(self):
        assert normalizer.normalize("MY | CNN HD", "aggressive") == "CNN"

    def test_strips_pipe_prefix_no_spaces(self):
        assert normalizer.normalize("MY|CNN", "aggressive") == "CNN"

    def test_strips_colon_prefix(self):
        assert normalizer.normalize("US: NBC", "aggressive") == "NBC"

    def test_strips_bracket_prefix(self):
        assert normalizer.normalize("[UK] BBC One HD", "aggressive") == "BBC One"

    def test_strips_dash_prefix(self):
        assert normalizer.normalize("UK - BBC One", "aggressive") == "BBC One"

    def test_strips_multiple_prefixes(self):
        # e.g. "[MY] MY | CNN HD" — both bracket and pipe prefix
        assert normalizer.normalize("[MY] MY | CNN HD", "aggressive") == "CNN"

    def test_no_prefix_unchanged_aside_from_default_rules(self):
        assert normalizer.normalize("BBC One HD", "aggressive") == "BBC One"

    def test_empty_string_safe(self):
        assert normalizer.normalize("", "aggressive") == ""

    def test_does_not_strip_channel_name_without_separator(self):
        # "ESPN" alone has no separator — must NOT be stripped
        assert normalizer.normalize("ESPN HD", "aggressive") == "ESPN"


# ──────────────────────────────────────────────── regex strategy

class TestRegexMatchStrategy:
    def test_normalized_names_match(self, stream_cnn_hd, channel_cnn):
        strategy = RegexMatchStrategy()
        result = strategy.find_match(stream_cnn_hd, [channel_cnn])
        assert result.channel == channel_cnn
        assert result.match_type == MatchType.REGEX
        assert result.score == 1.0

    def test_names_differ_after_normalization_no_match(self, stream_unrelated, channel_cnn):
        strategy = RegexMatchStrategy()
        result = strategy.find_match(stream_unrelated, [channel_cnn])
        assert result.channel is None
        assert result.match_type == MatchType.NONE

    def test_match_is_case_insensitive(self, stream_cnn_lower, channel_cnn):
        # "cnn" should match "CNN" after normalization
        strategy = RegexMatchStrategy()
        result = strategy.find_match(stream_cnn_lower, [channel_cnn])
        assert result.channel == channel_cnn

    def test_aggressive_normalizer_strips_prefix(self, channel_cnn):
        stream = Stream(id=10, name="MY | CNN HD", provider=None, channel_group=None, raw={})
        strategy = RegexMatchStrategy(normalizer_mode="aggressive")
        result = strategy.find_match(stream, [channel_cnn])
        assert result.channel == channel_cnn

    def test_no_shared_state_between_instances(self, stream_cnn_hd, channel_cnn):
        s1 = RegexMatchStrategy()
        s2 = RegexMatchStrategy(normalizer_mode="none")
        r1 = s1.find_match(stream_cnn_hd, [channel_cnn])
        r2 = s2.find_match(stream_cnn_hd, [channel_cnn])
        # s1 normalizes "CNN HD" → "CNN" → matches; s2 keeps "CNN HD" → no match
        assert r1.channel == channel_cnn
        assert r2.channel is None


# ──────────────────────────────────────────────── exact strategy

class TestExactMatchStrategy:
    def test_identical_names_match(self, stream_cnn_exact, channel_cnn):
        strategy = ExactMatchStrategy()
        result = strategy.find_match(stream_cnn_exact, [channel_cnn])
        assert result.channel == channel_cnn
        assert result.match_type == MatchType.EXACT
        assert result.score == 1.0

    def test_one_char_different_no_match(self, channel_cnn):
        stream = Stream(id=1, name="CCN", provider=None, channel_group=None, raw={})
        strategy = ExactMatchStrategy()
        result = strategy.find_match(stream, [channel_cnn])
        assert result.channel is None

    def test_case_insensitive(self, stream_cnn_lower, channel_cnn):
        strategy = ExactMatchStrategy()
        result = strategy.find_match(stream_cnn_lower, [channel_cnn])
        assert result.channel == channel_cnn

    def test_quality_suffix_prevents_match(self, stream_cnn_hd, channel_cnn):
        # "CNN HD" != "CNN" — exact strategy does NOT strip suffixes
        strategy = ExactMatchStrategy()
        result = strategy.find_match(stream_cnn_hd, [channel_cnn])
        assert result.channel is None

    def test_no_shared_state_with_regex(self, stream_cnn_hd, channel_cnn):
        regex = RegexMatchStrategy()
        exact = ExactMatchStrategy()
        assert regex.find_match(stream_cnn_hd, [channel_cnn]).channel == channel_cnn
        assert exact.find_match(stream_cnn_hd, [channel_cnn]).channel is None


# ──────────────────────────────────────────────── fuzzy strategy

class TestFuzzyMatchStrategy:
    def test_above_threshold_matches(self, stream_bbc_exact, channel_bbc):
        strategy = FuzzyMatchStrategy(threshold=0.85)
        result = strategy.find_match(stream_bbc_exact, [channel_bbc])
        assert result.channel == channel_bbc
        assert result.match_type == MatchType.FUZZY
        assert result.score == 1.0

    def test_score_at_threshold_matches(self, channel_bbc):
        # "BBC On" vs "BBC One" — compute expected score and set threshold just at it
        from rapidfuzz import fuzz
        raw = fuzz.ratio("bbc on", "bbc one")
        score = raw / 100.0
        stream = Stream(id=1, name="BBC On", provider=None, channel_group=None, raw={})
        strategy = FuzzyMatchStrategy(threshold=score)  # exact boundary — should match
        result = strategy.find_match(stream, [channel_bbc])
        assert result.channel == channel_bbc

    def test_below_threshold_no_match(self, channel_bbc):
        # Set threshold impossibly high so nothing matches
        stream = Stream(id=1, name="BBC On", provider=None, channel_group=None, raw={})
        strategy = FuzzyMatchStrategy(threshold=0.99)
        result = strategy.find_match(stream, [channel_bbc])
        assert result.channel is None

    def test_best_scoring_channel_wins(self, channel_cnn, channel_bbc):
        # "BBC One" should score higher against channel_bbc than channel_cnn
        stream = Stream(id=1, name="BBC One HD", provider=None, channel_group=None, raw={})
        strategy = FuzzyMatchStrategy(threshold=0.5)
        result = strategy.find_match(stream, [channel_cnn, channel_bbc])
        assert result.channel == channel_bbc

    def test_completely_unrelated_no_match(self, stream_unrelated, channel_cnn):
        strategy = FuzzyMatchStrategy(threshold=0.85)
        result = strategy.find_match(stream_unrelated, [channel_cnn])
        assert result.channel is None

    def test_no_shared_state_between_strategies(self, stream_bbc_exact, channel_bbc):
        exact = ExactMatchStrategy()
        fuzzy = FuzzyMatchStrategy(threshold=0.5)
        # Both should find the match independently
        assert exact.find_match(stream_bbc_exact, [channel_bbc]).channel == channel_bbc
        assert fuzzy.find_match(stream_bbc_exact, [channel_bbc]).channel == channel_bbc
