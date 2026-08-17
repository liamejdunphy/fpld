# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only Fantasy Premier League assistant for the 2026/27 season. Two Python scripts read the public FPL API and write Markdown briefs and league reports. A React artifact (JSX, meant for Claude's artifact viewer) provides a five-gameweek transfer planner. Nothing ever writes to FPL.

## Running

Python 3.9+, stdlib only — no dependencies, no virtualenv, no build step.

```bash
# First run — creates ~/.fpld/config.json
python3 fpld_brief.py --init

# Daily brief
python3 fpld_brief.py --print

# Look up FPL's exact spelling for a player name
python3 fpld_brief.py --find odegaard

# League sync + report (needs at least GW1 scored)
python3 fpld_league.py --sync --report

# Verify IDs before the season starts
python3 fpld_league.py --peek
```

Override the data directory with `FPLD_HOME` env var or `--home` flag. Default is `~/.fpld/`.

There are no tests. There is no linter configured.

## Architecture

**`fpld_brief.py`** — daily brief pipeline:
- `get()` fetches from the FPL API (stdlib `urllib`, 0.4s pacing, SSL context)
- `build()` transforms bootstrap + fixtures into a player model with fixture-difficulty runs over a configurable horizon
- `squad_of()` resolves your 15 from the API picks endpoint, falling back to `squad_fallback` names in config (matched accent-insensitively via `norm()`)
- `score()` is the transfer heuristic: form 32%, fixtures 28%, points-per-million 22%, threat/defence 18%, scaled for blanks. Deliberately simple — 8 lines
- `captain_score()` is a separate ceiling-based ranking (no price term) used only for captaincy
- `diff()` compares today's model against `state.json` to detect overnight price changes and flag changes
- `dial()` computes the risk mode (SHIELD/SAFE/BALANCED/AGGRESSIVE/SWING) from points-behind and gameweeks-left

**`fpld_league.py`** — stateful league tracker:
- Stores all rival squads, captains, transfers, and chips in SQLite (`~/.fpld/league.db`)
- `sync()` fetches bootstrap, league standings (paginated), and per-manager picks for each scored gameweek (fetched once, then cached)
- `league_eo()` computes effective ownership within the league (captains count double)
- `report()` generates: table, rival grid (≤8 managers), head-to-head diffs, exposure/edge analysis, league differentials, captaincy split, chip history
- API requests are rate-limited with `PAUSE = 0.4` — do not remove this

**`planner/fpld-planner.jsx`** — React artifact (not a standalone app). Five-gameweek transfer planner with squad editing, FT roll tracking, hit counting, budget validation, and the same risk-dial logic. State persists via `window.storage`. Exports a text summary for pasting into chat.

**`config.json`** — contains `team_id`, `league_id`, `horizon`, `watchlist`, and optional `squad_fallback`. IDs are public. The repo copy has real IDs filled in.

## Key design decisions

- The FPL API is undocumented and field names change between seasons. If a stat reads zero across the board, a field was likely renamed.
- `norm()` handles accent-insensitive matching (Ødegaard → Odegaard, Dúbravka → Dubravka) using Unicode decomposition plus a manual transliteration table for Nordic/special characters.
- Selling price isn't exposed by the API, so budget math uses current price and drifts once players rise.
- Price-change pressure uses net transfers as a proxy — FPL's real formula is private.
- The playbook (`docs/playbook.md`) defines the risk-dial mechanic and chip strategy that the scripts implement. The dial logic in code must stay consistent with the playbook thresholds.
