#!/usr/bin/env python3
"""Minimal tests for core fpld functions. No framework — just assertions.

    python3 test_fpld.py
"""

import sys

# ---------------------------------------------------------------- norm()
from fpld_brief import norm

def test_norm():
    assert norm("Ødegaard") == norm("odegaard"), "ø → o"
    assert norm("Dúbravka") == norm("dubravka"), "ú → u"
    assert norm("João Pedro") == norm("joao pedro"), "ã → a"
    assert norm("Sørloth") == norm("sorloth"), "ø → o"
    assert norm("Gyökeres") == norm("gyokeres"), "ö → o"
    assert norm("Müller") == norm("muller"), "ü → u"
    assert norm("B.Fernandes") == norm("bfernandes"), "strips punctuation"
    assert norm("HAALAND") == norm("haaland"), "case insensitive"
    assert norm("  spaces  ") == "spaces", "trims whitespace"
    print("  norm: OK")


# ---------------------------------------------------------------- dial()
from fpld_brief import dial

def test_dial():
    # Leading (mid-season)
    mode, _ = dial(-10, 30, gw=15)
    assert mode == "SHIELD", f"leading should be SHIELD, got {mode}"

    # Level
    mode, _ = dial(0, 30, gw=15)
    assert mode == "SAFE", f"level should be SAFE, got {mode}"

    # Slightly behind
    mode, _ = dial(10, 30, gw=15)  # pressure = 0.33
    assert mode == "SAFE", f"0.33 pressure should be SAFE, got {mode}"

    # Moderate
    mode, _ = dial(30, 30, gw=15)  # pressure = 1.0
    assert mode == "BALANCED", f"1.0 pressure should be BALANCED, got {mode}"

    # Behind
    mode, _ = dial(60, 30, gw=15)  # pressure = 2.0
    assert mode == "AGGRESSIVE", f"2.0 pressure should be AGGRESSIVE, got {mode}"

    # Way behind
    mode, _ = dial(100, 20, gw=20)  # pressure = 5.0
    assert mode == "SWING", f"5.0 pressure should be SWING, got {mode}"

    # Season over
    mode, _ = dial(50, 0, gw=38)
    assert mode == "SEASON OVER", f"0 GWs left should be SEASON OVER, got {mode}"

    # Edge cases: exact thresholds
    mode, _ = dial(15, 30, gw=15)  # pressure = 0.5
    assert mode == "SAFE", f"0.5 pressure should be SAFE, got {mode}"

    mode, _ = dial(16, 30, gw=15)  # pressure = 0.533
    assert mode == "BALANCED", f"0.533 pressure should be BALANCED, got {mode}"

    mode, _ = dial(45, 30, gw=15)  # pressure = 1.5
    assert mode == "BALANCED", f"1.5 pressure should be BALANCED, got {mode}"

    mode, _ = dial(46, 30, gw=15)  # pressure = 1.533
    assert mode == "AGGRESSIVE", f"1.533 pressure should be AGGRESSIVE, got {mode}"

    mode, _ = dial(90, 30, gw=15)  # pressure = 3.0
    assert mode == "AGGRESSIVE", f"3.0 pressure should be AGGRESSIVE, got {mode}"

    mode, _ = dial(91, 30, gw=15)  # pressure = 3.033
    assert mode == "SWING", f"3.033 pressure should be SWING, got {mode}"

    # Playbook rule: before GW10, cap at BALANCED
    mode, _ = dial(60, 30, gw=5)  # would be AGGRESSIVE, but capped
    assert mode == "BALANCED", f"GW5 AGGRESSIVE should be capped to BALANCED, got {mode}"

    mode, _ = dial(100, 20, gw=3)  # would be SWING, but capped
    assert mode == "BALANCED", f"GW3 SWING should be capped to BALANCED, got {mode}"

    mode, _ = dial(30, 30, gw=5)  # BALANCED stays BALANCED (not capped)
    assert mode == "BALANCED", f"GW5 BALANCED should stay BALANCED, got {mode}"

    # Playbook rule: after GW30, shift one band more aggressive
    mode, _ = dial(10, 8, gw=31)  # pressure 1.25 = BALANCED, shifted to AGGRESSIVE
    assert mode == "AGGRESSIVE", f"GW31 BALANCED should shift to AGGRESSIVE, got {mode}"

    mode, _ = dial(0, 8, gw=35)  # pressure 0 = SAFE, shifted to BALANCED
    assert mode == "BALANCED", f"GW35 SAFE should shift to BALANCED, got {mode}"

    mode, _ = dial(100, 5, gw=34)  # pressure 20 = SWING, stays SWING (already max)
    assert mode == "SWING", f"GW34 SWING should stay SWING, got {mode}"

    print("  dial: OK")


# ---------------------------------------------------------------- score()
from fpld_brief import score, captain_score

def _make_player(**kw):
    base = {"id": 1, "name": "Test", "pos": "MID", "club": "TST",
            "price": 8.0, "form": 5.0, "ppg": 5.0, "owned": 20.0,
            "minutes": 900, "status": "a", "xgi90": 0.5, "defcon": 200,
            "fdr": 3.0, "blanks": 0, "run": [{"gw": 1, "opp": "OPP",
            "home": True, "fdr": 3}]}
    base.update(kw)
    return base

def test_score():
    p = _make_player()
    s = score(p, 5)
    assert s > 0, "healthy player should score > 0"

    # Injured player scores 0
    injured = _make_player(status="i")
    assert score(injured, 5) == 0, "injured player should score 0"

    # Low minutes scores 0
    low_mins = _make_player(minutes=30)
    assert score(low_mins, 5) == 0, "low minutes should score 0"

    # Better form = higher score
    high_form = _make_player(form=8.0)
    low_form = _make_player(form=2.0)
    assert score(high_form, 5) > score(low_form, 5), "higher form should score higher"

    # Easier fixtures = higher score
    easy = _make_player(fdr=1.5)
    hard = _make_player(fdr=4.5)
    assert score(easy, 5) > score(hard, 5), "easier fixtures should score higher"

    print("  score: OK")


def test_captain_score():
    p = _make_player()
    cs = captain_score(p)
    assert cs > 0, "healthy player should have captain score > 0"

    # No fixtures = 0
    no_fix = _make_player(run=[])
    assert captain_score(no_fix) == 0, "no fixtures should be 0"

    # FWD ceiling > DEF ceiling
    fwd = _make_player(pos="FWD")
    def_ = _make_player(pos="DEF")
    assert captain_score(fwd) > captain_score(def_), "FWD ceiling > DEF ceiling"

    print("  captain_score: OK")


# ---------------------------------------------------------------- run all

def main():
    print("Running fpld tests...\n")
    passed, failed = 0, 0
    for name, fn in [("norm", test_norm), ("dial", test_dial),
                     ("score", test_score), ("captain_score", test_captain_score)]:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  {name}: FAILED — {e}")
            failed += 1
        except Exception as e:
            print(f"  {name}: ERROR — {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
