# Test plan

Run through these checks to verify everything works end to end.
Tick each off as you go. Estimated total: ~15 minutes.

---

## 1. Local pipeline (laptop)

### 1a. Brief

```bash
python3 fpld_brief.py --print
```

- [x] Prints a brief with today's date
- [x] Shows 15/15 matched in the source line
- [x] Squad table shows the new squad (Gabriel, Shaw, Kayode, DWH, etc.)
- [x] Captaincy shortlist shows 3-4 players
- [x] Footer mentions xPts maturity status (immature pre-season)
- [x] File written to `~/.fpld/briefs/YYYY-MM-DD.md`

### 1b. Player lookup

```bash
python3 fpld_brief.py --find haaland
```

- [x] Finds Haaland in the local player map
- [x] Shows position, club, price

### 1c. Fixture grid

```bash
python3 fpld_brief.py --fixtures
```

- [x] Prints a full-season FDR grid for all 20 teams
- [x] Saved to `~/.fpld/fixtures.md`

### 1d. League

```bash
python3 fpld_league.py --peek
```

- [x] Shows your league name and member count
- [x] No errors (league data won't exist until GW1 is scored)

### 1e. xPts model

```bash
python3 fpld_xpts.py --pull --train --predict
```

- [x] Pull completes (may say "All players already pulled today")
- [x] Training prints per-position stats (GK, DEF, MID, FWD)
- [x] Maturity line shows `IMMATURE` (0 real samples pre-season)
- [x] Predictions table prints top 20 players
- [x] `~/.fpld/xpts_model.json` contains a `"maturity"` key with `"mature": false`
- [x] `~/.fpld/xpts_predictions.json` contains a `"_maturity"` key

---

## 2. GitHub Actions

### 2a. Daily workflow

Go to: **Actions** → *FPL daily brief* → **Run workflow**

- [x] Workflow completes green
- [x] A commit appears with message "Daily brief YYYY-MM-DD"
- [x] `data/briefs/YYYY-MM-DD.md` exists in the commit
- [x] `data/xpts.db` is updated in the commit
- [x] `data/xpts_model.json` is updated in the commit
- [x] A GitHub Issue is created with label `daily-brief`
- [x] The Issue body contains the full brief (squad table, proposals, captain)
- [x] You receive a notification (check email or GitHub mobile app)

### 2b. Deadline workflow

Go to: **Actions** → *FPL deadline pack* → **Run workflow**

- [ ] Workflow completes green
- [ ] A GitHub Issue is created with label `deadline-pack`
- [ ] The Issue body contains both the brief AND the league report (or just
      the brief if no league data exists yet)

### 2c. Database persistence

Run the daily workflow **twice** (wait for the first to finish):

- [ ] Second run does not re-pull all players (should say "already pulled today")
- [ ] `data/xpts.db` grows or stays the same size (not reset to zero)
- [ ] League data (if any) is preserved between runs

### 2d. Issue lifecycle

- [ ] After running daily workflow twice, the first day's `daily-brief` Issue
      is auto-closed with "Superseded by today's brief"
- [ ] `deadline-pack` Issues auto-close after 3 days

---

## 3. Phone workflow

### 3a. Notifications

- [ ] Install GitHub mobile app (if not already)
- [ ] Watch the repo (Settings → Notifications → Watching)
- [ ] Trigger a workflow manually from the Actions tab on your phone
- [ ] Receive a push notification when the Issue is created

### 3b. Deadline day simulation

- [ ] Open a `deadline-pack` Issue on your phone
- [ ] Copy the Issue body
- [ ] Open Claude (app or claude.ai) on your phone
- [ ] Paste the brief and ask "Pick my team for this GW"
- [ ] Verify Claude gives a concrete team sheet with captain and transfers

---

## 4. Claude Code agents (laptop only)

### 4a. Scout

```
claude
> scout Shaw for me
```

- [ ] Agent activates and searches the web
- [ ] Returns structured assessment (status, injury history, fixtures, verdict)

### 4b. Coach

```
claude
> pick my team for GW1
```

- [ ] Agent reads the brief and playbook
- [ ] Returns a team sheet with formation, captain, bench order, transfers

### 4c. Analyst

```
claude
> what are my rivals doing?
```

- [ ] Agent reads league report (or explains no data yet if pre-GW1)

### 4d. Quant

```
claude
> check model health
```

- [ ] Agent reads `xpts_model.json`
- [ ] Reports maturity status, R², MAE, any concerns

### 4e. Manager (full chain)

```
claude
> run the full deadline prep
```

- [ ] Agent runs the pipeline (brief + league + xPts)
- [ ] Scouts flagged players via web search
- [ ] Summarises league position
- [ ] Delivers a complete deadline brief with team sheet

---

## 5. Post-GW1 verification

_Run these after GW1 is scored (typically Sunday/Monday):_

### 5a. League sync

```bash
python3 fpld_league.py --sync --report
```

- [ ] Sync completes without errors
- [ ] Report includes league table with real points
- [ ] Rival squads are captured
- [ ] Transfer history is populated

### 5b. xPts with real data

```bash
python3 fpld_xpts.py --pull --train --predict --league
```

- [ ] Training shows `n real` > 0 for each position
- [ ] Maturity still shows `IMMATURE` (need ~100+ real samples)
- [ ] League-differential xPts computed successfully

### 5c. Brief with scored data

```bash
python3 fpld_brief.py --print
```

- [ ] Overnight changes section shows real price moves (if any)
- [ ] Form column is no longer all 0.0
- [ ] Proposals section has real scores (not "form is zero")
- [ ] If xPts still immature: heuristic ranks proposals, xPts shown with `*`

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Brief shows old squad | `~/.fpld/config.json` is stale | `cp config.json ~/.fpld/` |
| GH Actions fails on league sync | GW1 not scored yet | Expected — `|| true` handles it |
| xPts R² > 0.95 | Overfitting on historical averages | Expected pre-season, maturity gate handles it |
| Issue body is truncated | Brief > 65K chars | Normal — truncated to GitHub limit |
| "No model found" on predict | Haven't trained yet | Run `--pull --train` first |
| Agent doesn't activate | Wrong phrasing | Try `@fpl-scout Shaw` explicitly |
