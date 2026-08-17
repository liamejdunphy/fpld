# FPL 2026/27 — Season Playbook

**How to use this:** paste this whole file at the start of a new chat before each deadline, with Sections 2 and 7 updated. That gives me your full state instantly and keeps advice consistent week to week.

---

## 1. My profile

- **Track record:** regular player, mid-table mini-league finishes
- **Goal this season:** win the mini-league
- **Engagement:** deep dive every gameweek
- **Strategy stance:** risk level is *not fixed* — it scales to my position (see Section 3)

---

## 2. Current state — UPDATE EACH WEEK

```
Gameweek:
Squad (GK/DEF/MID/FWD):
Bench order:
Captain / Vice:
Bank:                    Team value:
Free transfers:          (rolls up to 5)
Overall rank:            Points:
Mini-league rank:        Points behind leader:
Gameweeks remaining:
Chips left — 1st set:    (expire GW19)
Chips left — 2nd set:
Flagged / injured:
```

---

## 3. The risk dial (core mechanic)

Each week, compute:

**Pressure = (points behind mini-league leader) ÷ (gameweeks remaining)**

| Pressure | Mode | What it means |
|---|---|---|
| Negative (I'm leading) | **Shield** | Mirror the chasers. Match their captain. Own what they own. Avoid unique picks — a differential that hits helps them, not me. Take the draw. |
| 0 – 0.5 | **Safe** | Template core, template captain, no hits. Grind the gap down on transfers alone. |
| 0.5 – 1.5 | **Balanced** | One calculated differential (10–20% owned). Template captain unless the alternative is within ~0.5 xPts. |
| 1.5 – 3.0 | **Aggressive** | 2–3 differentials under 10% owned. Off-template captain when expected points are close. Hits acceptable if they buy a genuine edge. |
| Over 3.0 | **Swing** | Contrarian captain. Deliberately low-ownership squad. Spend chips on maximum-variance weeks, not safe ones. Playing for the tail, not the median. |

**Notes on using it honestly:**
- Run the number against both my mini-league leader *and* my overall rank target. If they disagree, mini-league wins — that's the stated goal.
- Before GW10, cap the dial at Balanced regardless of the number. Early-season gaps are noise, and there's too much season left to burn value chasing them.
- After GW30, shift one band more aggressive than the number says. Fewer weeks left means fewer chances for variance to work.
- If leading, the discipline is *boredom*. Shield mode should feel dull. That's correct.

---

## 4. Weekly deadline routine

Work through in order. Don't skip to transfers.

1. **Damage report** — injuries, suspensions, flags, minutes concerns in my 15.
2. **Compute the risk dial** — get the mode before making any decision, so the mode frames the decisions rather than the reverse.
3. **Fixture window** — next 4–6 gameweeks. Which teams are entering a good run, which are exiting one.
4. **Underlying form** — xG/xA, shots in the box, big chances, set-piece duties. Trust volume over one-off returns.
5. **DefCon check** — are my defenders and defensive mids actually hitting thresholds? (10 CBIT for DEF, 12 CBIRT for MID/FWD.) A defender averaging 7 isn't a DefCon asset, he's a clean-sheet punt.
6. **Transfer decision** — including the option to roll. Rolling to 2 is usually stronger than a marginal move; rolling past 3 rarely is.
7. **Hit maths** — a -4 needs to gain 4+ points over the *remaining horizon*, not just this week. In Safe/Shield mode: no hits. In Swing mode: hits are cheap.
8. **Captain** — top 3 candidates with reasoning, then apply the dial to choose between them.
9. **Bench order** — actually set it. Free points get left on benches every season.
10. **Chip check** — does this week trigger anything in Section 5?
11. **Log it** — add to Section 7.

---

## 5. Chip plan

**Structure:** two sets of four. First set (Wildcard, Free Hit, Bench Boost, Triple Captain) **must be used before the GW19 deadline, Saturday 2 January 13:30 GMT.** Unused chips are lost, not carried over. Second set refreshes for GW20–38. One chip per gameweek maximum.

**First half — the trap to avoid:** hoarding chips waiting for double gameweeks that may not arrive before January. First-half doubles are rare. A Bench Boost on 15 clean fixtures is a perfectly good Bench Boost.

Provisional shape (revisit at each landmark, don't lock now):

- **Wildcard 1** — target the first genuine fixture swing, likely around the GW5–6 international break given the three-week gap. Latest sensible: GW12.
- **Bench Boost 1** — 1–2 weeks after Wildcard 1, while the squad is deep and everyone's fit.
- **Triple Captain 1** — best premium in his highest-ceiling home fixture before GW19. Doesn't need a double.
- **Free Hit 1** — hold as insurance for a blank, a fixture pile-up, or an injury crisis. If GW17 arrives unused, play it on the best available fixture set rather than lose it.
- **Second set** — traditional usage: Wildcard on the spring fixture swing, Free Hit on the blank, Bench Boost and Triple Captain on the doubles.

**Dial interaction:** in Swing mode, chips go on high-variance weeks (a differential triple captain, a Free Hit stacked with low-owned assets). In Shield mode, chips go where the chasers are going — matching their chip week neutralises it.

---

## 6. Season calendar

| Landmark | Why it matters |
|---|---|
| GW1 deadline — Fri 21 Aug, 18:30 BST | Season opens: Arsenal v Coventry |
| GW5 → GW6 gap, 21 Sept – 6 Oct | Merged Sept/Oct international break. Three weeks. Prime Wildcard 1 window and full squad reassessment. |
| November international break | Second reassessment. Check chip burn-down against GW19. |
| **GW19 deadline — Sat 2 Jan, 13:30 GMT** | **Hard expiry, first chip set.** Work backwards from here from GW12. |
| GW20 | Second chip set unlocks. Full reset of the plan. |
| Jan/Feb | Blank and double gameweeks begin to appear. Free Hit and Bench Boost territory. |
| GW30+ | Shift the dial one band aggressive. Endgame. |

---

## 7. Decision log — APPEND EACH WEEK

Keep this short. The point is spotting my own patterns, not writing a diary.

```
GW__ | Mode: ______ | Transfer(s): ______ | Captain: ______
Result: ___ pts (avg ___) | OR: ______ | ML gap: ______
Call I'd repeat:
Call I wouldn't:
```

**Review at GW10, GW19, GW28.** Look for recurring errors: knee-jerk transfers after a bad captain, chasing last week's points, benching the right player, taking hits in Safe mode.

---

## 8. Standing instructions for Claude

- Always compute the risk dial before recommending anything, and state the mode explicitly.
- Search for current data — prices, injuries, ownership, press conferences, fixture changes. Don't rely on memory; the season moves weekly.
- Give me the top 3 options with reasoning, not a single answer. I make the call.
- Flag when I'm deviating from my own mode — especially taking risks while leading, or playing safe while far behind.
- Push back on knee-jerk moves. If I want to transfer out a player who returned zero but has strong underlying numbers, say so.
- Prices in £m, distances metric where relevant.
