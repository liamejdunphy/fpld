# fpld — setup

FPL + LD. Daily brief and mini-league tracker.

No dependencies. Python 3.9 or later, stdlib only.

## 1. Find your IDs

- **team_id** — log into FPL, open the *Points* tab. URL reads `/entry/1234567/event/1`. The number after `entry` is yours.
- **league_id** — open your mini-league. URL reads `/leagues/987654/standings/c`. That number.

## 2. First run

```bash
python3 fpld_brief.py --init
```

Creates `~/.fpld/config.json`. Fill in:

```json
{
  "team_id": 1234567,
  "league_id": 987654,
  "horizon": 5,
  "watchlist": ["Saka", "Palmer", "Gyökeres"]
}
```

`watchlist` tracks players you don't own — you'll get their price moves and injury news too, which is how you catch a rise before it happens.

Then:

```bash
python3 fpld_brief.py --print
```

Brief lands in `~/.fpld/briefs/YYYY-MM-DD.md`.

## 3. Before GW1 finishes

The picks endpoint returns nothing until a gameweek has completed, so until then add your 15 by name to `config.json`:

```json
"squad_fallback": ["Kinsky","Dúbravka","Ben White","Maguire","Ballard",
  "De Cuyper","O'Shea","B.Fernandes","Mbeumo","Tzolis","Ødegaard",
  "Gómez","Haaland","João Pedro","Calvert-Lewin"]
```

Names must match FPL's own short names. If one doesn't resolve it's silently skipped — check the squad table lists all 15, and adjust spelling if not. Once GW1 is scored the script switches to the API automatically and you can delete this.

## 4. Run it daily

**macOS / Linux** — `crontab -e`, then:

```
0 8 * * * /usr/bin/python3 /path/to/fpld_brief.py >> ~/.fpld/log.txt 2>&1
```

8am daily. Price changes lock in around 01:30 UK time, so any morning slot catches them.

**macOS, if cron is blocked by permissions** — use `launchd` instead: put a `.plist` in `~/Library/LaunchAgents/` with `StartCalendarInterval`, then `launchctl load` it.

**Windows** — Task Scheduler → Create Basic Task → Daily → Start a program → `python.exe`, arguments `C:\path\to\fpld_brief.py`.

To get it on your phone, point the output at a synced folder (iCloud, Dropbox, Obsidian vault) by setting `FPLD_HOME`.

## 5. The confirm loop

Nothing is ever applied. The FPL API is read-only, so every proposal needs you to make the transfer yourself on the site. The intended cycle:

1. Script writes the brief each morning
2. You skim it — most days it says nothing changed, which is the point
3. When something moves, paste the brief into our chat
4. We work the decision through the playbook, and you apply it before the deadline

## What the scores mean

A shortlist filter, not a points projection: form 32%, fixture difficulty over your horizon 28%, points per million 22%, attacking threat or defensive contribution 18%, all scaled down for blank gameweeks. Anyone flagged or under 60 minutes played scores zero so they surface as replacement candidates.

Deliberately simple and legible. If you want to reweight it, the `score()` function is eight lines.

## Known limits

- Selling price isn't exposed by the API, so budget maths uses current price. Diverges once players rise.
- Price-change pressure uses net transfers as a proxy. FPL's real formula is private — treat it as a hint.
- Field names change between seasons. If a column reads zero across the board, FPL renamed something; tell me and I'll patch it.
