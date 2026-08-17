# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only Fantasy Premier League assistant for the 2026/27 season. Three Python scripts read the public FPL API: a daily brief, a league tracker, and an expected points model. A standalone React app provides a five-gameweek transfer planner. Nothing ever writes to FPL.

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

# Expected points model — one-off pull + train (~5 min first time)
python3 fpld_xpts.py --pull --train

# Predict with league-differential context
python3 fpld_xpts.py --predict --league

# Full-season fixture difficulty grid
python3 fpld_brief.py --fixtures
```

Override the data directory with `FPLD_HOME` env var or `--home` flag. Default is `~/.fpld/`.

There are no tests. There is no linter configured.

## Architecture

**`fpld_brief.py`** — daily brief pipeline:
- `get()` fetches from the FPL API (stdlib `urllib`, 0.4s pacing, SSL context)
- `build()` transforms bootstrap + fixtures into a player model with fixture-difficulty runs over a configurable horizon
- `squad_of()` resolves your 15 from the API picks endpoint, falling back to `squad_fallback` names in config (matched accent-insensitively via `norm()`)
- `score()` is the fallback transfer heuristic: form 32%, fixtures 28%, points-per-million 22%, threat/defence 18%, scaled for blanks. Replaced by xPts when a model is available.
- `captain_score()` is a separate ceiling-based ranking (no price term), also replaced by xPts when available
- `load_xpts()` loads ML predictions from `xpts_predictions.json` if present — the brief auto-switches to xPts for proposals and captaincy
- `diff()` compares today's model against `state.json` to detect overnight price changes and flag changes
- `dial()` computes the risk mode (SHIELD/SAFE/BALANCED/AGGRESSIVE/SWING) from points-behind and gameweeks-left

**`fpld_league.py`** — stateful league tracker:
- Stores all rival squads, captains, transfers, and chips in SQLite (`~/.fpld/league.db`)
- `sync()` fetches bootstrap, league standings (paginated), and per-manager picks for each scored gameweek (fetched once, then cached)
- `league_eo()` computes effective ownership within the league (captains count double)
- `snoop_transfers()` fetches each rival's transfer history from the API and stores in `transfer_history` table
- `report()` generates: table, rival grid (≤8 managers), head-to-head diffs, recent rival activity (3-GW transfer patterns), rival moves, exposure/edge, league differentials, EO-aware captain recommendation, season tracker (captain hit rate, bench leak, transfer ROI), chip ammunition per rival, captaincy split, chip history
- API requests are rate-limited with `PAUSE = 0.4` — do not remove this

**`fpld_xpts.py`** — expected points model:
- `pull()` fetches `element-summary/{id}/` for every player — per-GW current season data + per-season historical summaries. Full pull on first run (~5 min), incremental (only new-today) on subsequent runs.
- `train()` fits per-position (GK/DEF/MID/FWD) ridge regression via the normal equation. Features: form, FDR, home/away, xGI/90, minutes, PPG, price, ownership. Pure Python linear algebra — no numpy/sklearn. Saves a maturity gate: the model tracks real per-GW samples vs synthetic historical samples and marks itself immature when trained mostly on season averages.
- `predict_all()` produces xPts per player for next GW and 5-GW horizon. Saved to `xpts_predictions.json` (with `_maturity` metadata) for consumption by the brief. The brief only switches to xPts as primary ranking when the model is mature (≥100 real samples, ≥30% real). When immature, heuristic scores rank proposals and xPts appear as a secondary reference column.
- `differential_xpts()` adjusts predictions using league EO: high-EO players are worth less (everyone benefits), low-EO players are where you gain ground.
- Data stored in `~/.fpld/xpts.db` (SQLite): `player_history` (past seasons), `player_gw_detail` (per-GW stats), `player_meta`.

**`planner/`** — standalone Vite + React app. Five-gameweek transfer planner with squad editing, FT roll tracking, hit counting, budget validation, and the same risk-dial logic. State persists via localStorage. Exports a text summary for pasting into chat.

**`config.json`** — contains `team_id`, `league_id`, `horizon`, `watchlist`, and optional `squad_fallback`. IDs are public. The repo copy has real IDs filled in.

## Key design decisions

- The FPL API is undocumented and field names change between seasons. If a stat reads zero across the board, a field was likely renamed.
- `norm()` handles accent-insensitive matching (Ødegaard → Odegaard, Dúbravka → Dubravka) using Unicode decomposition plus a manual transliteration table for Nordic/special characters.
- Selling price isn't exposed by the API, so budget math uses current price and drifts once players rise.
- Price-change pressure uses net transfers as a proxy — FPL's real formula is private.
- The playbook (`docs/playbook.md`) defines the risk-dial mechanic and chip strategy that the scripts implement. The dial logic in code must stay consistent with the playbook thresholds.
