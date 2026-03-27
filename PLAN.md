# PLAN.md — Channelarr Build Roadmap

This is a living document. Mark tasks `[x]` as completed. Do not skip phases — each builds on the last.

---

## Phase 1 — Core Infrastructure
**Goal:** Working CLI that replicates original behavior with safety-first defaults.
Dry-run works. `--apply` commits. No channel creation without `--allow-new-channels`.

**Dependencies:** `requests` (already present), `pyyaml`

### Tasks
- [x] `pyproject.toml` — project metadata, dependencies, entry point (`channelarr = "channelarr:main"`)
- [x] `core/models.py` — all dataclasses: `Stream`, `Channel`, `StreamMatch`, `ChannelChange`, `ChangeSet`, `AppliedChange`, `RunResult`, `Config` and sub-configs
- [x] `api/endpoints.py` — all API URL path constants
- [x] `api/client.py` — thin HTTP wrapper; auth header injection; retry logic; raises `APIException`; no business logic
- [x] `config/schema.py` — `Config` dataclass matching the YAML schema (see AGENTS.md)
- [x] `config/loader.py` — reads/writes `~/.config/channelarr/config.yaml`; returns `Config`
- [x] `config/wizard.py` — interactive first-run setup; writes initial `config.yaml`
- [x] `core/normalizer.py` — `default` normalizer (strips HD/SD/4K/FHD/UHD, brackets, trims whitespace)
- [x] `matching/base.py` — `MatchStrategy` protocol
- [x] `matching/regex_match.py` — regex/normalization strategy (ports current upstream behavior)
- [x] `core/planner.py` — pure function: `plan(streams, channels, config, strategy, resolver) -> ChangeSet`
- [x] `core/executor.py` — walks ChangeSet, applies API writes, returns `RunResult`
- [x] `core/differ.py` — formats `ChangeSet` into structured diff data (plain text for Phase 1)
- [x] `utils/cli_args.py` — argparse with: `--apply`, `--allow-new-channels`, `--config`, `--refresh`, `--reconfigure`, `--verbose`, `--quiet`
- [x] `channelarr.py` — entry point: wires all modules, runs pipeline, gates executor behind `--apply`
- [x] `config.example.yaml` — fully annotated example
- [x] `tests/conftest.py` — shared fixtures: sample `Stream` and `Channel` objects, minimal `Config`, mock API response dicts; build this before any test file
- [x] `tests/test_normalizer.py`:
  - `"CNN HD"` → `"CNN"`
  - `"BBC One [SD]"` → `"BBC One"`
  - `"4K Sport (UHD)"` → `"4K Sport"` (only trailing quality tags stripped, not leading)
  - `"   Sky News  "` → `"Sky News"` (whitespace trim)
  - `""` → `""` (empty string safe)
  - `"CNN"` → `"CNN"` (no suffix, unchanged)
  - Multiple suffixes: `"ITV HD SD"` → `"ITV"`
- [x] `tests/test_planner.py`:
  - Stream matches existing channel by name → `UPDATE`
  - Stream has no matching channel, `allow_new_channels=True` → `CREATE`
  - Stream has no matching channel, `allow_new_channels=False` → `SKIP(CREATE_NOT_PERMITTED)`
  - Multiple streams normalize to same name → planner groups them (one `ChannelChange` with multiple candidates)
  - Channel with no matching streams at all → not in ChangeSet (planner only processes streams)
  - Verify planner makes zero API calls (inject a dummy client that raises if called)
- [x] `tests/test_client.py`:
  - Auth request sends correct body and stores token
  - Successful GET returns parsed JSON
  - Non-2xx response raises `APIException` with status code
  - Retry fires on 5xx and succeeds on second attempt
  - Retry exhausted raises `APIException`
  - `--refresh` triggers M3U refresh endpoint before fetching
- [x] `tests/test_executor.py`:
  - UPDATE change → correct PUT called with merged `.raw` payload; `AppliedChange.success = True`
  - CREATE change → POST to `from-stream/` then PUT; `AppliedChange.success = True`
  - SKIP change → no API call made; recorded in `RunResult`
  - API error on UPDATE → `AppliedChange.success = False`, error captured, execution continues
  - Executor never called in dry-run (tested at `channelarr.py` level via CLI flag check)

**Done when:**
```bash
python3 channelarr.py              # shows diff, touches nothing
python3 channelarr.py --apply      # updates existing channels
python3 channelarr.py --apply --allow-new-channels  # full original behavior
```

---

## Phase 2 — Safety Layer + Group Scoping + Pairing Memory
**Goal:** Locks, allowlist, blocklist, and `--allow-delete` are all fully operational.
Group-scoped matching prevents cross-group false matches (e.g. MY|CNN ≠ UK CNN).
A pairing store lets the user confirm ambiguous matches once; subsequent runs remember them.
Locked channels are fully protected by default, but can be unlocked seamlessly via the
pairing wizard (one-time confirmation, saved to pairing store) or `--unlock` for a single run.

**Dependencies:** none new

### Pre-work: model changes (do before anything else in this phase)
- [x] `core/models.py` — add `channel_group: Optional[str]` to `Stream`; add `channel_group_id: Optional[int]` to `Channel`
- [x] `channelarr.py` — populate `channel_group` / `channel_group_id` when constructing `Stream` and `Channel` from API responses
- [x] `config/schema.py` — add `scope_to_group: bool = False` to `MatchingConfig`
- [x] `tests/conftest.py` — add `channel_group` to all stream fixtures; add `channel_group_id` to all channel fixtures
- [x] Update `config.example.yaml` with `scope_to_group` option and explanation

### Group-scoped matching
- [x] `matching/regex_match.py` — when `scope_to_group=True`, only consider channels whose `channel_group_id` matches `stream.channel_group`; fall back to unscoped if no same-group channels exist (log a warning)
- [x] `matching/base.py` — update `MatchStrategy` protocol signature to accept `scope_to_group: bool`

### Pairing store (match memory)
**What it does:** When the user confirms a pairing (stream name → channel), it is saved locally.
On future runs the planner loads saved pairings and uses them directly, bypassing the strategy.
This means the user only has to resolve an ambiguous match once.

- [x] `core/models.py` — add `SavedPairing` dataclass: `normalized_stream_name`, `channel_group`, `channel_id`, `channel_name`, `confirmed_at`
- [x] `pairings/__init__.py`
- [x] `pairings/store.py` — read/write `~/.local/share/channelarr/pairings.json`; keyed by `(normalized_stream_name, channel_group)`; never deletes entries (use `active: bool` to disable); also records locked-name skips (Scenario B) so future runs skip normalization work entirely for known-locked names
- [x] `core/planner.py` — check pairing store first; if a saved pairing exists for a stream, use it directly and skip the strategy for that stream
- [x] `channelarr.py` — load pairing store at startup; pass to planner

### Pairing wizard (interactive dry-run pairing UI)
**When it runs:** During a dry-run, after the planner and filters, for two situations:
1. Ambiguous matches — unconfirmed change with multiple candidates or cross-group uncertainty
2. Locked channel overrides — a SKIP(LOCKED) change where the user wants to explicitly approve it

For situation 2: confirming a locked channel in the wizard saves an approval to the pairing store.
On future runs, the planner finds the saved approval and proceeds — no wizard prompt needed again.
The lock list in config is never modified; the approval lives only in the pairing store.

- [x] `ui/pairing_wizard.py`:
  - Ambiguous section: display ranked candidates (same-group first, then by name similarity); prompt user to pick a number or skip; save confirmed pairings to store
  - Locked section: display each SKIP(LOCKED) change and ask "Approve this update for all future runs? [y/N]"; if yes, save a locked-approval entry to pairing store; if no, lock stands
  - Approval entries in pairing store include `override_lock: true` so they are distinguishable from normal pairings
- [x] `channelarr.py` — after dry-run diff output, if ambiguous or locked changes exist, offer to run pairing wizard; `--pair` flag forces wizard even if nothing is pending (to review/override existing pairings)
- [x] `utils/cli_args.py` — add `--pair` flag; add `--unlock "Channel Name"` flag (repeatable) for one-run unlocks without wizard interaction

### Filters
- [x] `filters/__init__.py`
- [x] `filters/lock.py` — if a channel name is in the lock list, mark `SKIP(LOCKED)` for ALL change types (UPDATE, CREATE, DELETE); lock list matched by normalized name; a saved pairing-store approval (`override_lock: true`) OR a `--unlock` flag causes the filter to pass the change through instead of skipping it
- [x] `filters/allowlist.py` — if allowlist non-empty, marks everything else `SKIP(NOT_IN_ALLOWLIST)`
- [x] `filters/blocklist.py` — marks `SKIP(BLOCKED)` for any change whose resolved channel name is in the blocklist
- [x] Wire filter pipeline in `channelarr.py`: lock → blocklist → allowlist (in this order)

### Priority resolver
- [x] `priority/__init__.py`
- [x] `priority/resolver.py` — given N stream candidates for one channel, picks the `winning_match` by `highest_priority` / `most_recent` / `first_match`; handles `stream.provider is None` (treat as lowest rank)
- [x] Wire priority resolver into `core/planner.py` as optional parameter (default: `first_match`)

### DELETE support
- [x] `core/planner.py` — second pass over channels: any channel with no matching streams emits `DELETE` or `SKIP(DELETE_NOT_PERMITTED)` depending on `config.allow_delete_default`
- [x] `--allow-delete` already in `utils/cli_args.py`; wire it into `channelarr.py` → `config.allow_delete_default`

### Tests
- [x] `tests/test_filters.py`:
  - Locked channel name (UPDATE) → `SKIP(LOCKED)`, no stream assignment happens
  - Locked channel name (DELETE) → `SKIP(LOCKED)`, channel not deleted
  - Locked channel name (CREATE) → `SKIP(LOCKED)`, channel not created
  - Non-locked channel → untouched by lock filter
  - Locked channel + pairing store has `override_lock: true` approval → change passes through (not skipped)
  - Locked channel + `--unlock "Channel Name"` flag → change passes through for that run only
  - Allowlist non-empty, channel in list → unchanged
  - Allowlist non-empty, channel not in list → `SKIP(NOT_IN_ALLOWLIST)`
  - Allowlist empty → all channels pass through (filter is no-op)
  - Blocklisted channel → `SKIP(BLOCKED)` regardless of other flags
  - Filter order: lock runs before blocklist, blocklist before allowlist
- [x] `tests/test_priority_resolver.py`:
  - Two candidates, provider ranks defined → higher-rank provider wins
  - Two candidates, one provider has no rank → ranked provider wins
  - Both providers unranked, strategy `first_match` → first candidate wins
  - Both providers unranked, strategy `most_recent` → most-recently-added stream wins (by stream id as proxy)
  - Single candidate → returned as-is regardless of strategy
  - Empty candidates list → returns `None` (no winner)
  - `stream.provider is None` → treated as lowest priority
- [x] `tests/test_group_scoping.py`:
  - `scope_to_group=True`: stream in group A only matches channels in group A
  - `scope_to_group=True`: stream in group A with no same-group channels → falls back to unscoped (with warning)
  - `scope_to_group=False`: stream matches channel regardless of group (current behavior)
  - "MY | CNN" in group `Malaysia` does not match "CNN" channel in group `News`
- [x] `tests/test_pairings.py`:
  - `store.save(pairing)` writes to file; `store.load()` reads it back correctly
  - Saving a pairing for the same stream+group twice updates the existing entry (no duplicates)
  - Planner uses saved pairing directly, bypassing strategy
  - Pairing with `active=False` is ignored by planner
  - No pairings file → planner runs normally (not an error)
  - Locked channel approval (`override_lock: true`) is loaded by lock filter and allows change through
  - `--unlock` flag bypasses lock filter for named channels without touching pairing store
- [x] Update `config.example.yaml` with `scope_to_group`, locks, allowlist, blocklist, priority, and pairing store path examples

**Done when:**
- Locked channel names are never changed or created by default, even with `--apply`
- A locked channel can be approved via the pairing wizard (once) or `--unlock` (per run) — no config editing required
- Allowlist correctly scopes a run to a subset of channels
- Blocklist makes channels completely invisible to the executor
- Priority rules deterministically resolve which stream wins when multiple match the same channel
- "MY | CNN" in the Malaysia group does not match the UK CNN channel
- User can confirm ambiguous pairings in a dry-run; confirmed pairings are used on all future runs without prompting
- All filter/skip states appear in diff output with reason

---

## Phase 3 — Visibility & Logging
**Goal:** Rich terminal output, verbose/quiet modes, structured logs, audit history, interactive mode.

**Dependencies:** `rich`

### Tasks
- [x] `ui/console.py` — Rich diff tables: color-coded by ChangeType, summary line, SKIP reasons visible
- [x] Replace plain-text diff in `core/differ.py` with structured data that `ui/console.py` renders
- [x] `--verbose` mode: show all stream candidates per channel with match scores
- [x] `--quiet` mode: only show final summary line (N updated, N created, N skipped)
- [x] `logging_/run_logger.py` — JSON lines log: timestamp, streams evaluated, changes proposed, changes applied
- [x] `logging_/history.py` — appends run summary to `history.jsonl`; never rewrites existing entries
- [x] Wire logging into `channelarr.py` (log each run after apply and after dry-run)
- [x] `ui/interactive.py` — `--interactive` mode: Rich prompt per change, approve/skip/quit
- [x] `-i` / `--interactive` flag in `utils/cli_args.py`
- [x] `tests/test_config_loader.py`:
  - [x] Valid YAML with all fields → `Config` dataclass populated correctly
  - [x] Missing optional fields (locks, allowlist, blocklist) → defaults to empty lists
  - [x] Missing required field (endpoint) → raises clear error, not a raw `KeyError`
  - [x] Unknown field in YAML → ignored (forward compatibility)
  - [x] File not found → raises `FileNotFoundError` with helpful message pointing to `--reconfigure`
  - [x] `loader.write(config)` round-trips: write then read back → same values

**Done when:**
- Terminal output is a Rich-formatted table with color-coded change types
- `--verbose` shows match candidates and scores
- Every run writes to the log file and appends to `history.jsonl`
- `--interactive` allows per-channel approval before `--apply` executes

---

## Phase 4 — Advanced Matching
**Goal:** Exact and fuzzy strategies available and swappable via config or `--strategy` flag.

**Dependencies:** `rapidfuzz`

### Tasks
- [x] `matching/exact.py` — exact string match (case-insensitive option)
- [x] `matching/fuzzy.py` — fuzzy match via `rapidfuzz`; respects `fuzzy_threshold` from config
- [x] `core/normalizer.py` — add `aggressive` normalizer (strips language codes, country codes, brackets)
- [x] Strategy factory in `channelarr.py` — reads `config.matching.strategy`, instantiates correct class
- [x] `--strategy` CLI flag to override strategy for one run
- [x] `tests/test_matching.py`:
  - [x] Regex strategy: normalized names match → `StreamMatch` with `MatchType.REGEX`, score 1.0
  - [x] Regex strategy: names differ after normalization → no match
  - [x] Exact strategy: identical names → match; one character different → no match
  - [x] Exact strategy: case-insensitive option → `"cnn"` matches `"CNN"`
  - [x] Fuzzy strategy: score above threshold → match with correct score value
  - [x] Fuzzy strategy: score at exactly threshold → match (boundary inclusive)
  - [x] Fuzzy strategy: score below threshold → no match
  - [x] All three strategies: swapping strategy on same input changes outcome predictably (no shared state)

**Done when:**
- `matching.strategy: fuzzy` in config activates fuzzy matching
- All three strategies pass tests
- Swapping strategy does not require touching planner code

---

## Phase 5 — Web UI (Visual Review)
**Goal:** Local browser-based diff review and apply before committing changes.

**Dependencies:** `flask`, `flask-cors` (optional install: `pip install channelarr[web]`)

### Tasks
- [ ] `web/server.py` — Flask app factory with config injection
- [ ] `web/routes.py`:
  - `GET /api/diff` — runs planner, returns ChangeSet as JSON
  - `POST /api/apply` — runs executor (requires `web.allow_apply: true` in config)
  - `GET /api/history` — returns `history.jsonl` entries as JSON
- [ ] `web/templates/index.html` — diff review table; Approve All / Apply Selected buttons
- [ ] `web/templates/history.html` — paginated run history
- [ ] `channelarr --web` or `channelarr serve` command in `utils/cli_args.py`
- [ ] Config schema: `web.enabled`, `web.host`, `web.port`, `web.allow_apply`, `web.auto_open`
- [ ] Server binds `127.0.0.1` by default; loud warning if `0.0.0.0` is configured
- [ ] `pyproject.toml` optional dependency group `[web]`
- [ ] `tests/test_web_routes.py` (uses Flask test client — no real HTTP):
  - `GET /api/diff` → returns JSON with `creates`, `updates`, `skips` keys
  - `POST /api/apply` with `web.allow_apply: false` → 403 forbidden
  - `POST /api/apply` with `web.allow_apply: true` → calls executor, returns run summary
  - `GET /api/history` → returns entries from `history.jsonl` as JSON array

**Note on `config/wizard.py` testing:** The wizard uses interactive prompts (`input()`), which are hard to unit test directly. Test it by injecting fake input via `monkeypatch` (pytest built-in) to simulate a user typing values — no manual testing needed.

**Done when:**
- `channelarr serve` starts local server
- Browser shows pending diff with color coding
- User can approve and apply from browser
- History page shows past runs

---

## Attachment Matching (completed out of phase, added during live testing)
**Goal:** Use streams already attached to a channel as the primary match signal,
not just the channel name. More robust than name-only matching — survives channel renames.

- [x] `core/planner.py` — `_build_attachment_index`: maps `normalized_stream_name → channel`
  from each channel's current `stream_ids`; sanity guard filters entries with no token
  overlap between attached stream name and channel name (prevents poisoned index)
- [x] `core/models.py` — added `MatchType.ATTACHMENT`
- [x] Match priority: pairing store > attachment index > name strategy
- [x] `tests/test_attachment_matching.py` — 9 tests including poisoned-index regression

## Deduplication (completed out of phase, added during live testing)
**Goal:** Find channels with the same normalized name, merge their streams onto one, delete the rest.

- [x] `dedup/finder.py` — groups channels by normalized name; winner = most streams then lowest ID
- [x] `dedup/merger.py` — PUT winner with merged streams, DELETE duplicates
- [x] `--dedup` flag: dry-run shows groups; `--dedup --apply` executes
- [x] `ui/console.py` — dedup group display and result output
- [x] `tests/test_dedup.py` — 13 tests

---

## Phase 5 — Web UI (Visual Review)
**Goal:** Local browser-based diff review and apply before committing changes.
**Status:** Deferred — user wants to validate the tool further before building the web UI.

**Dependencies:** `flask`, `flask-cors` (optional install: `pip install channelarr[web]`)

### Tasks
- [ ] `web/server.py` — Flask app factory with config injection
- [ ] `web/routes.py`:
  - `GET /api/diff` — runs planner, returns ChangeSet as JSON
  - `POST /api/apply` — runs executor (requires `web.allow_apply: true` in config)
  - `GET /api/history` — returns `history.jsonl` entries as JSON
- [ ] `web/templates/index.html` — diff review table; Approve All / Apply Selected buttons
- [ ] `web/templates/history.html` — paginated run history
- [ ] `channelarr --web` or `channelarr serve` command in `utils/cli_args.py`
- [ ] Config schema: `web.enabled`, `web.host`, `web.port`, `web.allow_apply`, `web.auto_open`
- [ ] Server binds `127.0.0.1` by default; loud warning if `0.0.0.0` is configured
- [ ] `pyproject.toml` optional dependency group `[web]`
- [ ] `tests/test_web_routes.py` (uses Flask test client — no real HTTP):
  - `GET /api/diff` → returns JSON with `creates`, `updates`, `skips` keys
  - `POST /api/apply` with `web.allow_apply: false` → 403 forbidden
  - `POST /api/apply` with `web.allow_apply: true` → calls executor, returns run summary
  - `GET /api/history` → returns entries from `history.jsonl` as JSON array

**Done when:**
- `channelarr serve` starts local server
- Browser shows pending diff with color coding
- User can approve and apply from browser
- History page shows past runs

---

## Backlog / Future Ideas

- Pagination support for Dispatcharr API (current hardcoded `page_size=2500` truncates large libraries)
- `--dry-run` flag as an explicit alias (even though dry-run is already the default)
- Export diff to JSON or CSV for external review
- Scheduled runs via cron with email/webhook notifications
- Multiple config profiles (e.g. `--profile sports` for a scoped run)
- Rollback: given a `history.jsonl` entry, reverse the changes it made

---

## Dependencies Summary

| Phase | New Dependencies |
|---|---|
| 1 | `pyyaml` |
| 2 | none |
| 3 | `rich` |
| 4 | `rapidfuzz` |
| 5 | `flask`, `flask-cors` |
| dev | `pytest`, `pytest-cov`, `responses`, `mypy`, `ruff` |

## pyproject.toml Starting Point

```toml
[project]
name = "channelarr"
version = "0.1.0"
description = "Safety-first Dispatcharr channel and stream manager. Fork of dispatcharr-group-channel-streams by kpirnie (github.com/udezekene/Channelarr)."
requires-python = ">=3.10"
dependencies = [
    "requests>=2.28",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
rich = ["rich>=13.0"]
fuzzy = ["rapidfuzz>=3.0"]
web = ["flask>=3.0", "flask-cors>=4.0"]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "responses>=0.25", "mypy>=1.9", "ruff>=0.4"]

[project.scripts]
channelarr = "channelarr:main"
```
