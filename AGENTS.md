# AGENTS.md — Channelarr Project Context

This file is the authoritative context document for any AI agent or developer working on Channelarr.
Read this before writing a single line of code.

---

## What Channelarr Is

Channelarr is a **fork** of [dispatcharr-group-channel-streams](https://github.com/kpirnie/dispatcharr-group-channel-streams)
by kpirnie. The Channelarr fork lives at [github.com/udezekene/Channelarr](https://github.com/udezekene/Channelarr). It is a Python CLI tool for managing channels and stream assignments in a
[Dispatcharr](https://github.com/dispatcharr/dispatcharr) instance via its REST API.

**The core problem it solves:** When you have multiple M3U providers, the same channel (e.g. CNN)
appears as many streams (CNN HD, CNN SD, CNN International). Channelarr groups those streams and
assigns them to channels as failover sources, so if one stream dies, the next kicks in automatically.

**Why Channelarr exists (and not just the original):**
The original tool is useful but dangerous for users with curated channel lists — it creates new channels
aggressively and has no dry-run mode. Channelarr is built safety-first: every run is a dry-run unless
`--apply` is explicitly passed. It gives the user full visibility and control before anything changes.

---

## Original Codebase (Preserved, Do Not Modify)

These files from the upstream fork are kept **verbatim** as reference. Never edit them.

| File | What it does |
|---|---|
| `main.py` | Original entry point. Parses args, instantiates `DCHG_Main`, calls `create_channels()`. |
| `api/dchg_main.py` | Monolithic class. Auth, fetch streams, fetch channels, normalize names, create/update channels. All logic in one place. |
| `config/config_handler.py` | INI config at `~/.config/.dgcs_conf`. Read, write, prompt for config. |
| `utils/args.py` | argparse: `--endpoint`, `--username`, `--password`, `--normalizer`, `--refresh`, `--reconfigure`. |
| `utils/exceptions.py` | `APIException` with status code + response text. |

**What the original does in sequence:**
1. Authenticate → `POST /api/accounts/token/` → bearer token
2. Optionally refresh M3U → `POST /api/m3u/refresh/`
3. Fetch all streams → `GET /api/channels/streams/?page_size=2500`
4. Fetch all channels → `GET /api/channels/channels/?page_size=2500`
5. Normalize stream names via regex (strips HD/SD/4K etc.)
6. Group streams by normalized name
7. For each group: if channel exists → `PUT /api/channels/channels/{id}/`; if not → `POST /api/channels/channels/from-stream/` then `PUT`

**Key problems with the original (what we fix):**
- No dry-run: changes are immediate on first run
- No preview: you can't see what will happen before it happens
- Creates new channels by default: dangerous for curated lists
- No channel locking: no way to protect specific channels
- No priority rules: stream order is arbitrary
- No audit trail: no record of what was changed
- INI config: limited to flat key-value, can't express complex rules

---

## Channelarr Architecture

### New Entry Point

`channelarr.py` — the only file to run. The original `main.py` is preserved for reference.

```
python3 channelarr.py              # dry-run (default) — shows diff, touches nothing
python3 channelarr.py --apply      # commits the planned changes
python3 channelarr.py --apply --allow-new-channels   # also permits channel creation
```

### File Structure

```
channelarr/
├── channelarr.py                  # Entry point: arg parsing, DI wiring, pipeline orchestration
│
├── api/
│   ├── client.py                  # Thin HTTP wrapper; raises APIException; no business logic
│   └── endpoints.py               # All API URL constants in one place
│
├── core/
│   ├── models.py                  # ALL dataclasses: Stream, Channel, ChangeSet, ChannelChange, Config, etc.
│   ├── normalizer.py              # Name normalization functions (pluggable; "default", "aggressive", "none")
│   ├── planner.py                 # PURE: streams + channels + config → ChangeSet. Zero side effects.
│   ├── executor.py                # EFFECTFUL: ChangeSet + client → applies API writes. Returns RunResult.
│   └── differ.py                  # Formats ChangeSet into structured diff data (no rendering logic here)
│
├── matching/
│   ├── base.py                    # MatchStrategy protocol/ABC
│   ├── exact.py                   # Exact string match
│   ├── regex_match.py             # Regex/normalization match (current upstream behavior)
│   └── fuzzy.py                   # Fuzzy match via rapidfuzz; respects fuzzy_threshold from config
│
├── filters/
│   ├── lock.py                    # Marks locked channels SKIP; lock list from config
│   ├── allowlist.py               # If allowlist non-empty, marks everything else SKIP
│   └── blocklist.py               # Marks blocklisted channels SKIP (invisible in normal diff view)
│
├── priority/
│   └── resolver.py                # Given N stream candidates for one channel, picks winner by rules
│
├── logging_/
│   ├── run_logger.py              # JSON lines log per run (what was evaluated / proposed / applied)
│   └── history.py                 # Appends run summaries to history.jsonl (audit trail across runs)
│
├── ui/
│   ├── console.py                 # Rich-based console: diff tables, color coding, confirm prompts
│   └── interactive.py             # --interactive mode: step-through approval loop per channel change
│
├── web/                           # Phase 5 only
│   ├── server.py                  # Flask app factory
│   ├── routes.py                  # /api/diff, /api/apply, /api/history
│   └── templates/
│       ├── index.html             # Diff review UI
│       └── history.html           # Audit trail browser
│
├── config/
│   ├── schema.py                  # Authoritative Config dataclass (YAML shape defined here)
│   ├── loader.py                  # Reads/writes config.yaml; validates; returns Config instance
│   └── wizard.py                  # Interactive first-run setup; writes initial config.yaml
│
├── utils/
│   ├── cli_args.py                # New argparse for channelarr (all new flags)
│   └── exceptions.py              # Channelarr exceptions (extend originals; do not modify original file)
│
├── tests/
│   ├── conftest.py                # Shared fixtures: mock API responses, sample data
│   ├── test_planner.py
│   ├── test_executor.py
│   ├── test_matching.py
│   ├── test_filters.py
│   ├── test_normalizer.py
│   ├── test_config_loader.py
│   └── test_priority_resolver.py
│
├── config.example.yaml            # Fully annotated example config (committed to repo)
├── pyproject.toml                 # Project metadata, dependencies, entry point
├── AGENTS.md                      # This file
├── CLAUDE.md                      # Claude Code session entry point
├── PLAN.md                        # Phased build roadmap with task checklist
└── README.md                      # User-facing docs, crediting upstream fork
```

---

## Core Data Structures (`core/models.py`)

Define these first. Every other module imports from here. No logic here — pure data.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

class ChangeType(Enum):
    CREATE = "create"    # new channel will be created
    UPDATE = "update"    # existing channel will have streams updated
    DELETE = "delete"    # channel will be deleted (requires --allow-delete)
    SKIP   = "skip"      # evaluated but will not be applied

class SkipReason(Enum):
    LOCKED                = "locked"
    BLOCKED               = "blocked"
    NOT_IN_ALLOWLIST      = "not_in_allowlist"
    CREATE_NOT_PERMITTED  = "create_not_permitted"
    DELETE_NOT_PERMITTED  = "delete_not_permitted"
    NO_MATCH              = "no_match"
    CONFLICT_UNRESOLVED   = "conflict_unresolved"
    USER_SKIPPED          = "user_skipped"   # interactive mode

class MatchType(Enum):
    EXACT  = "exact"
    REGEX  = "regex"
    FUZZY  = "fuzzy"
    NONE   = "none"

@dataclass
class Stream:
    id: int
    name: str
    provider: Optional[str]
    raw: dict[str, Any]          # original API dict; used when constructing PUT payloads

@dataclass
class Channel:
    id: int
    name: str
    stream_ids: list[int]
    raw: dict[str, Any]

@dataclass
class StreamMatch:
    stream: Stream
    channel: Optional[Channel]
    match_type: MatchType
    score: float                 # 1.0 for exact, 0.0–1.0 for fuzzy
    normalized_stream_name: str
    normalized_channel_name: Optional[str]

@dataclass
class ChannelChange:
    change_type: ChangeType
    stream: Stream
    channel: Optional[Channel]
    winning_match: Optional[StreamMatch]
    candidates: list[StreamMatch] = field(default_factory=list)
    skip_reason: Optional[SkipReason] = None
    skip_detail: Optional[str] = None

@dataclass
class ChangeSet:
    changes: list[ChannelChange] = field(default_factory=list)

    @property
    def creates(self) -> list[ChannelChange]:
        return [c for c in self.changes if c.change_type == ChangeType.CREATE]

    @property
    def updates(self) -> list[ChannelChange]:
        return [c for c in self.changes if c.change_type == ChangeType.UPDATE]

    @property
    def deletes(self) -> list[ChannelChange]:
        return [c for c in self.changes if c.change_type == ChangeType.DELETE]

    @property
    def skips(self) -> list[ChannelChange]:
        return [c for c in self.changes if c.change_type == ChangeType.SKIP]

@dataclass
class AppliedChange:
    change: ChannelChange
    success: bool
    api_response: Optional[dict[str, Any]] = None
    error: Optional[str] = None

@dataclass
class RunResult:
    applied: list[AppliedChange] = field(default_factory=list)
    dry_run: bool = True
    total_evaluated: int = 0

    @property
    def succeeded(self) -> list[AppliedChange]:
        return [a for a in self.applied if a.success]

    @property
    def failed(self) -> list[AppliedChange]:
        return [a for a in self.applied if not a.success]
```

---

## The Planner / Executor Split — Critical Design

This is the most important architectural decision. Understand it before touching anything.

```
API reads ──→ Planner ──→ ChangeSet ──→ [Filters] ──→ [Interactive?] ──→ Executor ──→ API writes
```

**Planner** (`core/planner.py`):
- Pure function in spirit. Signature: `plan(streams, channels, config, strategy, resolver) -> ChangeSet`
- Normalizes names, runs match strategy, resolves conflicts, determines ChangeType
- Makes NO API calls, NO console output, NO file I/O
- Because it is pure, dry-run is trivial: just don't call the executor

**Filter Pipeline** (applied after planning, before executor):
```python
changeset = planner.plan(streams, channels, config, strategy, resolver)
changeset = lock_filter.apply(changeset, config.locks)
changeset = blocklist_filter.apply(changeset, config.blocklist)
changeset = allowlist_filter.apply(changeset, config.allowlist)
```
Filters **annotate** — they mark changes as SKIP with a reason. They never delete from the list.
The full picture (including skips) is always visible in the diff.

**Dry-run gate** (in `channelarr.py`):
```python
if args.apply:
    result = executor.apply(changeset, client, logger)
    history.record(result)
else:
    print("Dry-run complete. Pass --apply to commit these changes.")
```
The executor is never called in dry-run. No `if dry_run: return` guards inside executor methods.
The gate in `channelarr.py` is the only gate.

**Executor** (`core/executor.py`):
- Iterates `changeset.changes`
- CREATE → `client.post(endpoints.CREATE_FROM_STREAM, ...)`
- UPDATE → `client.put(endpoints.CHANNEL, channel.id, payload)`
- DELETE → `client.delete(endpoints.CHANNEL, channel.id)` (only if `--allow-delete`)
- SKIP → record in RunResult, no API call
- Makes no decisions. If a CREATE reaches it, it creates. All decisions were made by planner + filters.

---

## Config File (YAML)

Default location: `~/.config/channelarr/config.yaml`
Override per run: `--config /path/to/config.yaml`

```yaml
endpoint: "https://dispatcharr.example.com"
username: "admin"
password: "changeme"

matching:
  strategy: "regex"          # regex | exact | fuzzy
  normalizer: "default"      # default | aggressive | none
  fuzzy_threshold: 0.85      # 0.0–1.0, only for fuzzy strategy

provider_priority:
  - name: "ProviderA"
    rank: 1                  # lower = higher priority

conflict_resolution:
  strategy: "highest_priority"  # highest_priority | most_recent | first_match

allow_new_channels_default: false   # override per run with --allow-new-channels
allow_delete_default: false         # override per run with --allow-delete

locks:
  - channel_name: "BBC One"
    reason: "Manually curated"

allowlist: []    # if non-empty, only these channels are processed
blocklist: []    # these channels are never evaluated

logging:
  log_file: "~/.local/share/channelarr/channelarr.log"
  history_file: "~/.local/share/channelarr/history.jsonl"
  level: "INFO"

web:
  enabled: false
  host: "127.0.0.1"
  port: 5000
  allow_apply: false
  auto_open: false
```

---

## CLI Flags (`utils/cli_args.py`)

| Flag | Effect |
|---|---|
| *(no flags)* | Dry-run: plan + diff, no writes |
| `--apply` | Commit the planned changes |
| `--allow-new-channels` | Permit channel creation this run (overrides config default) |
| `--allow-delete` | Permit channel deletion this run (overrides config default) |
| `--config PATH` | Use this config file instead of default |
| `--refresh` | Trigger M3U refresh before fetching streams |
| `--reconfigure` | Re-run the setup wizard |
| `-i` / `--interactive` | Step through each proposed change for approval |
| `--verbose` | Show all candidates, match scores, skip reasons |
| `--quiet` | Only show summary line |
| `--strategy NAME` | Override matching strategy for this run (regex/exact/fuzzy) |
| `--web` | Start local web UI server |

---

## Key Design Rules (Non-Negotiable)

1. **Dry-run is structural.** The executor is never called unless `--apply` is passed. Never add `if dry_run` guards inside executor methods.

2. **Filters annotate, they do not delete.** A filter marks a change SKIP; it does not remove it from the ChangeSet. The diff always shows everything including skips.

3. **ChangeSet is final after the filter pipeline.** The executor does not re-filter or modify change types.

4. **Preserve `.raw` on Stream and Channel.** When constructing PUT payloads, merge into `.raw` — don't construct from scratch. Protects against losing API fields added in future Dispatcharr versions.

5. **Config is read once at startup.** No module below `channelarr.py` reads from disk. All receive a `Config` dataclass instance. This makes testing trivial and prevents mid-run config drift.

6. **Original files are never modified.** `main.py`, `api/dchg_main.py`, `config/config_handler.py`, `utils/args.py`, `utils/exceptions.py` — read-only. New code goes in new files.

7. **Match strategies are stateless.** No caching, no state mutation. Safe to swap mid-session.

8. **Provider is optional on Stream.** The priority resolver must handle `stream.provider is None` gracefully (treat as lowest rank).

9. **CLI flags are per-run overrides only.** `--allow-new-channels` does not persist to config.

10. **Web UI is read-only by default.** `web.allow_apply: true` must be set explicitly. Server binds `127.0.0.1` by default and warns loudly if changed to `0.0.0.0`.

11. **`history.jsonl` is append-only.** Never rewrite or compact it.

12. **Python 3.10+ minimum for new code.** Use `match` statements, `|` union types. Do not introduce 3.10+ syntax into preserved original files (they declare 3.6+ compatibility).

---

## Dispatcharr API Reference

Base URL: configured by user (e.g. `https://dispatcharr.example.com`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/accounts/token/` | Auth; body `{username, password}`; returns `{access, refresh}` |
| POST | `/api/m3u/refresh/` | Trigger M3U refresh; returns 202 |
| GET | `/api/channels/streams/?page_size=2500` | All streams |
| GET | `/api/channels/channels/?page_size=2500` | All channels |
| POST | `/api/channels/channels/from-stream/` | Create channel from stream; body `{name, stream_id}` |
| PUT | `/api/channels/channels/{id}/` | Update channel; body `{name, streams: [id,...], tvg_id, channel_group_id}` |
| DELETE | `/api/channels/channels/{id}/` | Delete channel |

Auth header: `Authorization: Bearer {access_token}`

**Known limitation in original:** `page_size=2500` is hardcoded. If a user has more than 2500 streams or channels, results are silently truncated. Channelarr should support pagination.

---

## Python Conventions for This Project

- Dataclasses for all data (no dicts passed between modules)
- Type hints everywhere (mypy-clean)
- No global state — config and client are injected as parameters
- Functions over classes where there is only one method
- Module-level docstring on every file explaining its responsibility
- `ruff` for linting; `pytest` for tests
- Test the planner exhaustively — it is pure and easy to test. At minimum: exact match, no match (CREATE), skip due to lock, skip due to CREATE_NOT_PERMITTED.

---

## Fork Attribution

The upstream project is dispatcharr-group-channel-streams by kpirnie.
Any PR proposed back upstream should:
- Credit the original architecture
- Be scoped to the safety features (dry-run, --apply, --update-only) as a standalone PR
- Not include Channelarr-specific naming, config schema, or web UI

---

## Current State

- Upstream files cloned and preserved at: `/Users/udezekene/Documents/Projects/channelarr/`
- No new Channelarr code written yet
- Build starts at Phase 1 (see PLAN.md)
