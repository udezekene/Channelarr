"""Append-only run history stored as JSON lines.

Each line in history.jsonl is one complete run entry (as produced by
run_logger.build_entry). Existing entries are never modified or deleted.
"""

from __future__ import annotations
import json
from pathlib import Path

DEFAULT_HISTORY_PATH = Path.home() / ".local" / "share" / "channelarr" / "history.jsonl"


def append(entry: dict, path: Path | None = None) -> None:
    """Append one run entry to the history file.

    Creates the file (and parent directories) if they do not exist.
    Never modifies existing lines.
    """
    history_path = path or DEFAULT_HISTORY_PATH
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load(path: Path | None = None) -> list[dict]:
    """Return all history entries, oldest first.

    Returns an empty list if the file does not exist.
    Silently skips any lines that are not valid JSON.
    """
    history_path = path or DEFAULT_HISTORY_PATH
    if not history_path.exists():
        return []

    entries: list[dict] = []
    with open(history_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries
