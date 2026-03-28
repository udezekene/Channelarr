"""Tests for core/normalizer.py — default normalization mode."""

import pytest
from core.normalizer import normalize


class TestDefaultNormalizer:
    def test_strips_trailing_hd(self):
        assert normalize("CNN HD") == "CNN"

    def test_strips_trailing_sd(self):
        assert normalize("BBC One SD") == "BBC One"

    def test_strips_trailing_fhd(self):
        assert normalize("BBC Two FHD") == "BBC Two"

    def test_strips_trailing_uhd(self):
        assert normalize("Al Jazeera UHD") == "Al Jazeera"

    def test_strips_trailing_4k(self):
        assert normalize("DW 4K") == "DW"

    def test_strips_multiple_trailing_tokens(self):
        assert normalize("ITV HD SD") == "ITV"

    def test_strips_bracketed_sd(self):
        assert normalize("BBC One [SD]") == "BBC One"

    def test_strips_parenthesised_uhd(self):
        assert normalize("4K Sport (UHD)") == "4K Sport"

    def test_does_not_strip_leading_4k(self):
        # "4K" at the start of a name is part of the name, not a suffix
        assert normalize("4K Sport") == "4K Sport"

    def test_trims_whitespace(self):
        assert normalize("   BBC News  ") == "BBC News"

    def test_empty_string_is_safe(self):
        assert normalize("") == ""

    def test_no_suffix_unchanged(self):
        assert normalize("CNN") == "CNN"

    def test_case_insensitive_stripping(self):
        assert normalize("CNN hd") == "CNN"
        assert normalize("BBC [sd]") == "BBC"


class TestNoneMode:
    def test_no_suffix_stripped(self):
        assert normalize("CNN HD", mode="none") == "CNN HD"

    def test_whitespace_still_trimmed(self):
        assert normalize("  CNN  ", mode="none") == "CNN"

    def test_brackets_not_stripped(self):
        assert normalize("BBC [SD]", mode="none") == "BBC [SD]"


class TestUnknownModeFallsBackToDefault:
    def test_unknown_mode_uses_default(self):
        # Unknown modes should not crash; they fall back to default behavior
        assert normalize("CNN HD", mode="bogus") == "CNN"
