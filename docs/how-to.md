# How-to guides

Task-oriented recipes. Each section is self-contained — jump to what you need.

---

## Automate the daily brief

### macOS / Linux — cron

```bash
crontab -e
```

Add:

```
0 8 * * * /usr/bin/python3 /path/to/fpld_brief.py >> ~/.fpld/log.txt 2>&1
```

8am daily. Price changes lock in around 01:30 UK time, so any morning
slot catches them.

### macOS — launchd (if cron is blocked by permissions)

Create `~/Library/LaunchAgents/com.fpld.brief.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.fpld.brief</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/fpld_brief.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/you/.fpld/log.txt</string>
  <key>StandardErrorPath</key>
  <string>/Users/you/.fpld/log.txt</string>
</dict>
</plist>
```

Then load it:

```bash
launchctl load ~/Library/LaunchAgents/com.fpld.brief.plist
```

### Windows — Task Scheduler

Task Scheduler → Create Basic Task → Daily → Start a program →
`python.exe`, arguments `C:\path\to\fpld_brief.py`.

### GitHub Actions

Push the repo, then:

1. Settings → Actions → General → Workflow permissions → **Read and write**
2. Actions tab → *FPL daily brief* → **Run workflow** to test
3. It runs at 07:00 UTC daily and commits output to `data/`

Two workflows are included:

- **`daily.yml`** — runs at 07:00 UTC. Brief + league sync + xPts. Creates a
  GitHub Issue labelled `daily-brief`.
- **`deadline.yml`** — runs 6 hours before typical deadlines (Fri 12:30 UTC,
  Sat 05:00 UTC). Creates a combined brief + league report Issue labelled
  `deadline-pack`.

All databases are persisted in `data/` between runs — league history, xPts
training data, and model weights accumulate automatically.

Every run is a commit, so `git log data/` gives you a permanent history.

---

## Get briefs on your phone

Point the output at a synced folder by setting `FPLD_HOME`:

```bash
export FPLD_HOME=~/Library/Mobile\ Documents/com~apple~CloudDocs/fpld
python3 fpld_brief.py --print
```

Works with iCloud Drive, Dropbox, or an Obsidian vault. The brief is plain
Markdown so it renders natively in most note apps.

---

## Add or remove watchlist players

Edit `~/.fpld/config.json`:

```json
"watchlist": ["Saka", "Palmer", "Gyökeres", "Semenyo"]
```

Use FPL's short names. If you're not sure of the spelling:

```bash
python3 fpld_brief.py --find semenyo
```

Watchlist players appear in the overnight changes section (price moves,
injury flags) and in the price watch alerts.

---

## Read the league report

```bash
python3 fpld_league.py --sync --report
```

Always `--sync` first to fetch the latest data. The report includes:

- **Table** — your rank and gap to the leader
- **Rival grid** — who owns what (leagues of 8 or fewer)
- **Head to head** — for each rival ahead of you, exactly which players
  separate your squads
- **Rival moves** — what transfers each rival made this gameweek
- **Your exposure** — what rivals own that you don't (every point these
  score costs you ground)
- **Your edge** — your starting XI players that are rare in the league
- **League differentials** — in form globally, absent locally
- **Captaincy** — who your rivals captained
- **Chips** — who has burned which chips

Run `--sync` without `--report` if you just want to collect data silently
(e.g., from a cron job that captures history even when you don't read it).

---

## Set up the expected points model

First-time setup (takes ~5 minutes to fetch all player histories):

```bash
python3 fpld_xpts.py --pull --train
```

This fetches per-gameweek data for every player across all available
seasons from the FPL API, then trains a per-position linear regression.
The model is saved to `~/.fpld/xpts_model.json`.

After the initial pull, subsequent runs only fetch players not yet pulled
today:

```bash
python3 fpld_xpts.py --pull --train --predict
```

Once a model exists, the daily brief automatically uses xPts for transfer
proposals and captaincy rankings instead of the hand-tuned heuristic.

### Predict with league context

```bash
python3 fpld_xpts.py --predict --league
```

This loads your league's effective ownership data and computes
league-differential xPts: a player everyone in your league owns is worth
less to you than a player nobody has. Requires `fpld_league.py --sync`
to have been run first.

### Retrain during the season

Retrain weekly (or whenever you pull fresh data) to let the model learn
from the current season:

```bash
python3 fpld_xpts.py --pull --train
```

The model prints its learned weights each time. Watch for:
- **R²** — how much variance the model explains (0.15+ is decent for FPL)
- **MAE** — average error in predicted points (2.0 or below is solid)
- **Feature weights** — which factors matter most this season

### View the fixture grid

Full-season fixture difficulty table for all 20 teams:

```bash
python3 fpld_brief.py --fixtures
```

Saved to `~/.fpld/fixtures.md`. Use it to spot Wildcard windows, Free
Hit targets, and long-term transfer arcs.

---

## Use the transfer planner

```bash
cd planner && npm run dev
```

Open `http://localhost:5173/fpld/`.

1. Set your **points behind leader** and **gameweeks left** — the risk
   dial updates automatically
2. Edit the **squad** to match your current team (click the squad button
   to expand)
3. Set your **bank** and **free transfers**
4. For each gameweek card, click **+ Add Transfer** to plan moves
5. Select who goes out (dropdown), type who comes in with their club and
   price
6. Set a **captain** and optionally a **chip** for each week
7. The sidebar tracks FT rollover, budget, and hits automatically
8. Click **Build Summary** to export a text block for pasting into a
   Claude chat

The planner validates squad rules in real time: max 3 per club, correct
position counts, and budget. Errors show in red on the gameweek card.

---

## Deploy the planner to GitHub Pages

1. Push the repo to GitHub
2. Settings → Pages → Source → **GitHub Actions**
3. Any push to `planner/` on main triggers a build and deploy

The planner will be available at `https://<username>.github.io/fpld/`.

---

## Prepare for a deadline chat

Before each deadline, paste three things into a new Claude chat:

1. **The playbook** — copy the full contents of `docs/playbook.md` with
   Sections 2 and 7 updated
2. **Today's brief** — from `~/.fpld/briefs/YYYY-MM-DD.md`
3. **The planner summary** — click Build Summary in the planner and copy
   the text block

This gives Claude your full state: strategy, current squad, league
position, fixtures, proposals, and your planned transfers for review.

---

## Handle a player name that won't match

If a name in `squad_fallback` isn't resolving (your squad table shows
fewer than 15), the name doesn't match FPL's short name.

```bash
python3 fpld_brief.py --find fernandes
```

This searches FPL's database for matching names. Use the exact string
from the `"web_name"` column (the one in quotes).

Common gotchas:
- `B.Fernandes` not `Bruno Fernandes`
- `Ødegaard` not `Odegaard` (the script handles accents, but check anyway)
- `João Pedro` not `Joao Pedro`

Unmatched names are reported on stderr, not silently dropped.

---

## Interpret the scores

**Transfer score** (`score()`) — a shortlist filter, not a points
projection:

| Weight | Factor |
|---|---|
| 32% | Recent form (PPG, capped at 8.0) |
| 28% | Fixture difficulty over your horizon |
| 22% | Points per million (value) |
| 18% | Attacking threat (xGI/90) or defensive contribution |

Players who are flagged or under 60 minutes played score zero, which is
how they surface as replacement candidates. Premiums score low by design
(the value weight penalises expensive players) — this is deliberate.
Never use this score to pick a captain.

**Captain score** (`captain_score()`) — separate ranking based on ceiling:
- Fixture difficulty of the *next game only* (not the full horizon)
- Home advantage
- Attacking threat or defensive contribution
- Position ceiling (FWD > MID > DEF > GK)
- Price is deliberately excluded — you're doubling points, not buying them

---

## Understand the risk dial

The dial computes: **pressure = points behind / gameweeks remaining**

| Pressure | Mode | Meaning |
|---|---|---|
| Negative (leading) | SHIELD | Mirror the chasers. Match their captain. Avoid differentials. |
| 0 – 0.5 | SAFE | Template core, template captain, no hits. |
| 0.5 – 1.5 | BALANCED | One calculated differential. |
| 1.5 – 3.0 | AGGRESSIVE | 2–3 low-ownership picks. Off-template captain. |
| Over 3.0 | SWING | Contrarian everything. Chips on max-variance weeks. |

Before GW10, cap at BALANCED regardless. After GW30, shift one band
more aggressive. See `docs/playbook.md` Section 3 for the full
decision framework.

---

## Use the Claude Code agents

Four agents in `.claude/agents/` act as your FPL backroom staff:

| Agent | What it does | When to use |
|---|---|---|
| `fpl-scout` | Player research — fitness, injuries, form, community sentiment | "Is Shaw fit?" / "Best 6.5 mid?" |
| `fpl-coach` | Gameweek decisions — starting XI, captain, transfers, chips | "Pick my team for GW3" |
| `fpl-analyst` | Rival intelligence — EO edges, transfer patterns, league positioning | "What are my rivals doing?" |
| `fpl-quant` | ML model management — retrain, diagnose, evaluate predictions | "Retrain and check model health" |

### From Claude Code (laptop)

Ask naturally and the right agent activates, or call one explicitly:

```bash
claude  # then ask "scout Shaw for me" or "pick my GW3 team"
```

### From your phone (deadline day)

1. Open the **deadline-pack** GitHub Issue (arrives ~6h before deadline)
2. Copy the brief + league report
3. Open Claude on your phone, paste it, and ask: "Pick my team for this GW"

Claude doesn't have the agent files on mobile, but the brief contains all
the data the coach agent would read — squad, fixtures, xPts, proposals,
captaincy, risk dial. You get the same quality advice.
