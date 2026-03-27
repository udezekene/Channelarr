# Channelarr

A safety-first channel and stream management tool for [Dispatcharr](https://github.com/dispatcharr/dispatcharr).

Channelarr is a fork of [dispatcharr-group-channel-streams](https://github.com/kpirnie/dispatcharr-group-channel-streams) by [kpirnie](https://github.com/kpirnie), extended with dry-run defaults, structured change previews, explicit commit controls, and richer channel management options.

---

> **Legal notice:** Channelarr is intended for use exclusively with streaming sources you are legally licensed or entitled to access. This tool does not provide, distribute, or facilitate access to any streaming content — it is a management utility that organises streams already configured within your own Dispatcharr instance. The authors accept no liability for use of this tool with unlicensed, unauthorised, or infringing content sources. You are solely responsible for ensuring your sources comply with applicable copyright law and the terms of service of your content providers.

---

## The Core Difference

The original tool applies changes immediately on first run. Channelarr does not.

Every run is a **dry-run by default**. Channelarr shows you exactly what it plans to do — which channels would be updated, which streams would be assigned, what would be skipped and why — before anything is touched. Changes only happen when you pass `--apply`.

---

## What It Does

Dispatcharr manages streams from multiple sources. When those sources carry the same channel under slightly different names (e.g. "BBC One", "BBC One HD", "BBC One FHD"), Channelarr groups them and assigns all variants to a single channel as ordered failover sources. If the primary stream goes down, the next one takes over automatically.

Channelarr is designed for users who have a curated channel list they care about. It will not create new channels, delete anything, or overwrite your work unless you explicitly tell it to.

---

## Features

- **Dry-run by default** — nothing changes unless you pass `--apply`
- **Structured diff preview** — see every proposed change before committing
- **No auto-create** — new channels only appear if you pass `--allow-new-channels`
- **No auto-delete** — deletions require `--allow-delete`
- **Per-channel locks** — protect specific channels from ever being touched
- **Allowlist / blocklist** — scope a run to specific channels, or exclude channels entirely
- **Priority rules** — define which source is primary, secondary, etc. rather than relying on import order
- **Pluggable matching** — exact, regex (default), or fuzzy matching configurable per run
- **Interactive mode** — step through each proposed change and approve or skip individually
- **Audit trail** — every run is logged; history is preserved across sessions
- **YAML config** — all preferences in one file; CLI flags are per-run overrides only

---

## Requirements

- Python 3.10+
- A running Dispatcharr instance
- Valid Dispatcharr credentials

---

## Installation

```bash
git clone https://github.com/udezekene/Channelarr.git
cd Channelarr
pip install pyyaml requests
```

---

## Quick Start

**First run** — Channelarr will prompt for your Dispatcharr URL and credentials and save them to `~/.config/channelarr/config.yaml`.

```bash
python3 channelarr.py
```

This is a dry-run. Nothing is changed. Review the proposed diff.

**Apply the changes:**

```bash
python3 channelarr.py --apply
```

**Also allow creation of new channels:**

```bash
python3 channelarr.py --apply --allow-new-channels
```

---

## CLI Reference

| Flag | Effect |
|---|---|
| *(no flags)* | Dry-run: plan, diff, no writes |
| `--apply` | Commit the planned changes |
| `--allow-new-channels` | Permit channel creation this run |
| `--allow-delete` | Permit channel deletion this run |
| `--config PATH` | Use a specific config file |
| `--refresh` | Trigger a source refresh before fetching streams |
| `--reconfigure` | Re-run the setup wizard |
| `-i` / `--interactive` | Step through each proposed change for manual approval |
| `--verbose` | Show all candidates and match scores |
| `--quiet` | Show summary line only |
| `--strategy NAME` | Override matching strategy: `regex` / `exact` / `fuzzy` |

---

## Configuration

All preferences live in `~/.config/channelarr/config.yaml`. CLI flags override config values for a single run only — they do not persist.

```yaml
endpoint: "http://localhost:8080"
username: "admin"
password: "changeme"

matching:
  strategy: "regex"        # regex | exact | fuzzy
  normalizer: "default"    # strips quality suffixes (HD, SD, 4K, etc.)
  fuzzy_threshold: 0.85

provider_priority:
  - name: "ProviderA"
    rank: 1                # lower = higher priority

conflict_resolution:
  strategy: "highest_priority"   # highest_priority | most_recent | first_match

allow_new_channels_default: false
allow_delete_default: false

locks:
  - channel_name: "BBC One"
    reason: "Manually curated, do not touch"

allowlist: []   # if non-empty, only process these channels
blocklist: []   # never process or display these channels
```

See `config.example.yaml` for a fully annotated version.

---

## Credits

Channelarr is a fork of [dispatcharr-group-channel-streams](https://github.com/kpirnie/dispatcharr-group-channel-streams) by [kpirnie](https://github.com/kpirnie). The original tool provided the Dispatcharr API interaction pattern and channel grouping logic that Channelarr builds on.

---

## License

This project is provided as-is for personal and educational use.
