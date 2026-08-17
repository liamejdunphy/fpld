# fpld — FPL assistant, 2026/27

**FPL + LD.** A daily Fantasy Premier League briefing and a stateful
mini-league tracker. Reads the public FPL API, stores history in SQLite,
writes Markdown.

**It never writes anything to FPL.** The API is read-only, so every suggestion
is a proposal you apply yourself before the deadline.

```
config.json                    your team_id and league_id (already filled in)
fpld_brief.py                  daily brief: prices, injuries, fixtures, proposals
fpld_league.py                 mini-league intelligence: rival squads, league EO
fpld_xpts.py                   expected points model (ML, stdlib only)
planner/                       five-gameweek transfer planner (Vite + React)
docs/tutorial.md               first-time walkthrough, zero to first brief
docs/how-to.md                 task-oriented recipes (automate, deploy, etc.)
docs/playbook.md               season strategy: risk dial, chip plan, calendar
data/                          SQLite database, briefs, daily state (committed)
.github/workflows/daily.yml    runs it at 07:00 UTC and commits the output
.github/workflows/planner.yml  deploys the planner to GitHub Pages on push
```

New here? Start with the **[tutorial](docs/tutorial.md)**. Already set up?
See the **[how-to guides](docs/how-to.md)**.

## Run it locally

Python 3.9+, no dependencies.

```bash
mkdir -p ~/.fpld && cp config.json ~/.fpld/
python3 fpld_league.py --peek          # check IDs, league name, member count
python3 fpld_brief.py --print          # today's brief
python3 fpld_brief.py --find odegaard  # check how FPL spells a name
python3 fpld_league.py --sync --report # league tables (needs GW1 scored)
```

## Expected points model

ML-powered player scoring. Trains a per-position linear regression on
historical FPL data (multiple seasons), then predicts expected points for
every player. Replaces the hand-tuned heuristic in the brief when available.

```bash
python3 fpld_xpts.py --pull --train    # one-off: fetch history + train (~5 min)
python3 fpld_xpts.py --predict         # predict next GW for all players
python3 fpld_xpts.py --predict --league # add league-differential xPts
```

After the first pull, daily runs only fetch incremental updates. The brief
automatically uses xPts for proposals and captaincy when a model exists.

League-differential xPts adjusts predictions for your mini-league: a player
everyone owns is worth less to you than one nobody has. This is the edge no
public FPL tool offers.

## Transfer planner

A standalone React app for planning your next five gameweeks — transfers,
captains, chips, budget tracking, and the risk dial.

```bash
cd planner && npm install && npm run dev
```

Opens at `http://localhost:5173/fpld/`. State is saved in your browser's
localStorage. Hit **Build Summary** to export a text block you can paste
into a Claude chat before each deadline.

Deploys automatically to GitHub Pages when you push changes to `planner/`
on main. To enable: repo Settings → Pages → Source → **GitHub Actions**.

## Run it on GitHub

1. Push this repo (private is fine — `config.json` holds only public IDs)
2. Settings → Actions → General → Workflow permissions → **Read and write**
3. Settings → Pages → Source → **GitHub Actions** (for the planner)
4. Actions tab → *FPL daily brief* → **Run workflow** to test it
5. It then runs daily and commits to `data/`

Every run is a commit, so you get a permanent history. By March you can
`git log data/` and see exactly what your squad looked like in GW12 and
what you talked yourself into.

### Two workflows

| Workflow | Schedule | What it does |
|---|---|---|
| `daily.yml` | 07:00 UTC daily | Brief + league sync + xPts. Posts a GitHub Issue. |
| `deadline.yml` | Fri 12:30 + Sat 05:00 UTC | Same pipeline, posts a combined brief + league report as a "deadline pack" Issue. |

All databases (`league.db`, `xpts.db`, model weights) are persisted in `data/`
and restored each run, so league history accumulates across runs.

### Phone workflow (deadline day)

1. Get the GitHub notification (email or GitHub mobile app)
2. Open the **deadline-pack** Issue — brief + league report in one place
3. Copy it into Claude on your phone and ask it to pick your team
4. You can also trigger either workflow manually from the Actions tab

### Claude Code agents

Four agents in `.claude/agents/` for interactive use:

| Agent | Role | Model |
|---|---|---|
| `fpl-scout` | Player research — fitness, form, sentiment | Sonnet |
| `fpl-coach` | Gameweek decisions — XI, captain, transfers, chips | Opus |
| `fpl-analyst` | Rival intelligence — EO edges, transfer patterns | Sonnet |
| `fpl-quant` | ML pipeline — train, diagnose, improve the model | Opus |

## What you get each morning

**`data/briefs/YYYY-MM-DD.md`**
- Deadline countdown and your current risk-dial mode
- Overnight injury flags and price changes, for your squad *and* watchlist
- **Fixture alerts** — double and blank gameweeks flagged for every team in your horizon
- **Price watch** — players on your squad or watchlist near a price rise or fall (net transfer thresholds)
- Your 15 mapped across the next five fixtures with difficulty, DGW/blank annotations
- Three proposed replacements with candidates
- Captain shortlist

**`data/reports/league-YYYY-MM-DD.md`**
- League table with your gap to the leader
- **Rival grid** — a per-manager matrix of every split pick (leagues of 8 or fewer)
- **Head to head** — for each rival ahead of you, exactly what separates your squads
- **Rival moves** — exactly what transfers each rival made this gameweek
- **Your exposure** — what rivals own that you don't
- **Your edge** — your XI players that are rare in the league
- **League differentials** — in form, popular globally, absent locally
- Captaincy split and which rivals have burned which chips

The last four are the point. Global ownership tells you what the world does.
League effective ownership tells you about the people who can actually beat you.

## Timeline

| When | What works |
|---|---|
| Before GW1 deadline | `--peek`, daily brief. No league data exists yet. |
| After GW1 is scored | Everything. First sync captures every rival's opening squad. |
| GW10 onward | Transfer patterns and chip usage per rival become readable. |

Set the schedule now so it collects from GW1 rather than backfilling.

## Caveats, honestly

- **Scores are a shortlist filter, not a projection.** Form 32%, fixtures 28%,
  points per million 22%, threat 18%, scaled for blanks. Legible on purpose —
  `score()` is eight lines. Use it to surface candidates, not to decide.
- **Selling price isn't in the API.** Budget maths uses current price and
  drifts once players rise.
- **Price-change pressure is a proxy.** Net transfers only; FPL's real formula
  is private.
- **The API is undocumented.** Field names change between seasons. If a column
  reads zero across the board, something got renamed.
- Requests are paced at 0.4s. Don't remove that.
- Squad names in `squad_fallback` are matched accent-insensitively, and anything
  unmatched is reported on stderr rather than silently dropped. Use `--find`
  to get FPL's exact spelling.
