#!/usr/bin/env python3
"""One-time pull of full-season player stats for past seasons (public API, no login).

Usage: pull_past_stats.py [season ...]   (default: the two seasons before the current one)
Writes data/player_stats_<season>.json for each season, same shape as player_stats.json plus "name":
  id -> {name, rk, g, fpts, fpg, tm, pos, pts, reb, ast, st, blk, to (per game), tot{...totals, dd, td}, avg{...per game}}
Not part of the refresh workflow: finished seasons do not change.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import ROOT
from fantrax_stats import fetch_all


def main():
    lg = json.load(open(ROOT / "leagues.json"))
    cfg = sorted(lg["leagues"])
    seasons = sys.argv[1:] or cfg[cfg.index(lg["current"]) - 2:cfg.index(lg["current"])]
    for season in seasons:
        out = {"_season": season}
        for pid, s in fetch_all(lg["leagues"][season], {"timeframeTypeCode": "YEAR_TO_DATE"}).items():
            g, t = s["g"], s["tot"]
            if not g:
                continue
            pg = lambda k: round(t[k] / g, 1) if t.get(k) is not None else None
            out[pid] = {"name": s["name"], "rk": s["rk"], "g": g, "fpts": s["fpts"], "fpg": s["fpg"], "tm": s["tm"], "pos": s["pos"],
                        "pts": pg("pts"), "reb": pg("reb"), "ast": pg("ast"), "st": pg("st"), "blk": pg("blk"), "to": pg("to"),
                        "tot": t, "avg": s["avg"]}
        path = ROOT / "data" / f"player_stats_{season}.json"
        json.dump(out, open(path, "w"), separators=(",", ":"))
        bad = sum(1 for k, v in out.items() if k != "_season" and abs(v["tot"]["pts"] + 1.25 * v["tot"]["reb"] + 1.5 * v["tot"]["ast"]
                  + 2 * v["tot"]["st"] + 2 * v["tot"]["blk"] - v["tot"]["to"] - v["fpts"]) > 0.05)
        print(f"{season}: {len(out) - 1} players, {bad} FPts mismatches, {path.stat().st_size // 1024} KB", file=sys.stderr)


if __name__ == "__main__":
    main()
