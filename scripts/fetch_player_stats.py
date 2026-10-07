#!/usr/bin/env python3
"""Fetch per-game stats for the live season once it has scores, otherwise the last finished season (public, no login).
Writes data/player_stats.json: id -> {rk, g, fpts, fpg, pts, reb, ast, st, blk, to, tm, pos}
plus a "_season" key with the season label.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import call, ROOT, read_rows


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def main():
    lg = json.load(open(ROOT / "leagues.json"))
    cfg = lg["leagues"]
    scored = any(r[0] == lg["current"] and r[5] not in ("", "0.0") for r in read_rows(ROOT / "data" / "matchups.csv"))
    season = lg["current"] if scored else sorted(cfg)[sorted(cfg).index(lg["current"]) - 1]  # live season once it has scores
    lid, page, out = cfg[season], 1, {"_season": season}
    while True:
        d = call(lid, "getPlayerStats", {"statusOrTeamFilter": "ALL", "maxResultsPerPage": "500",
                 "pageNumber": str(page), "timeframeTypeCode": "YEAR_TO_DATE"}, auth=False)
        for r in d["statsTable"]:
            c = [x["content"] for x in r["cells"]]  # Rk, Sta, FPts, FP/G, PTS, REB, AST, ST, BLK, TO
            fpts, fpg = num(c[2]), num(c[3])
            sc = r["scorer"]
            out[sc["scorerId"]] = {"rk": int(c[0]) if c[0].isdigit() else None,
                "g": round(fpts / fpg) if fpts and fpg else 0, "fpts": fpts, "fpg": fpg,
                "pts": num(c[4]), "reb": num(c[5]), "ast": num(c[6]), "st": num(c[7]),
                "blk": num(c[8]), "to": num(c[9]), "tm": sc.get("teamShortName"), "pos": sc.get("posShortNames")}
        if page >= d["paginatedResultSet"]["totalNumPages"]:
            break
        page += 1
    json.dump(out, open(ROOT / "data" / "player_stats.json", "w"), separators=(",", ":"))
    print(len(out) - 1, "players", season, file=sys.stderr)


if __name__ == "__main__":
    main()
