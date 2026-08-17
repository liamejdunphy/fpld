#!/usr/bin/env python3
"""
fpld_league.py — stateful mini-league intelligence.

Builds a local SQLite history of your league: every rival's squad, captain,
transfers and chips, gameweek by gameweek. Then answers the question global
ownership can't: who is a differential *against the people you're actually
playing*.

Read-only against the FPL API. Nothing is ever applied to your team.

    python3 fpld_league.py --init
    python3 fpld_league.py --sync          # fetch and store (safe to re-run)
    python3 fpld_league.py --report        # write the league brief
    python3 fpld_league.py --sync --report

Stdlib only. Python 3.9+.
"""

import argparse
import json
import os
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://fantasy.premierleague.com/api"
HOME = Path(os.environ.get("FPLD_HOME", Path.home() / ".fpld"))
DB = HOME / "league.db"
CONFIG = HOME / "config.json"
REPORTS = HOME / "reports"
UA = "Mozilla/5.0 fpld (personal use)"
PAUSE = 0.4  # be polite; the API is unofficial and rate-limited

POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS managers (
  entry_id INTEGER PRIMARY KEY, player_name TEXT, team_name TEXT);
CREATE TABLE IF NOT EXISTS standings (
  gw INTEGER, entry_id INTEGER, rank INTEGER, total INTEGER, event_total INTEGER,
  PRIMARY KEY (gw, entry_id));
CREATE TABLE IF NOT EXISTS picks (
  gw INTEGER, entry_id INTEGER, element INTEGER, position INTEGER,
  multiplier INTEGER, is_captain INTEGER, is_vice INTEGER,
  PRIMARY KEY (gw, entry_id, element));
CREATE TABLE IF NOT EXISTS entry_gw (
  gw INTEGER, entry_id INTEGER, chip TEXT, transfers INTEGER, transfer_cost INTEGER,
  bank REAL, value REAL, bench_points INTEGER, PRIMARY KEY (gw, entry_id));
CREATE TABLE IF NOT EXISTS players (
  element INTEGER PRIMARY KEY, name TEXT, club TEXT, pos TEXT,
  price REAL, owned_global REAL, points INTEGER, form REAL, status TEXT, news TEXT);
CREATE TABLE IF NOT EXISTS player_gw (
  gw INTEGER, element INTEGER, points INTEGER, minutes INTEGER,
  PRIMARY KEY (gw, element));
CREATE INDEX IF NOT EXISTS ix_picks_gw ON picks(gw);
"""


# ------------------------------------------------------------------ fetch

def get(path, optional=False, retries=3):
    url = f"{API}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) and optional:
                return None
            if e.code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            raise SystemExit(f"FPL API {e.code} on {url}")
        except Exception:
            if attempt == retries - 1:
                if optional:
                    return None
                raise SystemExit(f"Couldn't reach {url}")
            time.sleep(2)
    return None


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ------------------------------------------------------------------ sync

def sync(conn, cfg, verbose=True):
    boot = get("bootstrap-static/")
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    events = boot.get("events", [])
    finished = [e["id"] for e in events if e.get("finished")]
    current = max(finished) if finished else 0

    rows = [(e["id"], e.get("web_name", "?"), teams.get(e["team"], "?"),
             POS.get(e.get("element_type"), "?"), num(e.get("now_cost")) / 10,
             num(e.get("selected_by_percent")), int(num(e.get("total_points"))),
             num(e.get("form")), e.get("status", "a"), (e.get("news") or "").strip())
            for e in boot["elements"]]
    conn.executemany("INSERT OR REPLACE INTO players VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    lid = cfg["league_id"]
    page, results, pending = 1, [], []
    league_name = None
    while True:
        lg = get(f"leagues-classic/{lid}/standings/?page_standings={page}&page_new_entries={page}", optional=True)
        if not lg:
            break
        league_name = (lg.get("league") or {}).get("name")
        std = lg.get("standings", {})
        results += std.get("results", [])
        ne = lg.get("new_entries", {}) or {}
        pending += ne.get("results", [])
        if not std.get("has_next") and not ne.get("has_next"):
            break
        page += 1
        time.sleep(PAUSE)

    # Before GW1 is scored, members sit in new_entries with no points yet.
    for r in pending:
        name = " ".join(filter(None, [r.get("player_first_name"), r.get("player_last_name")])) or "?"
        conn.execute("INSERT OR REPLACE INTO managers VALUES (?,?,?)",
                     (r["entry"], name, r.get("entry_name")))

    if not results:
        print(f"League '{league_name or lid}': {len(pending)} members registered, "
              f"no gameweek scored yet. Standings appear after GW1.")
    for r in results:
        conn.execute("INSERT OR REPLACE INTO managers VALUES (?,?,?)",
                     (r["entry"], r.get("player_name"), r.get("entry_name")))
        conn.execute("INSERT OR REPLACE INTO standings VALUES (?,?,?,?,?)",
                     (current, r["entry"], r.get("rank"), r.get("total"), r.get("event_total")))

    entries = [r["entry"] for r in results] or [r["entry"] for r in pending] or [cfg["team_id"]]
    if cfg["team_id"] not in entries:
        entries.append(cfg["team_id"])

    # Picks are immutable once a gameweek is scored, so fetch each exactly once.
    have = {(g, e) for g, e in conn.execute("SELECT gw, entry_id FROM picks GROUP BY gw, entry_id")}
    todo = [(g, e) for g in finished for e in entries if (g, e) not in have]
    if verbose and todo:
        print(f"Fetching {len(todo)} squad snapshots…")

    for i, (gw, entry) in enumerate(todo, 1):
        d = get(f"entry/{entry}/event/{gw}/picks/", optional=True)
        time.sleep(PAUSE)
        if not d or not d.get("picks"):
            continue
        conn.executemany("INSERT OR REPLACE INTO picks VALUES (?,?,?,?,?,?,?)",
                         [(gw, entry, p["element"], p.get("position"), p.get("multiplier", 0),
                           int(bool(p.get("is_captain"))), int(bool(p.get("is_vice_captain"))))
                          for p in d["picks"]])
        h = d.get("entry_history", {}) or {}
        conn.execute("INSERT OR REPLACE INTO entry_gw VALUES (?,?,?,?,?,?,?,?)",
                     (gw, entry, d.get("active_chip"), h.get("event_transfers", 0),
                      h.get("event_transfers_cost", 0), num(h.get("bank")) / 10,
                      num(h.get("value")) / 10, h.get("points_on_bench", 0)))
        if verbose and i % 25 == 0:
            print(f"  {i}/{len(todo)}")
        conn.commit()

    if current:
        live = get(f"event/{current}/live/", optional=True)
        if live:
            conn.executemany("INSERT OR REPLACE INTO player_gw VALUES (?,?,?,?)",
                             [(current, e["id"], e["stats"].get("total_points", 0),
                               e["stats"].get("minutes", 0)) for e in live.get("elements", [])])
    conn.commit()
    return current


# ------------------------------------------------------------------ analysis

def league_eo(conn, gw):
    """Effective ownership within the league. Captains count twice — that's the point."""
    n = conn.execute("SELECT COUNT(DISTINCT entry_id) FROM picks WHERE gw=?", (gw,)).fetchone()[0]
    if not n:
        return {}, 0
    rows = conn.execute("""
        SELECT element,
               SUM(CASE WHEN multiplier > 0 THEN 1 ELSE 0 END) AS starters,
               SUM(CASE WHEN multiplier > 1 THEN multiplier - 1 ELSE 0 END) AS extra,
               COUNT(*) AS squads
        FROM picks WHERE gw=? GROUP BY element""", (gw,)).fetchall()
    return {r[0]: {"starters": r[1], "captains": r[2], "squads": r[3],
                   "eo": 100.0 * (r[1] + r[2]) / n, "own": 100.0 * r[3] / n} for r in rows}, n


def my_squad(conn, entry, gw):
    return {r[0]: {"mult": r[1], "cap": r[2]} for r in conn.execute(
        "SELECT element, multiplier, is_captain FROM picks WHERE gw=? AND entry_id=?", (gw, entry))}


def player_map(conn):
    return {r[0]: {"name": r[1], "club": r[2], "pos": r[3], "price": r[4],
                   "global": r[5], "points": r[6], "form": r[7], "status": r[8], "news": r[9]}
            for r in conn.execute("SELECT * FROM players")}


def rival_moves(conn, gw):
    """Compare each rival's picks between gw and gw-1 to find transfers."""
    if gw <= 1:
        return {}
    prev, curr = gw - 1, gw
    entries = [r[0] for r in conn.execute(
        "SELECT DISTINCT entry_id FROM picks WHERE gw=?", (curr,)).fetchall()]
    moves = {}
    for entry in entries:
        prev_els = {r[0]: r[1] for r in conn.execute(
            "SELECT element, position FROM picks WHERE gw=? AND entry_id=?", (prev, entry))}
        curr_els = {r[0]: r[1] for r in conn.execute(
            "SELECT element, position FROM picks WHERE gw=? AND entry_id=?", (curr, entry))}
        outs = set(prev_els) - set(curr_els)
        ins = set(curr_els) - set(prev_els)
        if not outs and not ins:
            continue
        # Pair by position where possible
        paired = []
        ins_left = list(ins)
        for o in outs:
            o_pos = prev_els[o]
            match = next((i for i in ins_left if curr_els[i] == o_pos), None)
            if match:
                paired.append((o, match))
                ins_left.remove(match)
            else:
                paired.append((o, None))
        for i in ins_left:
            paired.append((None, i))
        moves[entry] = paired
    return moves


def report(conn, cfg, gw):
    P = player_map(conn)
    eo, n = league_eo(conn, gw)
    mine = my_squad(conn, cfg["team_id"], gw)
    L = [f"# League intelligence — after GW{gw}", ""]

    if not n:
        return "\n".join(L + ["_No squad data yet. Run --sync once GW1 has been scored._"])

    std = conn.execute("""SELECT s.rank, m.team_name, m.player_name, s.total, s.event_total, s.entry_id
                          FROM standings s JOIN managers m USING(entry_id)
                          WHERE s.gw=? ORDER BY s.rank""", (gw,)).fetchall()
    me = next((r for r in std if r[5] == cfg["team_id"]), None)
    L += [f"_{n} managers tracked._", "", "## Table", "",
          "| # | Team | GW | Total | Gap |", "|---|---|---|---|---|"]
    lead = std[0][3] if std else 0
    for r in std[:12]:
        mark = " ←" if r[5] == cfg["team_id"] else ""
        L.append(f"| {r[0]} | {r[1]}{mark} | {r[4]} | {r[3]} | {r[3] - lead:+d} |")
    L.append("")

    if me:
        behind = lead - me[3]
        left = 38 - gw
        p = behind / left if left else 0
        mode = ("SHIELD" if behind < 0 else "SAFE" if p <= 0.5 else "BALANCED" if p <= 1.5
                else "AGGRESSIVE" if p <= 3 else "SWING")
        L += [f"**{behind} points behind, {left} gameweeks left → pressure {p:.2f} → mode {mode}**", ""]

    # In a small league, aggregate ownership hides everything that matters.
    # Only split picks decide anything — what everyone owns is noise.
    if n <= 8:
        names = {r[5]: (r[1] or f"#{r[5]}") for r in std}
        order = [r[5] for r in std] or sorted(names)
        short = {e: (names[e][:11]) for e in order}
        split = [(e, d) for e, d in eo.items() if 0 < d["squads"] < n]
        split.sort(key=lambda x: (-x[1]["squads"], P.get(x[0], {}).get("name", "")))

        L += ["## Rival grid", "",
              f"_Only players some — not all — of you own. ● starting, ○ benched, "
              f"**C** captain. {len(split)} split picks out of "
              f"{len(eo)} owned league-wide._", "",
              "| Player | Pos | " + " | ".join(short[e] for e in order) + " |",
              "|---|---|" + "---|" * len(order)]

        cells = {(r[0], r[1]): (r[2], r[3]) for r in conn.execute(
            "SELECT entry_id, element, multiplier, is_captain FROM picks WHERE gw=?", (gw,))}
        for e, d in split[:25]:
            pl = P.get(e, {})
            row = []
            for entry in order:
                c = cells.get((entry, e))
                row.append("" if not c else ("**C**" if c[1] else "●" if c[0] > 0 else "○"))
            L.append(f"| {pl.get('name','?')} | {pl.get('pos','?')} | " + " | ".join(row) + " |")
        L.append("")

        # Who specifically is beating you, and with what.
        ahead = [r for r in std if r[3] > (me[3] if me else 0) and r[5] != cfg["team_id"]]
        if ahead:
            L += ["## Head to head", ""]
            for r in ahead[:4]:
                theirs = {el for (en, el) in cells if en == r[5]}
                only_them = [el for el in theirs if el not in mine]
                only_you = [el for el in mine if el not in theirs]
                nm = lambda ids: ", ".join(sorted(P.get(i, {}).get("name", "?") for i in ids)) or "—"
                L += [f"**{r[1]}** — {r[3] - (me[3] if me else 0)} ahead",
                      f"- They have, you don't: {nm(only_them)}",
                      f"- You have, they don't: {nm(only_you)}", ""]

        # Rival moves — what transfers each rival made this gameweek.
        if gw > 1:
            moves = rival_moves(conn, gw)
            rival_lines = []
            for r in std:
                entry = r[5]
                if entry == cfg["team_id"] or entry not in moves:
                    continue
                parts = []
                for out_el, in_el in moves[entry]:
                    out_name = P.get(out_el, {}).get("name", "?") if out_el else None
                    in_name = P.get(in_el, {}).get("name", "?") if in_el else None
                    if out_name and in_name:
                        parts.append(f"OUT {out_name} → IN {in_name}")
                    elif out_name:
                        parts.append(f"OUT {out_name}")
                    elif in_name:
                        parts.append(f"IN {in_name}")
                if parts:
                    team = r[1] or f"#{entry}"
                    rival_lines.append(f"- **{team}**: {', '.join(parts)}")
            if rival_lines:
                L += ["## Rival moves this gameweek", ""] + rival_lines + [""]

    def line(e, d):
        pl = P.get(e, {})
        flag = " ⚠️" if pl.get("status", "a") != "a" else ""
        return (f"| {pl.get('name','?')}{flag} | {pl.get('pos','?')} | {pl.get('club','?')} | "
                f"£{pl.get('price',0):.1f} | {d['eo']:.0f}% | {pl.get('global',0):.1f}% | "
                f"{d['eo'] - pl.get('global',0):+.0f} |")

    hdr = ["| Player | Pos | Club | £ | League EO | Global | Δ |", "|---|---|---|---|---|---|---|"]

    # Exposure: what your rivals have that you don't.
    unowned = sorted([(e, d) for e, d in eo.items() if e not in mine and d["eo"] > 0],
                     key=lambda x: -x[1]["eo"])
    risk = [x for x in unowned if x[1]["eo"] >= 25][:10] or unowned[:10]
    L += ["## Your exposure", "",
          "_Owned by rivals, not by you. Every point these score costs you ground._", ""] + hdr
    L += [line(e, d) for e, d in risk] or ["| — | | | | | | |"]
    L.append("")

    # Edge: what you have that they don't.
    edge = sorted([(e, eo.get(e, {"eo": 0, "own": 0, "squads": 0})) for e in mine
                   if mine[e]["mult"] > 0 and eo.get(e, {"eo": 100})["eo"] <= 35],
                  key=lambda x: x[1]["eo"])[:10]
    L += ["## Your edge", "",
          "_In your XI, rare in the league. This is where you gain._", ""] + hdr
    L += [line(e, d) for e, d in edge] or ["| — | | | | | | |"]
    L.append("")

    # True differentials: strong globally, absent locally.
    cand = []
    for e, pl in P.items():
        if e in mine or pl["status"] != "a" or pl["form"] < 3.5:
            continue
        local = eo.get(e, {"eo": 0.0})["eo"]
        if local <= 20 and pl["global"] >= 3:
            cand.append((e, {"eo": local}, pl["form"]))
    cand.sort(key=lambda x: (-x[2], x[1]["eo"]))
    L += ["## League differentials", "",
          "_In form, but barely owned here. Ranked by form, then rarity._", ""] + hdr
    L += [line(e, d) for e, d, _ in cand[:10]] or ["| — | | | | | | |"]
    L.append("")

    # Captaincy — the biggest single swing in any mini-league.
    caps = conn.execute("""SELECT element, COUNT(*) FROM picks WHERE gw=? AND is_captain=1
                           GROUP BY element ORDER BY 2 DESC""", (gw,)).fetchall()
    if caps:
        L += [f"## Captaincy, GW{gw}", ""]
        for e, c in caps[:6]:
            m = " ← you" if mine.get(e, {}).get("cap") else ""
            L.append(f"- **{P.get(e,{}).get('name','?')}** — {c}/{n} ({100*c/n:.0f}%){m}")
        L.append("")

    # Chips are public. Knowing a rival has burned their wildcard is real information.
    chips = conn.execute("""SELECT m.team_name, e.gw, e.chip FROM entry_gw e
                            JOIN managers m USING(entry_id)
                            WHERE e.chip IS NOT NULL ORDER BY e.gw DESC LIMIT 10""").fetchall()
    if chips:
        L += ["## Chips played", ""] + [f"- GW{g}: {t} — {c}" for t, g, c in chips] + [""]

    L += ["---", "",
          "_League EO counts captains twice. Δ is league minus global: positive means your "
          "rivals are heavier on that player than the world is, so it hurts more when it hauls._"]
    return "\n".join(L)


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description="Mini-league intelligence.")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--peek", action="store_true", help="check IDs and league size before GW1")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    HOME.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(exist_ok=True)

    if a.init or not CONFIG.exists():
        if not CONFIG.exists():
            CONFIG.write_text(json.dumps({"team_id": 0, "league_id": 0, "horizon": 5, "watchlist": []}, indent=2))
        print(f"Add team_id and league_id to {CONFIG}, then run --sync --report.")
        return

    cfg = json.loads(CONFIG.read_text())
    if not cfg.get("team_id") or not cfg.get("league_id"):
        raise SystemExit(f"Set both team_id and league_id in {CONFIG}.")

    if a.peek:
        me = get(f"entry/{cfg['team_id']}/", optional=True)
        lg = get(f"leagues-classic/{cfg['league_id']}/standings/", optional=True)
        if not me:
            print(f"team_id {cfg['team_id']} not found.")
        else:
            print(f"Team: {me.get('name')} — {me.get('player_first_name','')} {me.get('player_last_name','')}".strip())
        if not lg:
            print(f"league_id {cfg['league_id']} not found.")
            return
        L = lg.get("league", {})
        scored = lg.get("standings", {}).get("results", [])
        pending = (lg.get("new_entries", {}) or {}).get("results", [])
        print(f"League: {L.get('name')} (created {str(L.get('created',''))[:10]})")
        print(f"Members: {len(scored) or len(pending)}"
              f"{' — standings live' if scored else ' — awaiting GW1'}")
        return

    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)

    gw = conn.execute("SELECT MAX(gw) FROM picks").fetchone()[0] or 0
    if a.sync or not a.report:
        gw = sync(conn, cfg, verbose=not a.quiet) or gw

    if a.report:
        if not gw:
            print("Nothing to report yet — no scored gameweeks.")
            return
        text = report(conn, cfg, gw)
        out = REPORTS / f"league-{datetime.now():%Y-%m-%d}.md"
        out.write_text(text)
        print(f"Wrote {out}")
        if not a.quiet:
            print("\n" + text)
    conn.close()


if __name__ == "__main__":
    main()
