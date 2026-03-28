"""Tests for audit/checker.py — health scan logic."""

from __future__ import annotations

from core.models import AuditReport, Channel, EpgEntry, Stream
from audit.checker import run_audit


# ── fixtures ───────────────────────────────────────────────────────────────────

def _ch(id: int, name: str, stream_ids: list[int] = (), epg_data_id: int | None = None) -> Channel:
    return Channel(
        id=id, name=name,
        stream_ids=list(stream_ids),
        channel_group_id=1,
        epg_data_id=epg_data_id,
        tvg_id=None,
        raw={},
    )


def _stream(id: int, name: str = "stream") -> Stream:
    return Stream(id=id, name=name, provider=None, channel_group=None, raw={})


def _epg(id: int) -> EpgEntry:
    return EpgEntry(id=id, tvg_id=f"tvg.{id}", name=f"EPG {id}", epg_source=1)


# ── tests ──────────────────────────────────────────────────────────────────────

def test_detects_channels_without_epg():
    channels = [
        _ch(1, "BBC One", stream_ids=[10], epg_data_id=None),   # no EPG
        _ch(2, "CNN",     stream_ids=[11], epg_data_id=99),     # has EPG
    ]
    streams = [_stream(10), _stream(11)]
    epg = [_epg(99)]

    report = run_audit(channels, streams, epg)

    assert len(report.no_epg) == 1
    assert report.no_epg[0].id == 1


def test_detects_channels_without_streams():
    channels = [
        _ch(1, "BBC One", stream_ids=[],   epg_data_id=1),   # no streams
        _ch(2, "CNN",     stream_ids=[10], epg_data_id=2),
    ]
    streams = [_stream(10)]
    epg = [_epg(1), _epg(2)]

    report = run_audit(channels, streams, epg)

    assert len(report.no_streams) == 1
    assert report.no_streams[0].id == 1


def test_detects_orphan_streams():
    channels = [_ch(1, "BBC One", stream_ids=[10], epg_data_id=1)]
    streams = [_stream(10), _stream(11), _stream(12)]   # 11 and 12 not attached
    epg = [_epg(1)]

    report = run_audit(channels, streams, epg)

    assert len(report.orphan_streams) == 2
    orphan_ids = {s.id for s in report.orphan_streams}
    assert orphan_ids == {11, 12}


def test_detects_stale_epg_references():
    channels = [
        _ch(1, "BBC One", stream_ids=[10], epg_data_id=99),   # 99 no longer in EPG data
        _ch(2, "CNN",     stream_ids=[11], epg_data_id=1),    # valid
    ]
    streams = [_stream(10), _stream(11)]
    epg = [_epg(1)]   # only id=1 exists; id=99 is gone

    report = run_audit(channels, streams, epg)

    assert len(report.stale_epg) == 1
    assert report.stale_epg[0].id == 1   # channel id=1 (BBC One) has the stale ref


def test_clean_library_returns_empty_report():
    channels = [
        _ch(1, "BBC One", stream_ids=[10], epg_data_id=1),
        _ch(2, "CNN",     stream_ids=[11], epg_data_id=2),
    ]
    streams = [_stream(10), _stream(11)]
    epg = [_epg(1), _epg(2)]

    report = run_audit(channels, streams, epg)

    assert report.is_clean
    assert not report.no_epg
    assert not report.no_streams
    assert not report.orphan_streams
    assert not report.stale_epg
