# Tutorial: your first brief in ten minutes

This walks you from a fresh clone to reading your first daily brief. By the
end you'll have the brief running, your league connected, and the transfer
planner open in your browser.

**You need:** Python 3.9+, a browser, and your FPL account logged in.

---

## 1. Find your FPL IDs

Open the FPL website and log in.

**team_id** — click the *Points* tab. The URL looks like:

```
https://fantasy.premierleague.com/entry/1234567/event/1
```

The number after `entry` is your team_id. Write it down.

**league_id** — open your mini-league page. The URL looks like:

```
https://fantasy.premierleague.com/leagues/987654/standings/c
```

That number is your league_id.

## 2. Create your config

```bash
python3 fpld_brief.py --init
```

This creates `~/.fpld/config.json`. Open it and fill in your IDs:

```json
{
  "team_id": 1234567,
  "league_id": 987654,
  "horizon": 5,
  "watchlist": ["Saka", "Palmer", "Gyökeres"]
}
```

The `watchlist` tracks players you don't own. You'll get their price moves
and injury news in the brief, which is how you spot a transfer target before
it rises.

## 3. Add your squad (pre-season only)

The FPL API doesn't return your picks until GW1 has been scored. Before that,
add your 15 by name:

```json
"squad_fallback": [
  "Kinsky", "Dúbravka", "Ben White", "Maguire", "Ballard",
  "De Cuyper", "O'Shea", "B.Fernandes", "Mbeumo", "Tzolis",
  "Ødegaard", "Gómez", "Haaland", "João Pedro", "Calvert-Lewin"
]
```

Names must match FPL's own short names. If you're unsure how FPL spells
someone:

```bash
python3 fpld_brief.py --find odegaard
```

```
  "Ødegaard"  —  Martin Ødegaard (ARS, £6.5m)
```

Use exactly what appears in the quotes.

## 4. Run your first brief

```bash
python3 fpld_brief.py --print
```

You should see a Markdown brief with:
- Deadline countdown
- Your squad mapped across the next five fixtures
- Three proposed replacements (once the season has started and form data exists)
- A captain shortlist

The brief is also saved to `~/.fpld/briefs/YYYY-MM-DD.md`.

## 5. Check your league connection

```bash
python3 fpld_league.py --peek
```

This confirms your IDs work and shows the league name and member count.
If you see an error, double-check your league_id — it must be a classic
league, not head-to-head.

## 6. Sync league data (after GW1)

Once the first gameweek has been scored:

```bash
python3 fpld_league.py --sync --report
```

This fetches every rival's squad, captain, and chips, stores them in a local
SQLite database, and writes a league intelligence report. The first sync
takes a minute or two (it's fetching one page per rival per gameweek at
0.4s each). Subsequent syncs only fetch new gameweeks.

The report lands in `~/.fpld/reports/league-YYYY-MM-DD.md`.

## 7. Open the transfer planner

```bash
cd planner && npm install && npm run dev
```

Open `http://localhost:5173/fpld/` in your browser. You'll see your squad
preloaded, the risk dial, and five gameweek cards where you can plan
transfers, set captains, and track chips.

Edit the squad details to match your actual team. Everything saves
automatically to your browser.

## 8. The daily loop

That's the setup. From here, the intended daily cycle is:

1. The brief runs each morning (manually, via cron, or via GitHub Actions)
2. You skim it — most days nothing changed, which is the point
3. When something moves (injury, price change, fixture swing), paste the
   brief into a Claude chat along with your playbook
4. Work the decision, then apply it on the FPL site before the deadline

See [How-to: automate the daily brief](how-to.md#automate-the-daily-brief)
for scheduling options, and [the playbook](playbook.md) for decision
strategy.
