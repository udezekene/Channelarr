# CLAUDE.md — Channelarr

## Start Here

Read `AGENTS.md` before doing anything. It contains the full project context, architecture, design rules, and data structures. This file is the session entry point — `AGENTS.md` is the source of truth.

## What This Project Is

Channelarr is a safety-first fork of dispatcharr-group-channel-streams. It manages stream-to-channel assignments in a Dispatcharr instance. The key shift from the original: **dry-run is the default**. Nothing changes unless `--apply` is explicitly passed.

## Project Location

`/Users/udezekene/Documents/Projects/channelarr/`

## Where to Start Building

Check `PLAN.md` for the current phase and open tasks. Work phase by phase — do not skip ahead. Each phase has a clear "done when" definition.

## Rules

- Never modify the original preserved files: `main.py`, `api/dchg_main.py`, `config/config_handler.py`, `utils/args.py`, `utils/exceptions.py`
- New entry point is `channelarr.py` — not `main.py`
- All new dataclasses go in `core/models.py` first; no raw dicts passed between modules
- The planner must remain pure (no API calls, no I/O); the executor is the only thing that writes to the API
- See AGENTS.md "Key Design Rules" section — these are non-negotiable

## User Context

The user (Kene) is not deeply familiar with Python. Keep explanations clear. When proposing a design decision, lead with what it means practically, not the theory. Prefer working code with brief comments over undocumented abstractions.

## Running the Tool (once built)

```bash
cd /Users/udezekene/Documents/Projects/channelarr
python3 channelarr.py                          # dry-run (default)
python3 channelarr.py --apply                  # commit changes
python3 channelarr.py --apply --allow-new-channels  # also permit channel creation
python3 channelarr.py --interactive            # step-through approval mode
```
