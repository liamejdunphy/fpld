#!/usr/bin/env python3
"""
fpld_xpts.py — expected points model for FPL.

Pulls historical per-gameweek data from the FPL API, trains a per-position
linear regression (pure Python, stdlib only), and predicts expected points
for upcoming gameweeks.

    python3 fpld_xpts.py --pull          # one-off: fetch all historical data (~5 min)
    python3 fpld_xpts.py --train         # train the model on accumulated data
    python3 fpld_xpts.py --predict       # predict next GW for all players
    python3 fpld_xpts.py --predict --league  # add league-differential xPts

Designed to be called by fpld_brief.py and fpld_league.py, or standalone.
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
from statistics import mean

API = "https://fantasy.premierleague.com/api"
HOME = Path(os.environ.get("FPLD_HOME", Path.home() / ".fpld"))
DB = HOME / "xpts.db"
MODEL = HOME / "xpts_model.json"
UA = "Mozilla/5.0 fpld (personal use)"
PAUSE = 0.4

POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS player_history (
  element INTEGER, season TEXT, minutes INTEGER, points INTEGER,
  goals INTEGER, assists INTEGER, clean_sheets INTEGER, bonus INTEGER,
  starts INTEGER, games INTEGER,
  PRIMARY KEY (element, season));
CREATE TABLE IF NOT EXISTS player_gw_detail (
  element INTEGER, gw INTEGER, season TEXT,
  minutes INTEGER, points INTEGER,
  goals INTEGER, assists INTEGER, clean_sheets INTEGER, bonus INTEGER,
  saves INTEGER, goals_conceded INTEGER,
  influence REAL, creativity REAL, threat REAL, ict REAL,
  expected_goals REAL, expected_assists REAL, expected_goal_involvements REAL,
  expected_goals_conceded REAL,
  was_home INTEGER, opponent INTEGER, difficulty INTEGER,
  PRIMARY KEY (element, gw, season));
CREATE TABLE IF NOT EXISTS player_meta (
  element INTEGER PRIMARY KEY, name TEXT, pos TEXT, club TEXT,
  price REAL, form REAL, ppg REAL, minutes INTEGER, status TEXT,
  xgi90 REAL, selected REAL,
  last_pulled TEXT);
CREATE INDEX IF NOT EXISTS ix_pgd_season ON player_gw_detail(season);
CREATE INDEX IF NOT EXISTS ix_pgd_element ON player_gw_detail(element);
"""


# ---------------------------------------------------------------- fetch

def get(path, optional=False):
    url = f"{API}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(3):
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
            if attempt == 2:
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


# ---------------------------------------------------------------- data pull

def pull(conn, boot, full=False, verbose=True):
    """Fetch element-summary for each player. Full pull on first run,
    incremental (only players not pulled today) on subsequent runs."""
    elements = boot["elements"]
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    today = datetime.now().strftime("%Y-%m-%d")

    # Determine current season tag
    events = boot.get("events", [])
    first_event = events[0] if events else {}
    season_start = first_event.get("deadline_time", "")[:4] or str(datetime.now().year)
    season = f"{season_start}/{int(season_start) + 1}"

    # Update player metadata (preserve last_pulled date)
    for e in elements:
        conn.execute("""INSERT INTO player_meta
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(element) DO UPDATE SET
              name=excluded.name, pos=excluded.pos, club=excluded.club,
              price=excluded.price, form=excluded.form, ppg=excluded.ppg,
              minutes=excluded.minutes, status=excluded.status,
              xgi90=excluded.xgi90, selected=excluded.selected""",
            (e["id"], e.get("web_name", "?"), POS.get(e.get("element_type"), "?"),
             teams.get(e["team"], "?"), num(e.get("now_cost")) / 10,
             num(e.get("form")), num(e.get("points_per_game")),
             int(num(e.get("minutes"))), e.get("status", "a"),
             num(e.get("expected_goal_involvements_per_90")),
             num(e.get("selected_by_percent")), None))
    conn.commit()

    # Determine which players need fetching
    if full:
        todo = [e["id"] for e in elements]
    else:
        already = {r[0] for r in conn.execute(
            "SELECT element FROM player_meta WHERE last_pulled = ?", (today,))}
        todo = [e["id"] for e in elements if e["id"] not in already]

    if not todo:
        if verbose:
            print("All players already pulled today.")
        return

    if verbose:
        print(f"Fetching element-summary for {len(todo)} players "
              f"(~{len(todo) * PAUSE / 60:.0f} min)…")

    for i, eid in enumerate(todo, 1):
        d = get(f"element-summary/{eid}/", optional=True)
        time.sleep(PAUSE)
        if not d:
            continue

        # Past seasons
        for s in d.get("history_past", []):
            conn.execute("""INSERT OR REPLACE INTO player_history
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (eid, s.get("season_name", "?"),
                 int(num(s.get("minutes"))), int(num(s.get("total_points"))),
                 int(num(s.get("goals_scored"))), int(num(s.get("assists"))),
                 int(num(s.get("clean_sheets"))), int(num(s.get("bonus"))),
                 int(num(s.get("starts"))),
                 int(num(s.get("starts")) + num(s.get("sub_appearances", 0)))))

        # Current season per-GW
        for h in d.get("history", []):
            conn.execute("""INSERT OR REPLACE INTO player_gw_detail
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (eid, h.get("round", 0), season,
                 int(num(h.get("minutes"))), int(num(h.get("total_points"))),
                 int(num(h.get("goals_scored"))), int(num(h.get("assists"))),
                 int(num(h.get("clean_sheets"))), int(num(h.get("bonus"))),
                 int(num(h.get("saves"))), int(num(h.get("goals_conceded"))),
                 num(h.get("influence")), num(h.get("creativity")),
                 num(h.get("threat")), num(h.get("ict_index")),
                 num(h.get("expected_goals")), num(h.get("expected_assists")),
                 num(h.get("expected_goal_involvements")),
                 num(h.get("expected_goals_conceded")),
                 1 if h.get("was_home") else 0,
                 h.get("opponent_team", 0), h.get("difficulty", 3)))

        conn.execute("UPDATE player_meta SET last_pulled = ? WHERE element = ?",
                     (today, eid))

        if verbose and i % 50 == 0:
            print(f"  {i}/{len(todo)} ({100 * i / len(todo):.0f}%)")

        if i % 100 == 0:
            conn.commit()

    conn.commit()
    if verbose:
        total = conn.execute("SELECT COUNT(*) FROM player_gw_detail").fetchone()[0]
        seasons = conn.execute("SELECT COUNT(DISTINCT season) FROM player_gw_detail").fetchone()[0]
        print(f"Done. {total} player-gameweek records across {seasons} season(s).")


# ---------------------------------------------------------------- linear algebra (pure Python)

def transpose(M):
    return list(map(list, zip(*M)))


def mat_mul(A, B):
    Bt = transpose(B)
    return [[sum(a * b for a, b in zip(row, col)) for col in Bt] for row in A]


def mat_vec(M, v):
    return [sum(m * x for m, x in zip(row, v)) for row in M]


def identity(n):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def invert(M):
    """Gauss-Jordan inversion of a square matrix."""
    n = len(M)
    A = [row[:] for row in M]
    I = identity(n)
    for col in range(n):
        # Partial pivot
        max_row = max(range(col, n), key=lambda r: abs(A[r][col]))
        A[col], A[max_row] = A[max_row], A[col]
        I[col], I[max_row] = I[max_row], I[col]
        diag = A[col][col]
        if abs(diag) < 1e-12:
            # Singular — add regularisation
            A[col][col] = 1e-6
            diag = 1e-6
        for j in range(n):
            A[col][j] /= diag
            I[col][j] /= diag
        for row in range(n):
            if row == col:
                continue
            factor = A[row][col]
            for j in range(n):
                A[row][j] -= factor * A[col][j]
                I[row][j] -= factor * I[col][j]
    return I


def ols(X, y, ridge=0.01):
    """Ordinary least squares with ridge regularisation.
    X: list of feature vectors, y: list of targets.
    Returns weight vector w such that y ≈ X @ w."""
    Xt = transpose(X)
    XtX = mat_mul(Xt, X)
    # Ridge: add lambda * I to diagonal
    for i in range(len(XtX)):
        XtX[i][i] += ridge
    XtX_inv = invert(XtX)
    Xty = mat_vec(Xt, y)
    return mat_vec(XtX_inv, Xty)


# ---------------------------------------------------------------- features

FEATURE_NAMES = [
    "bias",           # intercept
    "form",           # recent PPG (FPL's form field)
    "fdr",            # fixture difficulty (1-5, inverted so higher=easier)
    "home",           # 1 if home, 0 if away
    "xgi90",          # expected goal involvements per 90
    "minutes_pct",    # minutes played / 90 (nailed-on indicator)
    "ppg",            # season points per game
    "price",          # current price (proxy for quality)
    "selected_pct",   # global ownership
]


def extract_features_gw(row):
    """Extract feature vector from a player_gw_detail row + meta.
    Returns (features, target) or None if player didn't play."""
    minutes = row["minutes"]
    if minutes == 0:
        return None
    features = [
        1.0,                                         # bias
        min(row.get("form", 0) / 8.0, 1.0),         # form (normalised)
        (5.0 - row.get("difficulty", 3)) / 4.0,     # FDR (inverted, 0-1)
        float(row.get("was_home", 0)),               # home advantage
        min(row.get("xgi90", 0) / 0.8, 1.5),        # xGI per 90
        min(minutes / 90.0, 1.0),                    # minutes fraction
        min(row.get("ppg", 0) / 8.0, 1.0),          # PPG normalised
        row.get("price", 5.0) / 15.0,               # price normalised
        min(row.get("selected", 0) / 50.0, 1.0),    # ownership normalised
    ]
    target = row["points"]
    return features, target


def build_training_data(conn, pos):
    """Build training data for a single position from all available history.
    Uses per-GW detail when available, plus per-season averages from
    player_history to bootstrap before any current-season GWs exist."""
    X, y = [], []

    # 1. Per-gameweek detail (current season, once GWs are scored)
    rows = conn.execute("""
        SELECT d.element, d.gw, d.season, d.minutes, d.points,
               d.difficulty, d.was_home,
               d.expected_goal_involvements / NULLIF(d.minutes, 0) * 90.0 AS xgi90,
               m.form, m.ppg, m.price, m.selected
        FROM player_gw_detail d
        JOIN player_meta m ON d.element = m.element
        WHERE m.pos = ? AND d.minutes > 0
        ORDER BY d.season, d.gw""", (pos,)).fetchall()

    for r in rows:
        row = {
            "minutes": r[3], "points": r[4], "difficulty": r[5],
            "was_home": r[6], "xgi90": r[7] or 0.0,
            "form": r[8] or 0.0, "ppg": r[9] or 0.0,
            "price": r[10] or 5.0, "selected": r[11] or 0.0,
        }
        result = extract_features_gw(row)
        if result:
            X.append(result[0])
            y.append(result[1])

    n_real = len(X)  # samples from actual per-GW data

    # 2. Historical season averages — convert to per-game pseudo-observations.
    #    Each season becomes one training sample using per-game averages.
    #    Features we can't know (FDR, home/away) get neutral defaults.
    hist = conn.execute("""
        SELECT h.element, h.season, h.minutes, h.points, h.goals, h.assists,
               h.clean_sheets, h.bonus, h.starts, h.games, m.price, m.pos
        FROM player_history h
        JOIN player_meta m ON h.element = m.element
        WHERE m.pos = ? AND h.games > 0 AND h.minutes > 90
        ORDER BY h.season""", (pos,)).fetchall()

    for r in hist:
        games = max(r[9], 1)
        minutes = r[2]
        points = r[3]
        goals = r[4]
        assists = r[5]
        ppg = points / games
        mins_per_game = minutes / games
        # Estimate xGI/90 from actual goals+assists (imperfect but usable)
        gi_per_90 = (goals + assists) / max(minutes, 1) * 90.0
        price = r[10] or 5.0

        row = {
            "minutes": mins_per_game,
            "points": ppg,              # target: average points per game
            "difficulty": 3,            # neutral (we don't know fixture difficulty)
            "was_home": 0.5,            # half home, half away on average
            "xgi90": gi_per_90,
            "form": min(ppg / 8.0, 1.0) * 8.0,   # proxy form from PPG
            "ppg": ppg,
            "price": price,
            "selected": 0.0,            # unknown for past seasons
        }
        result = extract_features_gw(row)
        if result:
            X.append(result[0])
            y.append(result[1])

    n_synthetic = len(X) - n_real
    return X, y, n_real, n_synthetic


# ---------------------------------------------------------------- train

def train(conn, verbose=True):
    """Train per-position models and save weights."""
    models = {}
    total_real, total_synthetic = 0, 0
    for pos in ["GK", "DEF", "MID", "FWD"]:
        X, y, n_real, n_synthetic = build_training_data(conn, pos)
        total_real += n_real
        total_synthetic += n_synthetic
        if len(X) < 20:
            if verbose:
                print(f"  {pos}: only {len(X)} samples, skipping (need 20+)")
            continue

        w = ols(X, y, ridge=0.1)

        # Compute R² on training data
        y_pred = [sum(xi * wi for xi, wi in zip(x, w)) for x in X]
        ss_res = sum((yi - yp) ** 2 for yi, yp in zip(y, y_pred))
        y_mean = mean(y)
        ss_tot = sum((yi - y_mean) ** 2 for yi in y)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        mae = mean(abs(yi - yp) for yi, yp in zip(y, y_pred))

        models[pos] = {
            "weights": w,
            "feature_names": FEATURE_NAMES,
            "n_samples": len(X),
            "n_real": n_real,
            "n_synthetic": n_synthetic,
            "r2": round(r2, 4),
            "mae": round(mae, 2),
        }

        if verbose:
            src = f"{n_real} real + {n_synthetic} synthetic"
            print(f"  {pos}: {len(X)} samples ({src}), R²={r2:.3f}, MAE={mae:.2f}")
            for name, weight in zip(FEATURE_NAMES, w):
                print(f"    {name:15s} {weight:+.3f}")

    # Maturity gate: ratio of real per-GW samples to total.
    # Below 0.3 (or <100 real samples), the model is trained mostly on
    # historical averages and will overfit (form ≈ PPG tautology).
    maturity = total_real / max(total_real + total_synthetic, 1)
    mature = total_real >= 100 and maturity >= 0.3

    output = {
        "maturity": {
            "real_samples": total_real,
            "synthetic_samples": total_synthetic,
            "ratio": round(maturity, 3),
            "mature": mature,
        },
        "models": models,
    }
    MODEL.write_text(json.dumps(output, indent=2))

    if verbose:
        status = "MATURE" if mature else "IMMATURE (heuristic preferred)"
        print(f"\n  Maturity: {total_real} real / {total_real + total_synthetic} total "
              f"= {maturity:.0%} — {status}")
        print(f"Model saved to {MODEL}")
    return models


# ---------------------------------------------------------------- predict

def load_model():
    """Load saved model. Returns (models_dict, maturity_dict) or (None, None).
    Handles both old format (flat dict of positions) and new format (with maturity)."""
    if not MODEL.exists():
        return None, None
    try:
        data = json.loads(MODEL.read_text())
        if "maturity" in data:
            return data["models"], data["maturity"]
        # Old format: flat dict of positions
        return data, {"real_samples": 0, "synthetic_samples": 0, "ratio": 0, "mature": False}
    except Exception:
        return None, None


def predict_player(player, fixture, model_weights):
    """Predict xPts for a single player in a single fixture.
    player: dict with form, ppg, price, xgi90, minutes, selected/owned
    fixture: dict with fdr, home (bool)
    model_weights: weight vector for this position
    """
    features = [
        1.0,
        min(num(player.get("form", 0)) / 8.0, 1.0),
        (5.0 - num(fixture.get("fdr", 3))) / 4.0,
        1.0 if fixture.get("home") else 0.0,
        min(num(player.get("xgi90", 0)) / 0.8, 1.5),
        min(num(player.get("minutes", 0)) / 90.0, 1.0),
        min(num(player.get("ppg", 0)) / 8.0, 1.0),
        num(player.get("price", 5.0)) / 15.0,
        min(num(player.get("owned", player.get("selected", 0))) / 50.0, 1.0),
    ]
    return max(0.0, sum(f * w for f, w in zip(features, model_weights)))


def predict_all(conn, boot, fixtures_data):  # noqa: ARG001
    """Predict xPts for all players for the next gameweek.
    Returns {element_id: {"xpts": float, "xpts_horizon": float, ...}}"""
    models, maturity = load_model()
    if not models:
        return None

    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    events = boot.get("events", [])
    nxt = next((e for e in events if e.get("is_next")), None)
    cur = next((e for e in events if e.get("is_current")), None)
    upcoming = nxt["id"] if nxt else (cur["id"] + 1 if cur else 1)

    # Build fixture map: team_id → list of {gw, opp, home, fdr}
    fixture_map = {}
    for f in fixtures_data:
        ev = f.get("event")
        if ev is None or ev < upcoming:
            continue
        h, a = f.get("team_h"), f.get("team_a")
        fixture_map.setdefault(h, []).append({
            "gw": ev, "opp": a, "home": True,
            "fdr": f.get("team_h_difficulty", 3)})
        fixture_map.setdefault(a, []).append({
            "gw": ev, "opp": h, "home": False,
            "fdr": f.get("team_a_difficulty", 3)})
    for tid in fixture_map:
        fixture_map[tid].sort(key=lambda x: x["gw"])

    predictions = {}
    for e in boot["elements"]:
        pos = POS.get(e.get("element_type"), "?")
        if pos not in models:
            continue
        w = models[pos]["weights"]

        player = {
            "form": num(e.get("form")),
            "ppg": num(e.get("points_per_game")),
            "price": num(e.get("now_cost")) / 10,
            "xgi90": num(e.get("expected_goal_involvements_per_90")),
            "minutes": num(e.get("minutes")),
            "owned": num(e.get("selected_by_percent")),
        }

        tid = e["team"]
        player_fixtures = fixture_map.get(tid, [])

        # Next GW prediction
        next_fix = [f for f in player_fixtures if f["gw"] == upcoming]
        if not next_fix:
            xpts_next = 0.0
        else:
            xpts_next = sum(predict_player(player, f, w) for f in next_fix)

        # Horizon prediction (next 5 GWs)
        horizon_fixes = [f for f in player_fixtures if f["gw"] < upcoming + 5]
        xpts_horizon = sum(predict_player(player, f, w) for f in horizon_fixes)

        # Penalise flagged/low-minutes players
        if e.get("status", "a") != "a" or num(e.get("minutes")) < 60:
            xpts_next *= 0.1
            xpts_horizon *= 0.1

        predictions[e["id"]] = {
            "name": e.get("web_name", "?"),
            "pos": pos,
            "club": teams.get(tid, "?"),
            "price": num(e.get("now_cost")) / 10,
            "xpts": round(xpts_next, 2),
            "xpts_horizon": round(xpts_horizon, 2),
            "owned": num(e.get("selected_by_percent")),
        }

    # Attach maturity info so consumers know whether to trust predictions
    predictions["_maturity"] = maturity

    return predictions


def differential_xpts(predictions, league_eo):
    """Adjust xPts for league context. A player with high xPts but high
    league EO gains you nothing — everyone benefits equally. A player with
    high xPts and low league EO is where you gain ground.

    diff_xpts = xpts * (1 - league_eo/200)

    At 0% EO: full value. At 100% EO: half value (they score, but so does
    everyone). At 200% EO (everyone captains): zero differential value."""
    for pid, pred in predictions.items():
        if pid == "_maturity":
            continue
        eo = league_eo.get(pid, {}).get("eo", 0.0)
        pred["league_eo"] = round(eo, 1)
        pred["diff_xpts"] = round(pred["xpts"] * (1.0 - eo / 200.0), 2)
        pred["diff_xpts_horizon"] = round(pred["xpts_horizon"] * (1.0 - eo / 200.0), 2)
    return predictions


# ---------------------------------------------------------------- output

def print_predictions(predictions, squad_ids=None, top_n=15):
    """Print a ranked table of predicted points."""
    items = sorted((v for k, v in predictions.items() if k != "_maturity"),
                    key=lambda x: -x["xpts"])

    print(f"\n{'Player':<20} {'Pos':<4} {'Club':<4} {'£':>5} {'xPts':>6} "
          f"{'5GW':>6} {'Own%':>6}" +
          (" {:>6} {:>6}".format("LEO%", "dxPts") if "diff_xpts" in items[0] else ""))
    print("-" * (75 if "diff_xpts" in items[0] else 57))

    shown = 0
    for p in items:
        if squad_ids and p.get("id") not in squad_ids and shown >= top_n:
            continue
        marker = " *" if squad_ids and p.get("id") in squad_ids else ""
        line = (f"{p['name']:<20} {p['pos']:<4} {p['club']:<4} "
                f"{p['price']:5.1f} {p['xpts']:6.2f} {p['xpts_horizon']:6.2f} "
                f"{p['owned']:6.1f}")
        if "diff_xpts" in p:
            line += f" {p.get('league_eo', 0):6.1f} {p['diff_xpts']:6.2f}"
        print(line + marker)
        shown += 1
        if shown >= top_n:
            break


def save_predictions(predictions):
    """Save predictions to JSON for use by other scripts."""
    out = HOME / "xpts_predictions.json"
    out.write_text(json.dumps(predictions, indent=1))
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="FPL expected points model.")
    ap.add_argument("--pull", action="store_true",
                    help="fetch historical data from FPL API")
    ap.add_argument("--full", action="store_true",
                    help="force full re-pull of all players")
    ap.add_argument("--train", action="store_true",
                    help="train the model on accumulated data")
    ap.add_argument("--predict", action="store_true",
                    help="predict xPts for all players")
    ap.add_argument("--league", action="store_true",
                    help="include league-differential xPts")
    ap.add_argument("--top", type=int, default=20,
                    help="number of players to show (default 20)")
    ap.add_argument("--home", help="override data directory")
    a = ap.parse_args()

    global HOME, DB, MODEL
    if a.home:
        HOME = Path(a.home)
        DB = HOME / "xpts.db"
        MODEL = HOME / "xpts_model.json"
    HOME.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)

    boot = get("bootstrap-static/")

    if a.pull or a.full:
        pull(conn, boot, full=a.full)

    if a.train:
        print("Training per-position models…")
        train(conn)

    if a.predict:
        fixtures_data = get("fixtures/")
        predictions = predict_all(conn, boot, fixtures_data)
        if not predictions:
            raise SystemExit("No model found. Run --pull --train first.")

        if a.league:
            # Load league EO from league.db if available
            league_db = HOME / "league.db"
            if league_db.exists():
                lconn = sqlite3.connect(league_db)
                max_gw = lconn.execute(
                    "SELECT MAX(gw) FROM picks").fetchone()[0]
                if max_gw:
                    n = lconn.execute(
                        "SELECT COUNT(DISTINCT entry_id) FROM picks WHERE gw=?",
                        (max_gw,)).fetchone()[0]
                    rows = lconn.execute("""
                        SELECT element,
                               SUM(CASE WHEN multiplier > 0 THEN 1 ELSE 0 END) AS starters,
                               SUM(CASE WHEN multiplier > 1 THEN multiplier - 1 ELSE 0 END) AS extra
                        FROM picks WHERE gw=? GROUP BY element""", (max_gw,)).fetchall()
                    league_eo = {r[0]: {"eo": 100.0 * (r[1] + r[2]) / n}
                                 for r in rows} if n else {}
                    predictions = differential_xpts(predictions, league_eo)
                    print(f"League-differential xPts computed ({n} managers, GW{max_gw})")
                lconn.close()
            else:
                print("No league.db found — run fpld_league.py --sync first for league-adjusted xPts.")

        print_predictions(predictions, top_n=a.top)
        out = save_predictions(predictions)
        print(f"\nPredictions saved to {out}")

    if not (a.pull or a.full or a.train or a.predict):
        # Default: pull + train + predict
        pull(conn, boot)
        print("\nTraining per-position models…")
        train(conn)
        fixtures_data = get("fixtures/")
        predictions = predict_all(conn, boot, fixtures_data)
        if predictions:
            print_predictions(predictions, top_n=a.top)
            save_predictions(predictions)

    conn.close()


if __name__ == "__main__":
    main()
