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
PLAYERS = HOME / "players.json"
BRIEFS = HOME / "briefs"
FIXTURES = HOME / "fixtures.md"
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


# ---------------------------------------------------------------- player map

def save_player_map(boot):
    """Write a local name→id map from bootstrap data. Called on every run."""
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    entries = {}
    for e in boot["elements"]:
        pid = e["id"]
        web = e.get("web_name", "")
        full = f"{e.get('first_name', '')} {e.get('second_name', '')}".strip()
        entries[str(pid)] = {
            "web_name": web,
            "full_name": full,
            "club": teams.get(e["team"], "?"),
            "pos": POS.get(e.get("element_type"), "?"),
            "price": num(e.get("now_cost")) / 10,
        }
    prev_count = 0
    if PLAYERS.exists():
        try:
            prev_count = len(json.loads(PLAYERS.read_text()))
        except Exception:
            pass
    PLAYERS.write_text(json.dumps(entries, ensure_ascii=False, indent=1))
    new_count = len(entries)
    added = new_count - prev_count if prev_count else 0
    return added


def load_player_map():
    """Load the local name map. Returns None if it doesn't exist yet."""
    if not PLAYERS.exists():
        return None
    try:
        return json.loads(PLAYERS.read_text())
    except Exception:
        return None


def find_in_map(pmap, query):
    """Search the local player map by name. Returns list of matches."""
    k = norm(query)
    hits = []
    for pid, info in pmap.items():
        if k in norm(info["web_name"]) or k in norm(info["full_name"]):
            hits.append({**info, "id": int(pid)})
    return sorted(hits, key=lambda x: -x["price"])


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
            if m:
                out.append(m)
            else:
                # Suggest closest matches from the player map
                suggestions = ""
                pmap = load_player_map()
                if pmap:
                    words = norm(raw).split()
                    candidates = [info["web_name"] for info in pmap.values()
                                  if any(w in norm(info["web_name"]) or w in norm(info["full_name"])
                                         for w in words)][:3]
                    if candidates:
                        suggestions = f" Did you mean: {', '.join(candidates)}?"
                missed.append(f"{raw}{suggestions}")
        if missed:
            raise SystemExit(
                f"squad_fallback: couldn't match {len(missed)} name(s):\n"
                + "\n".join(f"  - {m}" for m in missed)
                + "\nUse --find <name> to check FPL's spelling, then fix config.json."
            )
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

def load_xpts():
    """Load xPts predictions if available.
    Returns (predictions_dict, mature_bool).  When the model is immature
    (trained mostly on historical averages, not real per-GW data),
    mature=False and the caller should fall back to the heuristic."""
    xpts_file = HOME / "xpts_predictions.json"
    if not xpts_file.exists():
        return None, False
    try:
        raw = json.loads(xpts_file.read_text())
        maturity = raw.pop("_maturity", None)
        mature = maturity.get("mature", False) if maturity else True  # old format = trust
        # Convert string keys to int
        return {int(k): v for k, v in raw.items()}, mature
    except Exception:
        return None, False


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


# ---------------------------------------------------------------- 5-GW plan generation

def generate_plans(squad, model, cfg, xpts_data, xpts_mature, mode):
    """Generate sequenced 5-GW transfer plans at three aggression levels.

    Returns a dict with keys "safe", "balanced", "aggressive", each containing:
      - moves: [{gw, out: {id,name,pos,club,price}, in: {id,name,pos,club,price,xpts,reason}}]
      - ft_sequence: [{gw, ft_avail, used, rolled, hits}]
      - summary: one-line description
    """
    H = cfg["horizon"]
    gw_start = model["gw"]
    blanks_by_gw = model.get("blanks_by_gw", {})
    doubles = model.get("doubles", {})
    owned = {p["id"] for p in squad}
    pool = [p for p in model["players"].values()
            if p["status"] == "a" and p["minutes"] >= 60 and p["id"] not in owned]

    using_xpts = xpts_data is not None and xpts_mature
    has_diff = using_xpts and any(
        "diff_xpts_horizon" in v for v in xpts_data.values() if isinstance(v, dict))

    def player_value(p):
        """Score a player for transfer targeting."""
        if using_xpts:
            pred = xpts_data.get(p["id"])
            if pred:
                if has_diff and mode in ("AGGRESSIVE", "SWING"):
                    return pred.get("diff_xpts_horizon", pred["xpts_horizon"])
                return pred["xpts_horizon"]
        return score(p, H)

    def player_urgency(p):
        """How urgently a squad player needs replacing. Higher = replace sooner."""
        if p["status"] != "a":
            return 100  # injured/suspended = immediate
        v = player_value(p)
        # Check if player has a blank in the window
        player_club = p["club"]
        blank_urgency = 0
        for gw_off in range(H):
            gw_num = gw_start + gw_off
            blanking = blanks_by_gw.get(gw_num, [])
            if player_club in blanking:
                blank_urgency = max(blank_urgency, 10 - gw_off)  # sooner blank = more urgent
        return blank_urgency + max(0, 5 - v)  # low value + upcoming blank = urgent

    def best_replacement(out_player, already_used):
        """Find the best available replacement."""
        budget = out_player["price"] + 0.5  # allow slight stretch
        candidates = [p for p in pool if p["pos"] == out_player["pos"]
                      and p["price"] <= budget and p["club"] != out_player["club"]
                      and p["id"] not in already_used]
        if not candidates:
            # relax budget constraint
            candidates = [p for p in pool if p["pos"] == out_player["pos"]
                          and p["club"] != out_player["club"]
                          and p["id"] not in already_used][:10]
        if not candidates:
            return None
        return max(candidates, key=lambda p: player_value(p))

    def reason_for_move(out_p, in_p):
        """Short reason string for the transfer."""
        parts = []
        if out_p["status"] != "a":
            parts.append(f"{out_p['name']} flagged ({out_p.get('news') or out_p['status']})")
        else:
            parts.append(f"upgrade on {out_p['name']}")
        out_club = out_p["club"]
        for gw_off in range(H):
            gw_num = gw_start + gw_off
            if out_club in blanks_by_gw.get(gw_num, []):
                parts.append(f"{out_club} blank GW{gw_num}")
                break
        in_club = in_p["club"]
        for gw_off in range(H):
            gw_num = gw_start + gw_off
            if in_club in doubles.get(gw_num, []):
                parts.append(f"{in_club} DGW{gw_num}")
                break
        return "; ".join(parts)

    # Rank squad by urgency (most urgent = replace first)
    ranked_weak = sorted(
        [p for p in squad if p["minutes"] > 0 or p["status"] != "a"],
        key=lambda p: -player_urgency(p))

    # Pre-season guard: no real data, don't generate transfer plans
    preseason = squad and all(p["form"] == 0 for p in squad)
    if preseason:
        empty = {"moves": [], "ft_sequence": [], "summary": "Pre-season — no data to plan from."}
        return {"safe": empty, "balanced": empty, "aggressive": empty}

    def build_plan(max_moves, allow_hits):
        """Build a sequenced plan with up to max_moves transfers over 5 GWs."""
        moves = []
        used_ids = set()
        ft = 1  # default; could be overridden from API
        ft_sequence = []

        # Decide which players to replace and when
        targets = []
        for p in ranked_weak[:max_moves]:
            repl = best_replacement(p, used_ids)
            if repl is None:
                continue
            used_ids.add(repl["id"])
            # Find optimal GW to make this move
            urgency = player_urgency(p)
            targets.append({"out": p, "in": repl, "urgency": urgency,
                            "reason": reason_for_move(p, repl)})

        # Sort targets by urgency (most urgent first)
        targets.sort(key=lambda t: -t["urgency"])

        # Sequence: assign moves to GWs respecting FT rollover
        gw_moves = {gw_start + i: [] for i in range(H)}
        ft_track = ft

        # First pass: assign urgent moves (injured, blanking soon) to earliest possible
        # Second pass: spread remaining moves to maximise free transfers
        urgent = [t for t in targets if t["urgency"] >= 10]
        normal = [t for t in targets if t["urgency"] < 10]

        # Assign urgent moves ASAP
        for t in urgent:
            # Find the earliest GW where we can fit this
            assigned = False
            for gw_off in range(H):
                gw_num = gw_start + gw_off
                if len(gw_moves[gw_num]) == 0 or allow_hits:
                    gw_moves[gw_num].append(t)
                    assigned = True
                    break
            if not assigned and gw_moves:
                # Force into GW1 as a hit
                gw_moves[gw_start].append(t)

        # Assign normal moves: wait for FTs to accumulate
        remaining = list(normal)
        for gw_off in range(H):
            if not remaining:
                break
            gw_num = gw_start + gw_off
            # Simulate FT at this point
            ft_at_gw = min(5, ft_track)
            urgent_this_gw = len(gw_moves[gw_num])
            free_slots = ft_at_gw - urgent_this_gw

            if free_slots > 0 and remaining:
                # Use a free slot if we have accumulated FTs
                # But prefer to wait if ft_track < 2 and move isn't urgent
                if ft_at_gw >= 2 or gw_off >= 2:
                    to_assign = remaining.pop(0)
                    gw_moves[gw_num].append(to_assign)

            # FT rollover: used this GW = urgent + normal assigned
            used_this_gw = len(gw_moves[gw_num])
            ft_track = min(5, max(0, ft_at_gw - used_this_gw) + 1)

        # If we still have remaining moves and hits are allowed, assign to best GW
        if allow_hits and remaining:
            for t in remaining:
                # Find GW with best fixture for the incoming player
                best_gw = gw_start
                gw_moves[best_gw].append(t)

        # Build output
        ft_track = ft
        for gw_off in range(H):
            gw_num = gw_start + gw_off
            ft_avail = min(5, ft_track)
            gw_m = gw_moves[gw_num]
            used = len(gw_m)
            hits = max(0, used - ft_avail)

            for t in gw_m:
                out_p, in_p = t["out"], t["in"]
                xpts_out = None
                xpts_in = None
                if xpts_data:
                    pred_out = xpts_data.get(out_p["id"])
                    pred_in = xpts_data.get(in_p["id"])
                    if pred_out:
                        xpts_out = pred_out.get("xpts_horizon", 0)
                    if pred_in:
                        xpts_in = pred_in.get("xpts_horizon", 0)

                moves.append({
                    "gw": gw_num,
                    "out": {"id": out_p["id"], "name": out_p["name"], "pos": out_p["pos"],
                            "club": out_p["club"], "price": out_p["price"],
                            "xpts": xpts_out, "status": out_p["status"]},
                    "in": {"id": in_p["id"], "name": in_p["name"], "pos": in_p["pos"],
                           "club": in_p["club"], "price": in_p["price"],
                           "xpts": xpts_in, "owned": in_p["owned"]},
                    "reason": t["reason"],
                    "is_hit": hits > 0 and gw_m.index(t) >= ft_avail,
                })

            ft_sequence.append({
                "gw": gw_num,
                "ft_avail": ft_avail,
                "used": used,
                "rolled": used == 0,
                "hits": hits,
                "blanks": blanks_by_gw.get(gw_num, []),
                "doubles": doubles.get(gw_num, []),
            })

            ft_track = min(5, max(0, ft_avail - min(used, ft_avail)) + 1)

        total_hits = sum(s["hits"] for s in ft_sequence)
        total_moves = len(moves)
        hit_str = f", {total_hits} hit(s) ({total_hits * -4}pts)" if total_hits else ""
        summary = f"{total_moves} transfer(s) over {H} GWs{hit_str}"

        return {"moves": moves, "ft_sequence": ft_sequence, "summary": summary}

    return {
        "safe": build_plan(max_moves=2, allow_hits=False),
        "balanced": build_plan(max_moves=3, allow_hits=False),
        "aggressive": build_plan(max_moves=5, allow_hits=True),
    }


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
    mode = None
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
    watch = {w.lower() for w in cfg.get("watchlist", [])}

    def mine(p):
        return p["id"] in owned or p["name"].lower() in watch

    def tag(p):
        if p["id"] in owned:
            return " *(squad)*"
        if p["name"].lower() in watch:
            return " *(watchlist)*"
        return ""

    # Your squad and watchlist flags — always show these
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

    # Biggest price movers league-wide — surface value you weren't looking for
    top_risers = sorted([p for p, delta in d["price"] if delta > 0 and not mine(p)],
                        key=lambda x: x["price"], reverse=True)[:5]
    top_fallers = sorted([p for p, delta in d["price"] if delta < 0 and not mine(p)],
                         key=lambda x: x["price"], reverse=True)[:5]
    if top_risers or top_fallers:
        L.append("")
        L.append("**Biggest movers league-wide** (outside your squad and watchlist):")
        for p in top_risers:
            L.append(f"- 📈 {p['name']} ({p['club']}, {p['pos']}, £{p['price']:.1f}m, {p['owned']:.1f}% owned)")
        for p in top_fallers:
            L.append(f"- 📉 {p['name']} ({p['club']}, {p['pos']}, £{p['price']:.1f}m, {p['owned']:.1f}% owned)")
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

    # Price change alerts — flag ANY player likely to rise/fall tonight
    RISE_THRESHOLD = 100000   # net transfers suggesting an imminent rise
    FALL_THRESHOLD = -100000  # net transfers suggesting an imminent fall
    risers = sorted([p for p in model["players"].values()
                     if p["net_transfers"] >= RISE_THRESHOLD],
                    key=lambda x: -x["net_transfers"])[:10]
    fallers = sorted([p for p in model["players"].values()
                      if p["net_transfers"] <= FALL_THRESHOLD],
                     key=lambda x: x["net_transfers"])[:10]
    if risers or fallers:
        L += ["## Price watch", "",
              "_Players likely to change price tonight (net transfer proxy). "
              "Squad and watchlist players highlighted._", ""]
        for p in risers:
            L.append(f"- 📈 **{p['name']}** ({p['club']}, {p['pos']}, £{p['price']:.1f}m, "
                     f"{p['owned']:.1f}% owned) — {p['net_transfers']:+,.0f} net transfers, "
                     f"likely to **rise**{tag(p)}")
        for p in fallers:
            L.append(f"- 📉 **{p['name']}** ({p['club']}, {p['pos']}, £{p['price']:.1f}m, "
                     f"{p['owned']:.1f}% owned) — {p['net_transfers']:+,.0f} net transfers, "
                     f"likely to **fall**{tag(p)}")
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
    xpts_data, xpts_mature = load_xpts()
    using_xpts = xpts_data is not None and xpts_mature
    xpts_available = xpts_data is not None  # immature model exists but not primary

    # EO-aware scoring: use differential xPts when mode demands it
    # AGGRESSIVE/SWING → favour low-EO (diff_xpts), SHIELD → favour high-EO (template)
    has_diff = using_xpts and any(
        "diff_xpts_horizon" in v for v in xpts_data.values() if isinstance(v, dict))
    use_diff = has_diff and mode in ("AGGRESSIVE", "SWING")
    use_shield = has_diff and mode == "SHIELD"

    if using_xpts:
        if use_diff:
            def xp(p):
                pred = xpts_data.get(p["id"])
                return pred.get("diff_xpts_horizon", pred["xpts_horizon"]) if pred else 0.0
            def xp_next(p):
                pred = xpts_data.get(p["id"])
                return pred.get("diff_xpts", pred["xpts"]) if pred else 0.0
        elif use_shield:
            # SHIELD: penalise low-EO picks — invert the differential
            # eo_boost = xpts * (1 + league_eo/200) — high-EO picks score higher
            def xp(p):
                pred = xpts_data.get(p["id"])
                if not pred: return 0.0
                eo = pred.get("league_eo", 0.0)
                return pred["xpts_horizon"] * (1.0 + eo / 200.0)
            def xp_next(p):
                pred = xpts_data.get(p["id"])
                if not pred: return 0.0
                eo = pred.get("league_eo", 0.0)
                return pred["xpts"] * (1.0 + eo / 200.0)
        else:
            def xp(p):
                pred = xpts_data.get(p["id"])
                return pred["xpts_horizon"] if pred else 0.0
            def xp_next(p):
                pred = xpts_data.get(p["id"])
                return pred["xpts"] if pred else 0.0
        scoring_label = "xPts"
    else:
        def xp(p):
            return score(p, H)
        def xp_next(p):
            return captain_score(p)
        scoring_label = "score"

    L += ["## Proposed moves — nothing is applied", ""]
    if using_xpts:
        if use_diff:
            L.append("_Ranked by differential xPts — low league EO, high ceiling._")
        elif use_shield:
            L.append("_Ranked by template xPts — high league EO, protect your lead._")
        else:
            L.append("_Ranked by xPts (ML model trained on historical data)._")
        L.append("")
    elif xpts_available:
        L.append("_Ranked by heuristic. xPts shown for reference (model immature)._")
        L.append("")
    preseason = squad and all(p["form"] == 0 for p in squad)
    if preseason:
        L += ["_No gameweek has been scored, so form is zero across the board and the "
              "transfer scoring has nothing real to work with. Proposals resume once "
              "GW1 is in — anything suggested now would be noise._", ""]
    weakest = [] if preseason else sorted(
        [p for p in squad if p["minutes"] > 0 or p["status"] != "a"],
        key=lambda x: (x["status"] == "a", xp(x)))[:3]
    pool = sorted(model["players"].values(), key=lambda x: -xp(x))

    if not weakest and not preseason:
        L.append("_No squad data yet — seed `squad_fallback` in config.json, or wait for GW1 to finish._")
    for w in weakest:
        budget = w["price"] + 0.3
        opts = [p for p in pool if p["pos"] == w["pos"] and p["id"] not in owned
                and p["price"] <= budget and p["club"] != w["club"]][:3]
        ref_xpts_w = ""
        if xpts_available and not using_xpts:
            pred = xpts_data.get(w["id"])
            if pred:
                ref_xpts_w = f", xPts {pred['xpts_horizon']:.1f}*"
        L.append(f"**Consider replacing {w['name']}** ({w['pos']}, £{w['price']:.1f}m, "
                 f"{scoring_label} {xp(w):.1f}{ref_xpts_w}, FDR {w['fdr']:.1f})")
        if w["status"] != "a":
            L.append(f"- Flagged: {w['news'] or STATUS.get(w['status'])}")
        for o in opts:
            ref_xpts_o = ""
            if xpts_available and not using_xpts:
                pred = xpts_data.get(o["id"])
                if pred:
                    ref_xpts_o = f", xPts {pred['xpts_horizon']:.1f}*"
            eo_str = ""
            if has_diff:
                pred = xpts_data.get(o["id"])
                if pred and "league_eo" in pred:
                    eo_str = f", league EO {pred['league_eo']:.0f}%"
            L.append(f"- → **{o['name']}** ({o['club']}, £{o['price']:.1f}m, {o['owned']:.1f}% owned{eo_str}) "
                     f"{scoring_label} {xp(o):.1f}{ref_xpts_o}, form {o['form']:.1f}, fixtures {run_str(o, H)}")
        L.append("")

    # Captaincy
    L += [f"## Captain shortlist, GW{gw}", ""]
    caps = sorted([p for p in squad if p["status"] == "a"], key=lambda x: -xp_next(x))[:4]
    for c in caps:
        first = c["run"][0] if c["run"] else None
        where = f"{'vs' if first['home'] else 'at'} {first['opp']} (FDR {first['fdr']})" if first else "no fixture"
        xpts_str = f"xPts {xp_next(c):.2f}" if using_xpts else f"ceiling {captain_score(c)}"
        eo_cap = ""
        if has_diff:
            pred = xpts_data.get(c["id"])
            if pred and "league_eo" in pred:
                eo_cap = f", league EO {pred['league_eo']:.0f}%"
        L.append(f"- **{c['name']}** — {where}, {xpts_str}, "
                 f"xGI/90 {c['xgi90']:.2f}, {c['owned']:.1f}% owned{eo_cap}")
    L += ["", "---", ""]
    if using_xpts:
        L.append("_Proposals and captaincy ranked by xPts — a per-position linear regression "
                 "trained on historical FPL data. Run `python3 fpld_xpts.py --train` to retrain._")
    elif xpts_available:
        L.append("_Proposals ranked by heuristic (form 32%, fixtures 28%, value 22%, threat 18%). "
                 "xPts model exists but is **immature** — trained mostly on historical season "
                 "averages, not real per-GW data. It will activate automatically once enough "
                 "gameweeks are scored. Retrain with `python3 fpld_xpts.py --pull --train`._")
    else:
        L.append("_Transfer scores weight form 32%, fixtures 28%, points per million 22%, "
                 "threat 18%. Captaincy ranked by ceiling. Run `python3 fpld_xpts.py --pull --train` "
                 "to switch to ML-based xPts._")
    return "\n".join(L)


# ---------------------------------------------------------------- post-GW review

def review(cfg, boot, fixtures):
    """Generate a post-GW review comparing what happened vs what was planned."""
    events = boot.get("events", [])
    cur = next((e for e in events if e.get("is_current")), None)
    if not cur or not cur.get("finished"):
        return None  # no scored GW yet

    gw = cur["id"]
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}

    # Load the previous brief.json to see what was planned
    brief_file = HOME / "brief.json"
    prev_brief = None
    if brief_file.exists():
        try:
            prev_brief = json.loads(brief_file.read_text())
        except Exception:
            pass

    # Fetch scored picks for this GW
    tid = cfg["team_id"]
    picks_data = get(f"entry/{tid}/event/{gw}/picks/", optional=True)
    if not picks_data:
        return None

    picks = picks_data.get("picks", [])
    entry_history = picks_data.get("entry_history", {})
    points = entry_history.get("points", 0)
    bench_pts = entry_history.get("points_on_bench", 0)
    transfers_cost = entry_history.get("event_transfers_cost", 0)
    transfers_made = entry_history.get("event_transfers", 0)

    # Map element IDs to player data from bootstrap
    elements = {e["id"]: e for e in boot["elements"]}

    # Build scored squad
    captain_id = next((p["element"] for p in picks if p["is_captain"]), None)
    vice_id = next((p["element"] for p in picks if p["is_vice_captain"]), None)
    starters = [p for p in picks if p["position"] <= 11]
    bench = [p for p in picks if p["position"] > 11]

    def player_gw_points(element_id):
        el = elements.get(element_id)
        if not el:
            return 0
        return num(el.get("event_points", 0))

    captain_pts = player_gw_points(captain_id) * 2 if captain_id else 0
    vice_pts = player_gw_points(vice_id) * 2 if vice_id else 0
    captain_el = elements.get(captain_id, {})
    vice_el = elements.get(vice_id, {})

    L = [f"## GW{gw} Review", ""]
    L.append(f"**{points} pts** (bench {bench_pts}, hits {transfers_cost})")
    L.append("")

    # Captain review
    L.append(f"**Captain:** {captain_el.get('web_name', '?')} — "
             f"{player_gw_points(captain_id)}pts (x2 = {captain_pts}pts)")
    if vice_id:
        L.append(f"**Vice:** {vice_el.get('web_name', '?')} — "
                 f"{player_gw_points(vice_id)}pts")

    # Best captain among squad
    squad_pts = [(p["element"], player_gw_points(p["element"])) for p in picks]
    best_cap = max(squad_pts, key=lambda x: x[1])
    best_el = elements.get(best_cap[0], {})
    if best_cap[0] != captain_id:
        L.append(f"**Best captain would have been:** {best_el.get('web_name', '?')} "
                 f"({best_cap[1]}pts, +{best_cap[1] * 2 - captain_pts}pts swing)")
    else:
        L.append("**Captain call: nailed it.**")
    L.append("")

    # Bench review
    if bench_pts > 0:
        L.append(f"**Bench leak:** {bench_pts}pts left on the bench")
        for p in bench:
            pts = player_gw_points(p["element"])
            if pts > 0:
                el = elements.get(p["element"], {})
                L.append(f"- {el.get('web_name', '?')}: {pts}pts (bench {p['position'] - 11})")
        L.append("")

    # Transfers review
    if transfers_made > 0:
        transfers_data = get(f"entry/{tid}/transfers/", optional=True) or []
        gw_transfers = [t for t in transfers_data if t.get("event") == gw]
        if gw_transfers:
            L.append(f"**Transfers:** {transfers_made} made"
                     + (f" ({transfers_cost}pt hit)" if transfers_cost else " (free)"))
            for t in gw_transfers:
                in_el = elements.get(t["element_in"], {})
                out_el = elements.get(t["element_out"], {})
                in_pts = player_gw_points(t["element_in"])
                out_pts = player_gw_points(t["element_out"])
                delta = in_pts - out_pts
                L.append(f"- {out_el.get('web_name', '?')} ({out_pts}pts) → "
                         f"{in_el.get('web_name', '?')} ({in_pts}pts) "
                         f"{'📈' if delta > 0 else '📉' if delta < 0 else '➡️'} {delta:+d}pts")
            L.append("")

    # Compare against planned captain from previous brief
    if prev_brief and prev_brief.get("gw") == gw:
        caps = prev_brief.get("captain_shortlist", [])
        if caps:
            rec = caps[0]  # top recommendation
            rec_id = rec.get("id")
            if rec_id and rec_id != captain_id:
                rec_pts = player_gw_points(rec_id)
                L.append(f"**Brief recommended:** {rec['name']} as captain "
                         f"({rec_pts}pts vs your {player_gw_points(captain_id)}pts)")
                L.append("")

    return "\n".join(L)


# ---------------------------------------------------------------- price alert

def price_alert(cfg, model):
    """Check price-change pressure for squad, watchlist, and global movers.
    Returns markdown alert text, or None if nothing to report."""
    # Thresholds: lower than the daily brief's to catch earlier movement
    ALERT_RISE = 80000
    ALERT_FALL = -80000
    # Global movers need a higher bar — only the biggest swings
    GLOBAL_RISE = 150000
    GLOBAL_FALL = -150000

    squad_data = None
    try:
        tid, gw = cfg["team_id"], model["gw"]
        for g in (gw - 1, gw - 2):
            if g < 1:
                continue
            data = get(f"entry/{tid}/event/{g}/picks/", optional=True)
            if data:
                squad_data = {p["element"] for p in data.get("picks", [])}
                break
    except Exception:
        pass

    watch = {norm(w) for w in cfg.get("watchlist", [])}
    squad_alerts = []
    global_alerts = []

    for p in model["players"].values():
        net = p["net_transfers"]
        is_squad = squad_data and p["id"] in squad_data
        is_watch = any(w in norm(p["name"]) for w in watch)

        direction = "rise" if net > 0 else "fall"
        emoji = "📈" if net > 0 else "📉"

        if is_squad or is_watch:
            if net >= ALERT_RISE or net <= ALERT_FALL:
                tag = "squad" if is_squad else "watchlist"
                squad_alerts.append((abs(net),
                    f"- {emoji} **{p['name']}** ({p['club']}, £{p['price']:.1f}m) — "
                    f"{net:+,.0f} net transfers, likely to **{direction}** *({tag})*"))
        else:
            if net >= GLOBAL_RISE or net <= GLOBAL_FALL:
                # Flag reason hint from player status
                hint = ""
                if p["status"] != "a":
                    hint = f" — {STATUS.get(p['status'], p['status'])}"
                    if p.get("news"):
                        hint = f" — {p['news']}"
                global_alerts.append((abs(net),
                    f"- {emoji} **{p['name']}** ({p['club']}, {p['pos']}, £{p['price']:.1f}m, "
                    f"{p['owned']:.1f}% owned) — {net:+,.0f} net transfers{hint}"))

    if not squad_alerts and not global_alerts:
        return None

    L = ["## Price Alert", ""]

    if squad_alerts:
        squad_alerts.sort(reverse=True)
        L.append("**Your squad and watchlist** — act before ~02:30 UTC if needed:")
        L.append("")
        L.extend(line for _, line in squad_alerts)
        L.append("")

    if global_alerts:
        global_alerts.sort(reverse=True)
        L.append("**Biggest global movers** — large swings suggest news (injury, "
                 "press conference, or a bandwagon forming):")
        L.append("")
        L.extend(line for _, line in global_alerts[:8])
        L.append("")

    return "\n".join(L)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Daily FPL brief.")
    ap.add_argument("--init", action="store_true", help="write a starter config.json")
    ap.add_argument("--print", dest="show", action="store_true", help="print the brief")
    ap.add_argument("--find", metavar="NAME", help="look up how FPL spells a player")
    ap.add_argument("--json", action="store_true", help="write structured brief.json for the planner")
    ap.add_argument("--fixtures", action="store_true", help="full-season fixture difficulty grid")
    ap.add_argument("--review", action="store_true", help="post-GW review: captain, bench, transfers")
    ap.add_argument("--price-alert", action="store_true", help="evening price-change alert")
    ap.add_argument("--home", help="override the data directory")
    a = ap.parse_args()

    global HOME, CONFIG, STATE, PLAYERS, BRIEFS, FIXTURES
    if a.home:
        HOME = Path(a.home); CONFIG = HOME / "config.json"; STATE = HOME / "state.json"
        PLAYERS = HOME / "players.json"; BRIEFS = HOME / "briefs"; FIXTURES = HOME / "fixtures.md"
    HOME.mkdir(parents=True, exist_ok=True)
    BRIEFS.mkdir(exist_ok=True)

    if a.find:
        # Try local map first, fall back to live API
        pmap = load_player_map()
        if pmap:
            hits = find_in_map(pmap, a.find)
            if not hits:
                print(f"Nothing matching '{a.find}' in local player map ({len(pmap)} players).")
            for h in hits[:12]:
                print(f'  "{h["web_name"]}"  —  {h["full_name"]} '
                      f'({h["club"]}, £{h["price"]:.1f}m)')
            if hits:
                print(f"\n  ({len(pmap)} players in local map. Run the brief to refresh.)")
        else:
            print("No local player map yet — fetching from FPL API...")
            boot = get("bootstrap-static/")
            save_player_map(boot)
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
            print(f"\n  Player map saved. Future --find will use it offline.")
        return

    if a.fixtures:
        boot = get("bootstrap-static/")
        fixtures = get("fixtures/")
        teams = {t["id"]: t["short_name"] for t in boot["teams"]}
        events = boot.get("events", [])
        nxt = next((e for e in events if e.get("is_next")), None)
        cur = next((e for e in events if e.get("is_current")), None)
        upcoming = nxt["id"] if nxt else (cur["id"] + 1 if cur else 1)

        # Build fixture map: team_id -> {gw: [fixture_strings]}
        team_fixtures = {tid: {gw: [] for gw in range(1, 39)} for tid in teams}
        team_fdrs = {tid: {gw: [] for gw in range(1, 39)} for tid in teams}
        for f in fixtures:
            ev = f.get("event")
            if ev is None or ev < 1 or ev > 38:
                continue
            h, a_team = f.get("team_h"), f.get("team_a")
            if h in teams:
                opp = teams.get(a_team, "?")
                fdr = f.get("team_h_difficulty", 3)
                team_fixtures[h][ev].append(f"{opp.upper()}({fdr})")
                team_fdrs[h][ev].append(fdr)
            if a_team in teams:
                opp = teams.get(h, "?")
                fdr = f.get("team_a_difficulty", 3)
                team_fixtures[a_team][ev].append(f"{opp.lower()}({fdr})")
                team_fdrs[a_team][ev].append(fdr)

        # Sort teams alphabetically by short_name
        sorted_teams = sorted(teams.items(), key=lambda x: x[1])

        # Build Markdown table
        header = "| Team | " + " | ".join(str(gw) for gw in range(1, 39)) + " |"
        sep = "|---|" + "|".join("---" for _ in range(1, 39)) + "|"
        rows = [header, sep]
        for tid, short in sorted_teams:
            cells = []
            for gw in range(1, 39):
                fx = team_fixtures[tid][gw]
                cells.append(", ".join(fx) if fx else "-")
            rows.append(f"| {short} | " + " | ".join(cells) + " |")

        # Best runs summary
        window = range(upcoming, min(upcoming + 10, 39))
        avg_fdrs = []
        for tid, short in sorted_teams:
            fdrs = []
            for gw in window:
                fdrs.extend(team_fdrs[tid][gw])
            avg = mean(fdrs) if fdrs else 3.0
            avg_fdrs.append((short, avg))
        best5 = sorted(avg_fdrs, key=lambda x: x[1])[:5]

        lines = ["# Fixture Difficulty Grid", ""]
        lines.extend(rows)
        lines += ["", f"## Best runs (next 10 GWs)", "",
                  f"_From GW{upcoming} to GW{min(upcoming + 9, 38)}, lowest average FDR:_", ""]
        for rank, (short, avg) in enumerate(best5, 1):
            lines.append(f"{rank}. **{short}** — avg FDR {avg:.2f}")

        text = "\n".join(lines)
        FIXTURES.write_text(text)
        print(text)
        print(f"\nSaved to {FIXTURES}")
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
    added = save_player_map(boot)
    if added > 0:
        print(f"Player map updated: {added} new player(s) added to FPL.")
    fixtures = get("fixtures/")
    model = build(boot, fixtures, cfg["horizon"])

    # Standalone price alert mode
    if a.price_alert:
        alert = price_alert(cfg, model)
        if alert:
            alert_file = HOME / "price-alert.md"
            alert_file.write_text(alert)
            print(alert)
            print(f"\nWrote {alert_file}")
        else:
            print("No squad or watchlist players near a price change tonight.")
        return

    # Post-GW review (can run standalone or alongside the brief)
    if a.review:
        rev = review(cfg, boot, fixtures)
        if rev:
            review_file = HOME / "review-latest.md"
            review_file.write_text(rev)
            print(rev)
            print(f"\nWrote {review_file}")
        else:
            print("No scored GW to review yet.")
        if not a.show and not a.json:
            return  # standalone review mode

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

    if a.json:
        xpts_data, xpts_mature = load_xpts()
        H = cfg["horizon"]
        gw = model["gw"]

        def player_json(p):
            entry = {"id": p["id"], "name": p["name"], "pos": p["pos"],
                     "club": p["club"], "price": p["price"], "form": p["form"],
                     "ppg": p["ppg"], "xgi90": p["xgi90"], "owned": p["owned"],
                     "status": p["status"], "fdr": p["fdr"],
                     "fixtures": [{"gw": f["gw"], "opp": f["opp"], "home": f["home"],
                                   "fdr": f["fdr"]} for f in p["run"][:H]],
                     "score": score(p, H), "captain_score": captain_score(p)}
            if xpts_data:
                pred = xpts_data.get(p["id"])
                if pred:
                    entry["xpts"] = pred.get("xpts", 0)
                    entry["xpts_horizon"] = pred.get("xpts_horizon", 0)
            return entry

        # Risk dial
        behind, left = 0, 38 - gw + 1
        me = next((s for s in standings if s.get("entry") == cfg["team_id"]), None)
        leader = standings[0] if standings else None
        if me and leader:
            behind = leader.get("total", 0) - me.get("total", 0)
        mode, gloss = dial(behind, left)

        # Captain shortlist
        caps = sorted([p for p in squad if p["status"] == "a"],
                      key=lambda x: captain_score(x), reverse=True)[:4]

        # Generate 5-GW transfer plans
        plans = generate_plans(squad, model, cfg, xpts_data, xpts_mature, mode)

        brief_json = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "gw": gw,
            "deadline": model.get("deadline", ""),
            "dial": {"mode": mode, "behind": behind, "left": left, "gloss": gloss},
            "xpts_mature": xpts_mature,
            "squad": [player_json(p) for p in squad],
            "captain_shortlist": [player_json(c) for c in caps],
            "plans": plans,
            "all_players": {str(p["id"]): {"name": p["name"], "pos": p["pos"],
                            "club": p["club"], "price": p["price"],
                            "score": score(p, H)}
                            for p in model["players"].values()
                            if p["status"] == "a" and p["minutes"] >= 60},
        }

        json_out = HOME / "brief.json"
        json_out.write_text(json.dumps(brief_json, indent=1))
        print(f"Wrote {json_out}")


if __name__ == "__main__":
    main()
