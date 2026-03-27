"""Pairing store — reads and writes ~/.local/share/channelarr/pairings.json.

A pairing is a user-confirmed stream→channel assignment. Once confirmed, the
planner uses it directly on future runs without prompting again.

Lock-override approvals (override_lock=True) are also stored here. The lock
filter checks this store before deciding to skip a locked channel.
"""

from __future__ import annotations
import json
from pathlib import Path
from datetime import date
from typing import Optional
from core.models import SavedPairing

DEFAULT_PAIRINGS_PATH = Path.home() / ".local" / "share" / "channelarr" / "pairings.json"


class PairingStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_PAIRINGS_PATH
        self._pairings: list[SavedPairing] = []
        self._loaded = False

    # ----------------------------------------------------------------- public

    def load(self) -> list[SavedPairing]:
        """Load pairings from disk. Returns empty list if file does not exist."""
        if not self.path.exists():
            self._loaded = True
            return []
        with open(self.path) as f:
            raw: list[dict] = json.load(f)
        self._pairings = [SavedPairing(**entry) for entry in raw]
        self._loaded = True
        return self._pairings

    def save(self, pairing: SavedPairing) -> None:
        """Add or update a pairing entry, then write to disk."""
        self._ensure_loaded()
        key = (pairing.normalized_stream_name, pairing.channel_group)
        for i, p in enumerate(self._pairings):
            if (p.normalized_stream_name, p.channel_group) == key:
                self._pairings[i] = pairing
                self._write()
                return
        self._pairings.append(pairing)
        self._write()

    def get(
        self, normalized_name: str, channel_group: Optional[int]
    ) -> SavedPairing | None:
        """Return an active non-lock-override pairing, or None."""
        self._ensure_loaded()
        for p in self._pairings:
            if (
                p.normalized_stream_name == normalized_name
                and p.channel_group == channel_group
                and p.active
                and not p.override_lock
            ):
                return p
        return None

    def get_lock_approval(self, normalized_name: str) -> SavedPairing | None:
        """Return an active lock-override approval for this channel name, or None."""
        self._ensure_loaded()
        for p in self._pairings:
            if p.normalized_stream_name == normalized_name and p.override_lock and p.active:
                return p
        return None

    def all_active(self) -> list[SavedPairing]:
        self._ensure_loaded()
        return [p for p in self._pairings if p.active]

    # --------------------------------------------------------------- private

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(
                [vars(p) for p in self._pairings],
                f, indent=2, default=str,
            )
