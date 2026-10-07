#!/usr/bin/env python3
"""Fetch each team's counted lineup (player-level weekly FPts) via getLiveScoringStats.

Usage: fetch_players.py [season ...]   (default: the current season in leagues.json)
Writes data/player_weeks.csv: season, period, team_id, player_id, fpts
Each team-week's counted players sum to that team's matchup score (checked below).
Older seasons need the login cookie (see fetch_history.py).
"""
import csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import call, ROOT


def main():
    lg = json.load(open(ROOT / "leagues.json"))
    seasons = sys.argv[1:] or [lg["current"]]
    cfg = lg["leagues"]
    mu = {}
    for m in csv.DictReader(open(ROOT / "data" / "matchups.csv")):
        for side in ("away", "home"):
            if m[side + "_pts"] and m["phase"] == "regular":
                mu[(m["season"], int(m["period"]), m[side + "_id"])] = float(m[side + "_pts"])
    path = ROOT / "data" / "player_weeks.csv"
    keep = [r for r in csv.DictReader(open(path))] if path.exists() else []
    keep = [r for r in keep if r["season"] not in seasons]
    rows, bad = [], 0
    for s in seasons:
        lid = cfg[s]
        d = call(lid, "getStandings", {"view": "REGULAR_SEASON"}, auth=False)
        periods = [p["object1"] for p in d["displayedLists"]["periods"]]
        for p in periods:
            ls = call(lid, "getLiveScoringStats", {"period": str(p)}, auth=False)
            for tid, v in ls["statsPerTeam"]["allTeamsStats"].items():
                g = v.get("ACTIVE", {})
                for pid, pts in (g.get("scorerIdsToKeep") or {}).items():
                    rows.append({"season": s, "period": p, "team_id": tid, "player_id": pid, "fpts": pts})
                tot = mu.get((s, p, tid))
                if tot is not None and abs(tot - g.get("totalFpts", -1)) > 0.01:
                    bad += 1
                    print(f"  MISMATCH {s} p{p} {tid}: matchup {tot} vs live {g.get('totalFpts')}", file=sys.stderr)
            print(s, p, file=sys.stderr)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, ["season", "period", "team_id", "player_id", "fpts"])
        w.writeheader()
        w.writerows(keep + rows)
    print(f"{len(rows)} player-weeks written, {bad} team-week mismatches", file=sys.stderr)


if __name__ == "__main__":
    main()
