"""Tests for config/loader.py — read, write, and validation behaviour."""

import pytest
import yaml
from pathlib import Path
from config import loader
from config.schema import Config, MatchingConfig


# ──────────────────────────────────────────────────── helpers

def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f)


def _minimal_yaml(path: Path) -> None:
    _write_yaml(path, {"endpoint": "http://test.local", "username": "u", "password": "p"})


# ──────────────────────────────────────────────────── load tests

class TestLoad:
    def test_valid_yaml_all_fields(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        _write_yaml(cfg_path, {
            "endpoint": "http://host:8080",
            "username": "admin",
            "password": "secret",
            "matching": {
                "strategy": "fuzzy",
                "normalizer": "aggressive",
                "fuzzy_threshold": 0.9,
                "scope_to_group": True,
            },
            "provider_priority": ["ProviderA", "ProviderB"],
            "conflict_resolution": {"strategy": "most_recent"},
            "allow_new_channels_default": True,
            "allow_delete_default": True,
            "locks": [{"channel_name": "BBC One", "reason": "hands off"}],
            "allowlist": ["CNN"],
            "blocklist": ["Adult"],
        })

        config = loader.load(cfg_path)

        assert config.endpoint == "http://host:8080"
        assert config.username == "admin"
        assert config.matching.strategy == "fuzzy"
        assert config.matching.fuzzy_threshold == 0.9
        assert config.matching.scope_to_group is True
        assert config.provider_priority == ["ProviderA", "ProviderB"]
        assert config.conflict_resolution.strategy == "most_recent"
        assert config.allow_new_channels_default is True
        assert config.allow_delete_default is True
        assert config.locks[0].channel_name == "BBC One"
        assert config.allowlist == ["CNN"]
        assert config.blocklist == ["Adult"]

    def test_missing_optional_fields_default_to_empty(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        _minimal_yaml(cfg_path)

        config = loader.load(cfg_path)

        assert config.locks == []
        assert config.allowlist == []
        assert config.blocklist == []
        assert config.provider_priority == []

    def test_missing_required_endpoint_raises_value_error(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        _write_yaml(cfg_path, {"username": "u", "password": "p"})

        with pytest.raises(ValueError, match="endpoint"):
            loader.load(cfg_path)

    def test_unknown_fields_are_ignored(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        _write_yaml(cfg_path, {
            "endpoint": "http://test.local",
            "username": "u",
            "password": "p",
            "future_feature": "some_value",   # unknown — should not raise
            "another_unknown": [1, 2, 3],
        })

        config = loader.load(cfg_path)   # must not raise
        assert config.endpoint == "http://test.local"

    def test_file_not_found_raises_with_helpful_message(self, tmp_path):
        missing = tmp_path / "does_not_exist.yaml"

        with pytest.raises(FileNotFoundError, match="--reconfigure"):
            loader.load(missing)

    def test_matching_defaults_when_section_absent(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        _minimal_yaml(cfg_path)

        config = loader.load(cfg_path)

        assert config.matching.strategy == "regex"
        assert config.matching.normalizer == "default"
        assert config.matching.fuzzy_threshold == 0.85
        assert config.matching.scope_to_group is False


# ──────────────────────────────────────────────────── round-trip test

class TestRoundTrip:
    def test_write_then_load_returns_same_values(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        original = Config(
            endpoint="http://roundtrip.local",
            username="rt_user",
            password="rt_pass",
            matching=MatchingConfig(
                strategy="exact",
                normalizer="aggressive",
                fuzzy_threshold=0.75,
                scope_to_group=True,
            ),
            allow_new_channels_default=True,
            allow_delete_default=False,
            allowlist=["ESPN", "BBC One"],
            blocklist=["Adult Channel"],
        )

        loader.write(original, cfg_path)
        loaded = loader.load(cfg_path)

        assert loaded.endpoint == original.endpoint
        assert loaded.username == original.username
        assert loaded.matching.strategy == original.matching.strategy
        assert loaded.matching.scope_to_group == original.matching.scope_to_group
        assert loaded.matching.fuzzy_threshold == original.matching.fuzzy_threshold
        assert loaded.allow_new_channels_default == original.allow_new_channels_default
        assert loaded.allowlist == original.allowlist
        assert loaded.blocklist == original.blocklist

    def test_write_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c" / "config.yaml"
        config = Config(endpoint="http://x.local", username="u", password="p")

        loader.write(config, nested)

        assert nested.exists()
