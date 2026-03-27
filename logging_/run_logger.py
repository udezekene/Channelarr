"""Builds structured run-log entries.

A run entry is a plain dict that can be serialised to JSON.
It is written to history.jsonl by logging_/history.py.
"""

from __future__ import annotations
from datetime import datetime, timezone
from core.models import ChangeSet, RunResult


def build_entry(
    changeset: ChangeSet,
    result: RunResult | None,
    *,
    dry_run: bool,
) -> dict:
    """Return a JSON-serialisable dict summarising one Channelarr run."""
    entry: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "planned": {
            "creates": len(changeset.creates),
            "updates": len(changeset.updates),
            "deletes": len(changeset.deletes),
            "skips":   len(changeset.skips),
            "total":   len(changeset.changes),
        },
    }

    if result is not None:
        entry["applied"] = {
            "succeeded": len(result.succeeded),
            "failed":    len(result.failed),
            "errors": [a.error for a in result.failed if a.error],
        }

    return entry
