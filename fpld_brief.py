#!/usr/bin/env python3
"""
fpld_brief.py — a daily Fantasy Premier League briefing.

Reads the public FPL API, diffs against yesterday, and writes a dated
Markdown brief with PROPOSED moves. It never writes anything to FPL:
the API is read-only, so every suggestion needs you to apply it by hand.

Stdlib only. Python 3.9+.

    python3 fpld_brief.py --init          # create config.json
    python3 fpld_brief.py                 # write today's brief
    python3 fpld_brief.py --print         # also dump it to the terminal
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import re
import unicodedata
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean

API = "https://fantasy.premierleague.com/api"
HOME = Path(os.environ.get("FPLD_HOME", Path.home() / ".fpld"))
CONFIG = HOME / "config.json"
STATE = HOME / "state.json"
BRIEFS = HOME / "briefs"
UA = "Mozilla/5.0 fpld (personal use)"

DEFAULT_CONFIG = {
    "team_id": 0,
    "league_id": 0,
    "horizon": 5,
    "watchlist": [],
    "_comment": (
        "team_id: from your FPL 'Points' page URL /entry/<ID>/. "
        "league_id: from your mini-league URL /leagues/<ID>/standings/. "
        "horizon: how many gameweeks ahead to score fixtures. "
        "watchlist: player surnames you want tracked even if unowned."
    ),
}

POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
STATUS = {
    "a": None, "d": "Doubtful", "i": "Injured",
    "s": "Suspended", "u": "Unavailable", "n": "Not in squad",
}


# ---------------------------------------------------------------- fetching

def get(path, optional=False):
    url = f"{API}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if optional and e.code in (403, 404):
            return None
        raise SystemExit(f"FPL API returned {e.code} for {url}. "
                         f"{'Check your team_id/league_id.' if e.code == 404 else 'Try again shortly.'}")
    except Exception as e:
        if optional:
            return None
        raise SystemExit(f"Couldn't reach the FPL API ({e}). Check your connection.")


# Letters Unicode decomposition won't handle: these are distinct characters,
# not a base letter plus a diacritic, so NFKD drops them entirely.
TRANSLIT = str.maketrans({"ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "å": "a", "Å": "a",
                          "ß": "ss", "đ": "d", "Đ": "d", "ł": "l", "Ł": "l",
                          "ı": "i", "ŋ": "n", "þ": "th", "ð": "d"})


def norm(s):
    """Strip accents, punctuation and case so 'Dúbravka' matches 'Dubravka'
    and 'Ødegaard' matches 'Odegaard'."""
    s = str(s).translate(TRANSLIT)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------- model

def build(boot, fixtures, horizon):
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    events = boot.get("events", [])

    nxt = next((e for e in events if e.get("is_next")), None)
    cur = next((e for e in events if e.get("is_current")), None)
    upcoming = nxt["id"] if nxt else (cur["id"] + 1 if cur else 1)
    deadline = nxt.get("deadline_time") if nxt else None

    # Fixture difficulty per club over the horizon.
    window = range(upcoming, upcoming + horizon)
    runs = {tid: [] for tid in teams}
    for f in fixtures:
        ev = f.get("event")
        if ev not in window:
            continue
        h, a = f.get("team_h"), f.get("team_a")
        if h in runs:
            runs[h].append({"gw": ev, "opp": teams.get(a, "?"), "home": True, "fdr": f.get("team_h_difficulty", 3)})
        if a in runs:
            runs[a].append({"gw": ev, "opp": teams.get(h, "?"), "home": False, "fdr": f.get("team_a_difficulty", 3)})
    for tid in runs:
        runs[tid].sort(key=lambda x: x["gw"])

    # Detect double and blank gameweeks per team in the horizon window.
    doubles = {}  # {gw: [short_name, ...]}
    blanks_by_gw = {}  # {gw: [short_name, ...]}
    for gw in window:
        for tid, short in teams.items():
            count = sum(1 for x in runs[tid] if x["gw"] == gw)
            if count >= 2:
                doubles.setdefault(gw, []).append(short)
            elif count == 0:
                blanks_by_gw.setdefault(gw, []).append(short)

    players = {}
    for e in boot["elements"]:
        tid = e["team"]
        run = runs.get(tid, [])
        fdrs = [x["fdr"] for x in run]
        players[e["id"]] = {
            "id": e["id"],
            "name": e.get("web_name", "?"),
            "full": f"{e.get('first_name','')} {e.get('second_name','')}".strip(),
            "pos": POS.get(e.get("element_type"), "?"),
            "club": teams.get(tid, "?"),
            "team_id": tid,
            "price": num(e.get("now_cost")) / 10,
            "points": num(e.get("total_points")),
            "form": num(e.get("form")),
            "ppg": num(e.get("points_per_game")),
            "owned": num(e.get("selected_by_percent")),
            "minutes": num(e.get("minutes")),
            "status": e.get("status", "a"),
            "news": (e.get("news") or "").strip(),
            "chance": e.get("chance_of_playing_next_round"),
            "xgi90": num(e.get("expected_goal_involvements_per_90")),
            "defcon": num(e.get("defensive_contribution")),
            "net_transfers": num(e.get("transfers_in_event")) - num(e.get("transfers_out_event")),
            "run": run,
            "fdr": mean(fdrs) if fdrs else 3.0,
            "blanks": max(0, horizon - len(run)),
        }
    return {"teams": teams, "players": players, "gw": upcoming, "deadline": deadline,
            "finished": cur["id"] if cur else 0,
            "doubles": doubles, "blanks_by_gw": blanks_by_gw}


def squad_of(cfg, model):
    """Your 15. From the API if the season has started, else config fallback."""
    tid, gw = cfg["team_id"], model["gw"]
    for g in (gw - 1, gw - 2):
        if g < 1:
            break
        picks = get(f"entry/{tid}/event/{g}/picks/", optional=True)
        if picks and picks.get("picks"):
            ids = [p["element"] for p in picks["picks"]]
            return [model["players"][i] for i in ids if i in model["players"]], f"API (GW{g} picks)"

    names = cfg.get("squad_fallback") or []
    if names:
        out, missed = [], []
        by_web = {norm(p["name"]): p for p in model["players"].values()}
        by_full = {norm(p["full"]): p for p in model["players"].values()}
        for raw in names:
            k = norm(raw)
            m = by_web.get(k) or by_full.get(k)
            if not m:  # then try surname / substring
                hits = [p for p in model["players"].values()
                        if k and (k in norm(p["full"]) or norm(p["name"]) in k)]
                m = hits[0] if len(hits) == 1 else None
            (out.append(m) if m else missed.append(raw))
        if missed:
            print(f"⚠ Couldn't match {len(missed)} name(s): {', '.join(missed)}", file=sys.stderr)
        if out:
            return out, f"config.json fallback ({len(out)}/{len(names)} matched)"
    return [], "unknown"


def score(p, horizon):
    """Transparent heuristic for TRANSFERS. Value-weighted, so premiums score low
    by design — never use this to pick a captain."""
    if p["status"] != "a" or p["minutes"] < 60:
        return 0.0
    fixture = (5 - p["fdr"]) / 4                      # 0..1, easier is higher
    form = min(p["form"] / 8, 1.0)                    # 8.0 form treated as ceiling
    value = min(p["ppg"] / max(p["price"], 0.1) / 0.9, 1.0)
    threat = min(p["xgi90"] / 0.8, 1.0) if p["pos"] in ("MID", "FWD") else min(p["defcon"] / 250, 1.0)
    played = 1.0 - (p["blanks"] / max(horizon, 1))
    return round(100 * played * (0.32 * form + 0.28 * fixture + 0.22 * value + 0.18 * threat), 1)


CEILING = {"FWD": 1.0, "MID": 0.95, "DEF": 0.60, "GK": 0.35}


def captain_score(p):
    """Captaincy is about ceiling, not efficiency. Price is deliberately absent:
    you are doubling points, not buying them."""
    if p["status"] != "a" or not p["run"]:
        return 0.0
    first = p["run"][0]
    fixture = (5 - first["fdr"]) / 4
    home = 1.0 if first["home"] else 0.88
    threat = (min(p["xgi90"] / 0.9, 1.0) if p["pos"] in ("MID", "FWD")
              else min(p["defcon"] / 300, 1.0) * 0.5)
    form = min(p["form"] / 8, 1.0)
    return round(100 * CEILING.get(p["pos"], 0.5) * home *
                 (0.45 * threat + 0.35 * fixture + 0.20 * form), 1)


# ---------------------------------------------------------------- diffing

def diff(model, prev):
    old = prev.get("players", {}) if prev else {}
    price, flags, cleared = [], [], []
    for pid, p in model["players"].items():
        o = old.get(str(pid))
        if not o:
            continue
        if abs(p["price"] - o.get("price", p["price"])) > 0.001:
            price.append((p, p["price"] - o["price"]))
        if p["status"] != o.get("status", "a"):
            (cleared if p["status"] == "a" else flags).append(p)
    return {"price": price, "flags": flags, "cleared": cleared}


def dial(behind, left):
    if left <= 0:
        return "SEASON OVER", "No gameweeks remain."
    if behind < 0:
        return "SHIELD", "You lead. Mirror the chasers, match their captain, avoid unique picks."
    p = behind / left
    if p <= 0.5:
        return "SAFE", "Template core, template captain, no hits."
    if p <= 1.5:
        return "BALANCED", "One calculated differential. Template captain unless the gap is tiny."
    if p <= 3:
        return "AGGRESSIVE", "Two or three sub-10% picks. Off-template captain when close."
    return "SWING", "Contrarian captain, low ownership, chips on maximum-variance weeks."


# ---------------------------------------------------------------- output

def run_str(p, n=5):
    if not p["run"]:
        return "no fixtures in window"
    return " ".join(f"{x['opp'].upper() if x['home'] else x['opp'].lower()}({x['fdr']})" for x in p["run"][:n])


def brief(cfg, model, squad, source, d, standings):
    gw, H = model["gw"], cfg["horizon"]
    L = [f"# fpld — {datetime.now().strftime('%A %-d %B %Y')}", ""]

    if model["deadline"]:
        try:
            dl = datetime.fromisoformat(model["deadline"].replace("Z", "+00:00"))
            hrs = (dl - datetime.now(timezone.utc)).total_seconds() / 3600
            L += [f"**GW{gw} deadline** {dl.astimezone().strftime('%a %-d %b, %H:%M')} "
                  f"— {'PASSED' if hrs < 0 else f'{hrs:.0f}h away'}", ""]
        except Exception:
            pass

    # Risk dial
    if standings:
        me = next((r for r in standings if r["entry"] == cfg["team_id"]), None)
        top = standings[0] if standings else None
        if me and top:
            behind = top["total"] - me["total"]
            left = 38 - model["finished"]
            mode, gloss = dial(behind, left)
            L += ["## Where you stand", "",
                  f"- Mini-league: **{me['rank']} of {len(standings)}**, {behind} behind {top['entry_name']}",
                  f"- Gameweeks left: {left}",
                  f"- **Mode: {mode}** — {gloss}", ""]

    # Alerts — the reason this runs daily
    L += ["## Overnight changes", ""]
    owned = {p["id"] for p in squad}
    watch = [w.lower() for w in cfg.get("watchlist", [])]

    def mine(p):
        return p["id"] in owned or p["name"].lower() in watch

    hit = False
    for p in d["flags"]:
        if mine(p):
            hit = True
            ch = f" ({p['chance']}% chance)" if p["chance"] is not None else ""
            L.append(f"- 🔴 **{p['name']}** ({p['club']}) — {STATUS.get(p['status'], p['status'])}{ch}. "
                     f"{p['news'] or 'No detail given.'}")
    for p in d["cleared"]:
        if mine(p):
            hit = True
            L.append(f"- 🟢 **{p['name']}** ({p['club']}) is available again.")
    for p, delta in d["price"]:
        if mine(p):
            hit = True
            L.append(f"- {'📈' if delta > 0 else '📉'} **{p['name']}** {delta:+.1f} to £{p['price']:.1f}m")
    if not hit:
        L.append("- Nothing changed for your squad or watchlist.")
    L.append("")

    # Fixture alerts — doubles and blanks in the horizon window
    doubles = model.get("doubles", {})
    blanks_by_gw = model.get("blanks_by_gw", {})
    if doubles or blanks_by_gw:
        L += ["## Fixture alerts", ""]
        for g in sorted(set(doubles) | set(blanks_by_gw)):
            if g in doubles:
                names = ", ".join(sorted(doubles[g]))
                L.append(f"- GW{g}: **Double** — {names} play twice")
            if g in blanks_by_gw:
                names = ", ".join(sorted(blanks_by_gw[g]))
                L.append(f"- GW{g}: **Blank** — {names} have no fixture")
        L.append("")

    # Price pressure on your own players
    risky = sorted([p for p in squad if p["net_transfers"] < -60000], key=lambda x: x["net_transfers"])[:3]
    if risky:
        L += ["**Under selling pressure** (rough — FPL's real formula is private):", ""]
        L += [f"- {p['name']}: {p['net_transfers']:+,.0f} net transfers this gameweek" for p in risky]
        L.append("")

    # Price change alerts — flag players likely to rise/fall tonight
    RISE_THRESHOLD = 100000   # net transfers suggesting an imminent rise
    FALL_THRESHOLD = -100000  # net transfers suggesting an imminent fall
    risers = sorted([p for p in model["players"].values()
                     if mine(p) and p["net_transfers"] >= RISE_THRESHOLD],
                    key=lambda x: -x["net_transfers"])[:5]
    fallers = sorted([p for p in model["players"].values()
                      if mine(p) and p["net_transfers"] <= FALL_THRESHOLD],
                     key=lambda x: x["net_transfers"])[:5]
    if risers or fallers:
        L += ["## Price watch", "",
              "_Players on your squad or watchlist near a price change (net transfer proxy)._", ""]
        for p in risers:
            tag = "🟢 squad" if p["id"] in owned else "👀 watchlist"
            L.append(f"- 📈 **{p['name']}** ({p['club']}, £{p['price']:.1f}m) — "
                     f"{p['net_transfers']:+,.0f} net transfers, likely to **rise** ({tag})")
        for p in fallers:
            tag = "🟢 squad" if p["id"] in owned else "👀 watchlist"
            L.append(f"- 📉 **{p['name']}** ({p['club']}, £{p['price']:.1f}m) — "
                     f"{p['net_transfers']:+,.0f} net transfers, likely to **fall** ({tag})")
        L.append("")

    # Squad over the horizon
    L += [f"## Your squad, next {H} gameweeks", "",
          f"_Source: {source}. Uppercase = home, lowercase = away, (n) = difficulty._", "",
          "| Player | Pos | £ | Form | Next fixtures | Avg FDR |", "|---|---|---|---|---|---|"]
    # Build sets of clubs with doubles/blanks for squad annotation
    dgw_clubs = set()
    for clubs in model.get("doubles", {}).values():
        dgw_clubs.update(clubs)
    blank_clubs = set()
    for clubs in model.get("blanks_by_gw", {}).values():
        blank_clubs.update(clubs)

    for p in sorted(squad, key=lambda x: (["GK", "DEF", "MID", "FWD"].index(x["pos"]), -x["price"])):
        flag = " ⚠️" if p["status"] != "a" else ""
        fixtures = run_str(p, H)
        if p["club"] in dgw_clubs:
            fixtures += " (DGW)"
        if p["club"] in blank_clubs:
            fixtures += " ⚠️ BLANK"
        L.append(f"| {p['name']}{flag} | {p['pos']} | {p['price']:.1f} | {p['form']:.1f} | "
                 f"{fixtures} | {p['fdr']:.1f} |")
    L.append("")

    # Proposals
    L += ["## Proposed moves — nothing is applied", ""]
    preseason = squad and all(p["form"] == 0 for p in squad)
    if preseason:
        L += ["_No gameweek has been scored, so form is zero across the board and the "
              "transfer scoring has nothing real to work with. Proposals resume once "
              "GW1 is in — anything suggested now would be noise._", ""]
    weakest = [] if preseason else sorted(
        [p for p in squad if p["minutes"] > 0 or p["status"] != "a"],
        key=lambda x: (x["status"] == "a", score(x, H)))[:3]
    pool = sorted(model["players"].values(), key=lambda x: -score(x, H))

    if not weakest and not preseason:
        L.append("_No squad data yet — seed `squad_fallback` in config.json, or wait for GW1 to finish._")
    for w in weakest:
        budget = w["price"] + 0.3
        opts = [p for p in pool if p["pos"] == w["pos"] and p["id"] not in owned
                and p["price"] <= budget and p["club"] != w["club"]][:3]
        L.append(f"**Consider replacing {w['name']}** ({w['pos']}, £{w['price']:.1f}m, "
                 f"score {score(w, H)}, FDR {w['fdr']:.1f})")
        if w["status"] != "a":
            L.append(f"- Flagged: {w['news'] or STATUS.get(w['status'])}")
        for o in opts:
            L.append(f"- → **{o['name']}** ({o['club']}, £{o['price']:.1f}m, {o['owned']:.1f}% owned) "
                     f"score {score(o, H)}, form {o['form']:.1f}, fixtures {run_str(o, H)}")
        L.append("")

    # Captaincy
    L += [f"## Captain shortlist, GW{gw}", ""]
    caps = sorted([p for p in squad if p["status"] == "a"], key=lambda x: -captain_score(x))[:4]
    for c in caps:
        first = c["run"][0] if c["run"] else None
        where = f"{'vs' if first['home'] else 'at'} {first['opp']} (FDR {first['fdr']})" if first else "no fixture"
        L.append(f"- **{c['name']}** — {where}, ceiling score {captain_score(c)}, "
                 f"xGI/90 {c['xgi90']:.2f}, {c['owned']:.1f}% owned")
    L += ["", "---", "",
          "_Transfer scores weight value (form 32%, fixtures 28%, points per million 22%, "
          "threat 18%). Captaincy is ranked separately on ceiling — fixture, threat and "
          "position, with price excluded, because you're doubling points rather than buying them._"]
    return "\n".join(L)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Daily FPL brief.")
    ap.add_argument("--init", action="store_true", help="write a starter config.json")
    ap.add_argument("--print", dest="show", action="store_true", help="print the brief")
    ap.add_argument("--find", metavar="NAME", help="look up how FPL spells a player")
    ap.add_argument("--home", help="override the data directory")
    a = ap.parse_args()

    global HOME, CONFIG, STATE, BRIEFS
    if a.home:
        HOME = Path(a.home); CONFIG = HOME / "config.json"; STATE = HOME / "state.json"; BRIEFS = HOME / "briefs"
    HOME.mkdir(parents=True, exist_ok=True)
    BRIEFS.mkdir(exist_ok=True)

    if a.find:
        boot = get("bootstrap-static/")
        teams = {t["id"]: t["short_name"] for t in boot["teams"]}
        k = norm(a.find)
        hits = [e for e in boot["elements"]
                if k in norm(e.get("web_name", "")) or k in norm(
                    f"{e.get('first_name','')} {e.get('second_name','')}")]
        if not hits:
            print(f"Nothing matching '{a.find}'.")
        for e in sorted(hits, key=lambda x: -num(x.get("now_cost")))[:12]:
            print(f'  "{e["web_name"]}"  —  {e.get("first_name","")} {e.get("second_name","")} '
                  f'({teams.get(e["team"],"?")}, £{num(e.get("now_cost"))/10:.1f}m)')
        return

    if a.init or not CONFIG.exists():
        if not CONFIG.exists():
            CONFIG.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        print(f"Config at {CONFIG} — add your team_id and league_id, then run again.")
        return

    cfg = {**DEFAULT_CONFIG, **json.loads(CONFIG.read_text())}
    if not cfg.get("team_id"):
        raise SystemExit(f"Set team_id in {CONFIG} first.")

    boot = get("bootstrap-static/")
    fixtures = get("fixtures/")
    model = build(boot, fixtures, cfg["horizon"])
    squad, source = squad_of(cfg, model)

    standings = []
    if cfg.get("league_id"):
        lg = get(f"leagues-classic/{cfg['league_id']}/standings/", optional=True)
        if lg:
            standings = lg.get("standings", {}).get("results", [])

    prev = json.loads(STATE.read_text()) if STATE.exists() else None
    d = diff(model, prev)

    text = brief(cfg, model, squad, source, d, standings)
    out = BRIEFS / f"{datetime.now():%Y-%m-%d}.md"
    out.write_text(text)

    STATE.write_text(json.dumps({
        "date": datetime.now().isoformat(),
        "players": {str(k): {"price": v["price"], "status": v["status"]} for k, v in model["players"].items()},
    }))

    print(f"Wrote {out}")
    if a.show:
        print("\n" + text)


if __name__ == "__main__":
    main()
