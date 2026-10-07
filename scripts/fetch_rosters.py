#!/usr/bin/env python3
"""Fetch weekly rosters + draft picks for every season via the public fxea API (no login).

Usage: fetch_rosters.py [--current | --seasons ...]  (default: all). Other seasons are kept as stored.
Writes data/rosters.csv (season, period, team_id, player_id, status)
       data/draft.csv   (season, round, pick, team_id, player_id)
Powers the "Who Has Him" tracker.
"""
import csv, json, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import fxea, ROOT, target_seasons, read_rows


def fx(league, method, **q):
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    req = urllib.request.Request(
        f"https://www.fantrax.com/fxea/general/{method}?leagueId={league}&{qs}",
        headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    lg = json.load(open(ROOT / "leagues.json"))
    cfg = lg["leagues"]
    targets = target_seasons(lg, sys.argv[1:])
    rosters, draft = [], []
    for s, lid in cfg.items():
        if s not in targets:
            continue
        info = fxea(lid, "getLeagueInfo")
        nper = len(info["scoringPeriods"])
        for p in range(1, nper + 1):
            d = fx(lid, "getTeamRosters", period=p)
            for tid, t in d["rosters"].items():
                for it in t["rosterItems"]:
                    rosters.append([s, p, tid, it["id"], it["status"]])
        try:
            for pk in fx(lid, "getDraftResults")["draftPicks"]:
                if "playerId" not in pk:
                    continue  # pick not made yet
                draft.append([s, pk["round"], pk["pick"], pk["teamId"], pk["playerId"]])
        except Exception as e:
            print("  no draft", s, e, file=sys.stderr)
        print(s, nper, "periods", file=sys.stderr)
    for name, hdr, rows in (("rosters", ["season", "period", "team_id", "player_id", "status"], rosters),
                            ("draft", ["season", "round", "pick", "team_id", "player_id"], draft)):
        path = ROOT / "data" / f"{name}.csv"
        keep = [r for r in read_rows(path) if r[0] not in targets]  # other seasons kept as stored
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(hdr); w.writerows(sorted(keep + rows, key=lambda r: str(r[0])))
    print(len(rosters), "roster rows,", len(draft), "draft picks", file=sys.stderr)


if __name__ == "__main__":
    main()
