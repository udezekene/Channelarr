"""Health audit logic.

Pure function — no API calls, no I/O.  The caller fetches the data;
this module just analyses it and returns a structured report.
"""

from __future__ import annotations

from core.models import AuditReport, Channel, EpgEntry, Stream


def run_audit(
    channels: list[Channel],
    streams: list[Stream],
    epg_entries: list[EpgEntry],
) -> AuditReport:
    """Scan channels and streams for four categories of health problems.

    Categories
    ----------
    no_epg          — channel has no EPG assignment (epg_data_id is None)
    no_streams      — channel has no streams attached
    orphan_streams  — stream exists in the API but is not attached to any channel
    stale_epg       — channel's epg_data_id refers to an EPG entry that no longer exists
    """
    valid_epg_ids: set[int] = {e.id for e in epg_entries}
    attached_stream_ids: set[int] = {sid for ch in channels for sid in ch.stream_ids}

    no_epg: list[Channel] = []
    no_streams: list[Channel] = []
    stale_epg: list[Channel] = []

    for ch in channels:
        if not ch.epg_data_id:
            no_epg.append(ch)
        if not ch.stream_ids:
            no_streams.append(ch)
        if ch.epg_data_id and ch.epg_data_id not in valid_epg_ids:
            stale_epg.append(ch)

    orphan_streams = [s for s in streams if s.id not in attached_stream_ids]

    return AuditReport(
        no_epg=no_epg,
        no_streams=no_streams,
        orphan_streams=orphan_streams,
        stale_epg=stale_epg,
    )
