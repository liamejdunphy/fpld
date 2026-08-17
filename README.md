# fpld

**New ownership. New era.**

Welcome to the club. You've just taken over a Fantasy Premier League side, and you've brought in a full backroom staff to make sure you win the mini-league. No half measures.

The operation runs itself: a daily pipeline reads the FPL API, tracks your rivals, trains a machine learning model, and posts a briefing to your phone every morning. Before each deadline, the staff assembles and gives you a plan. You just make the call.

Nothing ever writes to FPL. Every move is yours to confirm.

---

## Meet the staff

### Gaffer — *The Manager*

> "I see the big picture. While the coach worries about Saturday, I'm thinking about the next five gameweeks. When the scout brings me a name, my first question isn't *is he good?* — it's *when do we bring him in, and who makes way?* I sequence the transfers, time the chips, and make sure we're not scrambling at the deadline because we burned our free transfers on impulse buys in GW3."

Runs the full pre-deadline operation. Chains the staff together, reviews the auto-generated 5-GW transfer plans (safe, balanced, aggressive), and delivers the final brief. Thinks in windows, not weeks.

`fpl-manager` · Opus · 30 turns

---

### Pep Talk — *The Coach*

> "The gaffer handles the transfer window. I handle matchday. Who starts, who's benched, who wears the armband. I read the risk dial and I commit — no hedging, no *it depends*. You ask me who to captain, you get a name and a reason, not a shortlist with caveats."

Makes concrete gameweek decisions: formation, starting XI, captain, bench order, and whether this is the week for a chip. Follows the playbook religiously.

`fpl-coach` · Opus · 15 turns

---

### Radar — *The Scout*

> "I'm out there every day, watching, reading, listening. Press conferences, training photos, community chatter. When someone says *is Shaw fit?*, I don't guess — I go and find out. I bring you a verdict: buy, hold, or avoid. With receipts."

Researches individual players on demand. Checks fitness, form, expected minutes, ownership trends, and what the FPL community is saying. Returns a structured scouting report.

`fpl-scout` · Sonnet · 12 turns

---

### Dossier — *The Analyst*

> "I know what your rivals had for breakfast. Who they transferred in, who they captained, which chips they've burned. While you're watching the match, I'm watching *them*. That differential edge you're sitting on? I'm the one who spotted that three of your rivals just sold the same player."

Rival intelligence specialist. Tracks league effective ownership, transfer patterns, captaincy splits, and chip ammunition. Tells you where you're exposed and where you have an edge that nobody else sees.

`fpl-analyst` · Sonnet · 12 turns

---

### Moneyball — *The Quant*

> "I don't do feelings. I do features, coefficients, and residuals. The model trains on real per-gameweek FPL data — form, fixture difficulty, home advantage, xGI, minutes, price — and spits out expected points for every player in the game. When the model says a 5.0m midfielder is projected higher than a 12.0m premium, that's not a bug. That's an edge."

Manages the xPts machine learning pipeline. Pulls data, trains per-position ridge regression models, monitors maturity (won't let an overfitted pre-season model make decisions), and produces league-differential xPts — predictions adjusted for *your* mini-league's ownership, not the global template.

`fpl-quant` · Opus · 15 turns

---

## How the operation runs

### Every morning at 07:00 UTC

The daily pipeline fires automatically via GitHub Actions:

1. **Brief** — prices, injuries, fixture flags, transfer proposals, captain shortlist
2. **League sync** — rival squads, transfers, chips, EO
3. **xPts predict** — fresh ML predictions (model retrains on Tuesdays after Monday Night Football)
4. **Plan generation** — three 5-GW transfer sequences at different aggression levels

A GitHub Issue appears on your phone with the full brief. Claude reads it and scouts any flagged players autonomously.

### Before each deadline

The manager chains the full staff: quant checks model health, scout verifies fitness, analyst pulls rival intel, then the coach delivers a team sheet. Or you just comment on the Issue — "pick my team", "scout Palmer", "should I take a hit?" — and get an answer.

### The planner

A web app at your GitHub Pages URL that shows the auto-generated transfer plans. Toggle between Safe / Balanced / Aggressive paths, tweak moves you disagree with, set captains and chips, then export the confirmed plan back to the Issue for the staff to review.

---

## Quick start

Python 3.9+, no dependencies.

```bash
# First run
mkdir -p ~/.fpld && cp config.json ~/.fpld/
python3 fpld_brief.py --print          # today's brief
python3 fpld_brief.py --find odegaard  # check FPL's spelling

# League intel (needs GW1 scored)
python3 fpld_league.py --sync --report

# ML model
python3 fpld_xpts.py --pull --train    # one-off: ~5 min
python3 fpld_xpts.py --predict --league
```

### Run it on GitHub

1. Push this repo (private is fine — `config.json` holds only public IDs)
2. Settings > Actions > General > Workflow permissions > **Read and write**
3. Settings > Pages > Source > **GitHub Actions**
4. Actions tab > *FPL daily brief* > **Run workflow**

Every run commits to `data/`, so you get a permanent history. By March you can `git log data/` and see exactly what your squad looked like in GW12.

---

## What lands on your phone each morning

**The brief** (`data/briefs/YYYY-MM-DD.md`)
- Deadline countdown and risk-dial mode
- Overnight injury flags and price changes for your squad and watchlist
- Double and blank gameweek alerts
- Price watch — players near a rise or fall
- Your 15 mapped across the next five fixtures
- Three proposed replacements with xPts
- Captain shortlist with EO context

**The league report** (`data/reports/league-YYYY-MM-DD.md`)
- League table with your gap
- Rival grid — per-manager matrix of split picks
- Head-to-head diffs for every rival ahead of you
- Rival transfers this week
- Your exposure (what they own that you don't)
- Your edge (what you own that they don't)
- Captaincy split and chip ammunition per rival

The last four are the point. Global ownership tells you what the world does. League EO tells you about the people who can actually beat you.

---

## The fine print

- **The FPL API is undocumented.** Field names change between seasons. If a stat reads zero across the board, something got renamed.
- **Selling price isn't exposed.** Budget maths uses current price and drifts once players rise.
- **xPts is a model, not a crystal ball.** It's trained on historical data and governed by a maturity gate — it won't make decisions until it has enough real per-GW samples.
- **Requests are paced at 0.4s.** Don't remove that.
- Squad names in `squad_fallback` are matched accent-insensitively (`Odegaard` finds `Odegaard`). Use `--find` to check FPL's exact spelling.
- stdlib only. No numpy, no sklearn, no Flask. Pure Python, pure football.
