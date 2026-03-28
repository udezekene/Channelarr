"""EPG auto-assignment logic.

Flow
----
1.  Fetch all EPG entries from /api/epg/epgdata/ (paginated).
2.  Fetch EPG sources, build a provider-name → source-id map so that a
    channel whose #1 stream comes from a given M3U provider can prefer that
    provider's EPG source over others.
3.  For each channel group, inspect the tvg_id suffix of already-assigned
    channels (e.g. ".za", ".uk") to establish a regional pattern.
4.  For each unassigned channel, narrow the candidate pool using:
      a) preferred source(s) from the channel's #1 stream provider
      b) group suffix pattern (if ≥60 % of assigned siblings share one)
    Then pick the best name-similarity match from that pool.
5.  Return sorted proposals — caller decides whether to apply or just display.

This module is pure (no API calls except the two fetch helpers).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from core.models import Channel, EpgEntry, EpgProposal, Stream
from core.normalizer import normalize as _normalize_fn
from api import endpoints

if TYPE_CHECKING:
    from api.client import APIClient

# Per-method minimum confidence floors.
# Methods with a regional anchor (suffix) can afford lower floors because
# false positives from other regions are already excluded.
# Methods without a regional anchor need higher floors to reduce noise.
METHOD_MIN_CONFIDENCE: dict[str, float] = {
    "provider+suffix": 0.40,
    "suffix":          0.55,
    "provider":        0.65,
    "name_only":       0.75,
}

# Minimum fraction of assigned siblings that must share a suffix for it to
# be used as the group's regional pattern.
SUFFIX_THRESHOLD = 0.60

# Tokens too common to serve as a meaningful match signal on their own.
# If the channel's only distinctive token is one of these, any match is noise.
_STOP_WORDS: frozenset[str] = frozenset({
    "tv", "hd", "fhd", "uhd", "sd", "hevc", "the", "a", "an", "and", "or",
    "channel", "live", "plus", "network", "news", "sport", "sports", "cinema",
    "kids", "music", "movies", "radio",
})


# ────────────────────────────────────────────────────── fetch helpers ──────


def _is_dummy(tvg_id: str, name: str) -> bool:
    return tvg_id.lower().startswith("dummy-") or name.lower().startswith("dummy-")


def _parse_epg_batch(data: dict | list) -> list[EpgEntry]:
    raw = data.get("results", data) if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    return [
        EpgEntry(
            id=item["id"],
            tvg_id=item.get("tvg_id", ""),
            name=item.get("name", ""),
            epg_source=item.get("epg_source", 0),
        )
        for item in raw
        if isinstance(item, dict) and "id" in item and "tvg_id" in item
        and not _is_dummy(item.get("tvg_id", ""), item.get("name", ""))
    ]


def iter_epg_entries(client: "APIClient", max_workers: int = 8):
    """Yield (batch: list[EpgEntry], total: int | None) as pages arrive.

    Fetches page 1 first to learn the total, then fires all remaining pages
    in parallel.  Batches arrive out of order but that doesn't matter for
    our use case.
    """
    import math
    import concurrent.futures

    page_size = 2500

    # Page 1 first — tells us total count so we can parallelise the rest
    first_data = client.get(endpoints.EPG_DATA, params={"page_size": page_size, "page": 1})
    total = first_data.get("count") if isinstance(first_data, dict) else None
    first_batch = _parse_epg_batch(first_data)
    yield first_batch, total

    if not total or len(first_batch) >= total:
        return

    remaining_pages = range(2, math.ceil(total / page_size) + 1)

    def _fetch_page(page: int) -> list[EpgEntry]:
        data = client.get(endpoints.EPG_DATA, params={"page_size": page_size, "page": page})
        return _parse_epg_batch(data)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_page, p): p for p in remaining_pages}
        for future in concurrent.futures.as_completed(futures):
            yield future.result(), total


def fetch_epg_entries(client: "APIClient") -> list[EpgEntry]:
    """Convenience wrapper — fetches all pages with no progress reporting."""
    entries: list[EpgEntry] = []
    for batch, _ in iter_epg_entries(client):
        entries.extend(batch)
    return entries


def fetch_epg_sources(client: "APIClient") -> list[dict]:
    """Return raw EPG source dicts from /api/epg/sources/."""
    data = client.get(endpoints.EPG_SOURCES, params={"page_size": 100})
    raw = data.get("results", data) if isinstance(data, dict) else data
    return raw if isinstance(raw, list) else []


# ─────────────────────────────────────────────── provider→source map ──────


def build_provider_source_map(
    sources: list[dict],
    provider_names: list[str],
) -> dict[str, list[int]]:
    """Map each M3U provider name to a list of matching EPG source IDs.

    Matching is by substring (case-insensitive) — e.g. "Sports" would
    match both "Sports" and "Sports HD" source entries.
    """
    mapping: dict[str, list[int]] = {}
    for provider in provider_names:
        p_lower = provider.lower()
        matched = [
            s["id"] for s in sources
            if isinstance(s, dict) and p_lower in s.get("name", "").lower()
        ]
        if matched:
            mapping[p_lower] = matched
    return mapping


# ─────────────────────────────────────────────────── group suffix ──────────


def _tvg_suffix(tvg_id: str) -> str | None:
    """Return the part after the last dot, e.g. 'SABC1.za' → 'za'."""
    m = re.search(r'\.(\w+)$', tvg_id)
    return m.group(1).lower() if m else None


def infer_group_suffixes(
    channels: list[Channel],
) -> dict[int | None, str | None]:
    """For each channel_group_id, return the dominant tvg_id suffix (or None)."""
    groups: dict[int | None, list[Channel]] = {}
    for ch in channels:
        groups.setdefault(ch.channel_group_id, []).append(ch)

    result: dict[int | None, str | None] = {}
    for gid, members in groups.items():
        assigned = [ch for ch in members if ch.tvg_id]
        if not assigned:
            result[gid] = None
            continue
        suffixes = [s for ch in assigned if (s := _tvg_suffix(ch.tvg_id or ""))]
        if not suffixes:
            result[gid] = None
            continue
        top, count = Counter(suffixes).most_common(1)[0]
        result[gid] = top if count / len(assigned) >= SUFFIX_THRESHOLD else None

    return result


# ─────────────────────────────────────────────────── name matching ─────────


def _norm(name: str) -> str:
    return _normalize_fn(name, mode="aggressive").lower()


def _score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


_TRAILING_NUMBER_RE = re.compile(r'\b(\d+)\s*$')


def _trailing_number(name: str) -> str | None:
    """Return the trailing digit sequence in a name, e.g. 'Sport 4K 1' → '1'."""
    m = _TRAILING_NUMBER_RE.search(name.strip())
    return m.group(1) if m else None


def _key_token(channel_norm: str) -> str | None:
    """Return the most distinctive token in the channel name.

    That is: the longest token that is not in _STOP_WORDS and not a pure
    number.  If every token is a stop word, return None (no key-token check).
    """
    tokens = [t for t in channel_norm.split()
              if t not in _STOP_WORDS and not t.isdigit()]
    return max(tokens, key=len) if tokens else None


def _best_match(
    channel_norm: str,
    channel_raw_name: str,
    candidates: list[EpgEntry],
    precomputed: dict[int, str],
) -> tuple[EpgEntry | None, float]:
    """Return the best-matching EpgEntry and its similarity score.

    Two pre-filters are applied before scoring:

    1. Number consistency — if the channel name ends with a number N, the
       EPG entry must also contain N.  Stops "BBC One +1" matching
       a generic "BBC One" entry.

    2. Key-token check — the channel's most distinctive token (longest
       non-stopword) must appear verbatim in the EPG entry name.  Stops
       "BBC News" matching "SABC News" (BBC not in sabc news),
       "Cartoon Network" matching "Food Network" (cartoon not in food network),
       etc.
    """
    ch_tokens = set(channel_norm.split())
    required_number = _trailing_number(channel_raw_name)
    key_tok = _key_token(channel_norm)
    best_entry: EpgEntry | None = None
    best_score = 0.0

    for entry in candidates:
        # 1. Number consistency
        if required_number:
            if not (re.search(r'\b' + required_number + r'\b', entry.name) or
                    re.search(r'\b' + required_number + r'\b', entry.tvg_id)):
                continue
        entry_norm = precomputed[entry.id]
        # 2. Key-token check
        if key_tok and re.search(r'\b' + re.escape(key_tok) + r'\b', entry_norm) is None:
            continue
        # Quick token pre-filter — skip entries that share no tokens at all
        if ch_tokens and not (ch_tokens & set(entry_norm.split())):
            continue
        s = _score(channel_norm, entry_norm)
        if s > best_score:
            best_score = s
            best_entry = entry

    return best_entry, best_score


# ──────────────────────────────────────────────────── main function ────────


def find_proposals(
    channels: list[Channel],
    stream_lookup: dict[int, Stream],
    epg_entries: list[EpgEntry],
    provider_source_map: dict[str, list[int]],  # provider_name_lower → [source_id]
    progress_callback: "Callable[[int], None] | None" = None,
) -> tuple[list[EpgProposal], int]:
    """Return (proposals_for_unassigned_channels, count_already_assigned).

    Proposals are sorted by confidence descending.

    progress_callback, if provided, is called once per unassigned channel
    processed with the value 1 so callers can advance a progress bar.
    """
    from typing import Callable  # local import avoids circular at module level

    # Pre-normalise all EPG names once (expensive without this)
    precomputed: dict[int, str] = {e.id: _norm(e.name) for e in epg_entries}

    # Build fast lookup indices
    by_source: dict[int, list[EpgEntry]] = {}
    by_suffix: dict[str, list[EpgEntry]] = {}
    for entry in epg_entries:
        by_source.setdefault(entry.epg_source, []).append(entry)
        s = _tvg_suffix(entry.tvg_id)
        if s:
            by_suffix.setdefault(s, []).append(entry)

    group_suffix = infer_group_suffixes(channels)

    already_assigned = sum(1 for ch in channels if ch.epg_data_id)
    unassigned = [ch for ch in channels if not ch.epg_data_id]

    proposals: list[EpgProposal] = []

    for channel in unassigned:
        ch_norm = _norm(channel.name)
        if not ch_norm:
            if progress_callback:
                progress_callback(1)
            continue

        # Preferred EPG source IDs from the channel's #1 stream provider
        preferred: list[int] = []
        if channel.stream_ids:
            stream = stream_lookup.get(channel.stream_ids[0])
            if stream and stream.provider:
                preferred = provider_source_map.get(stream.provider.lower(), [])

        suffix = group_suffix.get(channel.channel_group_id)

        # Try progressively wider pools until we find a match
        attempts: list[tuple[list[EpgEntry], str]] = []

        if suffix:
            # Group has a confirmed regional pattern — never cross that boundary.
            # Only widen by dropping the provider requirement, never by dropping the suffix.
            if preferred:
                pool = [e for e in epg_entries
                        if e.epg_source in preferred and _tvg_suffix(e.tvg_id) == suffix]
                attempts.append((pool, "provider+suffix"))
            attempts.append((by_suffix.get(suffix, []), "suffix"))
            # No further fallback — a .za group will never get a .fr suggestion.
        else:
            # No regional pattern known — use provider as the only signal.
            # name_only (all sources, no suffix) is a last resort and flagged clearly.
            if preferred:
                pool = [e for src in preferred for e in by_source.get(src, [])]
                attempts.append((pool, "provider"))
            attempts.append((epg_entries, "name_only"))

        for pool, method in attempts:
            if not pool:
                continue
            entry, score = _best_match(ch_norm, channel.name, pool, precomputed)
            if entry and score >= METHOD_MIN_CONFIDENCE.get(method, 0.40):
                proposals.append(EpgProposal(
                    channel=channel,
                    epg_entry=entry,
                    confidence=round(score, 3),
                    method=method,
                ))
                break

        if progress_callback:
            progress_callback(1)

    # Deduplicate: if multiple channels claim the same EPG entry, keep only
    # the highest-scoring one.  9 channels all pointing at "BBC World Service" is a
    # clear sign 8 of them are wrong.
    proposals.sort(key=lambda p: p.confidence, reverse=True)
    seen_epg_ids: set[int] = set()
    deduped: list[EpgProposal] = []
    for p in proposals:
        if p.epg_entry.id not in seen_epg_ids:
            seen_epg_ids.add(p.epg_entry.id)
            deduped.append(p)

    return deduped, already_assigned
