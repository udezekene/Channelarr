"""Executor: applies a ChangeSet to the Dispatcharr API.

This is the ONLY module that writes to the API. It is never called during
a dry-run — the gate that guards it lives in channelarr.py.

The executor makes no decisions. If a CREATE reaches it, it creates. All
decisions were already made by the planner and any filters.
"""

from __future__ import annotations
from core.models import ChangeSet, ChangeType, AppliedChange, RunResult, ChannelChange
from api.client import APIClient
from api import endpoints


def apply(changeset: ChangeSet, client: APIClient) -> RunResult:
    """Walk changeset.changes and apply every non-SKIP change via the API."""
    result = RunResult(dry_run=False, total_evaluated=len(changeset.changes))

    for change in changeset.changes:
        if change.change_type == ChangeType.SKIP:
            result.applied.append(AppliedChange(change=change, success=True))
            continue

        try:
            if change.change_type == ChangeType.UPDATE:
                _do_update(change, client)

            elif change.change_type == ChangeType.CREATE:
                _do_create(change, client)

            elif change.change_type == ChangeType.DELETE:
                assert change.channel is not None
                client.delete(f"{endpoints.CHANNELS}{change.channel.id}/")

            result.applied.append(AppliedChange(change=change, success=True))

        except Exception as exc:
            result.applied.append(AppliedChange(change=change, success=False, error=str(exc)))

    return result


def _do_update(change: ChannelChange, client: APIClient) -> None:
    assert change.channel is not None
    stream_ids = [m.stream.id for m in change.candidates]
    # Merge into .raw so we preserve any API fields added in future Dispatcharr versions
    payload = {**change.channel.raw, "streams": stream_ids}
    client.put(f"{endpoints.CHANNELS}{change.channel.id}/", json=payload)


def _do_create(change: ChannelChange, client: APIClient) -> None:
    assert change.winning_match is not None
    first_stream = change.candidates[0].stream

    # Step 1: create the channel from the first stream
    created: dict = client.post(endpoints.CREATE_FROM_STREAM, json={
        "name": change.winning_match.normalized_stream_name,
        "stream_id": first_stream.id,
    })
    channel_id = created["id"]

    # Step 2: update the new channel with all matching streams
    stream_ids = [m.stream.id for m in change.candidates]
    payload = {**created, "streams": stream_ids}
    client.put(f"{endpoints.CHANNELS}{channel_id}/", json=payload)
