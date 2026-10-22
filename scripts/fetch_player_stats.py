#!/usr/bin/env python3
"""Fetch per-game stats for the live season once it has scores, otherwise the last finished season (public, no login).
Writes data/player_stats.json: id -> {rk, g, fpts, fpg, pts, reb, ast, st, blk, to, tm, pos}
plus a "_season" key with the season label.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import ROOT, read_rows
from fantrax_stats import fetch_all


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
    out = {"_season": season}
    for pid, s in fetch_all(cfg[season], {"timeframeTypeCode": "YEAR_TO_DATE"}).items():
        g, t, a = s["g"], s["tot"], s["avg"]
        pg = lambda k: round(t[k] / g, 1) if g and t.get(k) is not None else None
        out[pid] = {"rk": s["rk"], "g": g, "fpts": s["fpts"], "fpg": s["fpg"], "tm": s["tm"], "pos": s["pos"],
                    # per-game box score (the dashboard player page shows these)
                    "pts": pg("pts"), "reb": pg("reb"), "ast": pg("ast"), "st": pg("st"), "blk": pg("blk"), "to": pg("to"),
                    # season totals of the six scoring stats, plus double/triple doubles
                    "tot": t,
                    # per-game averages of the other box score stats (minutes, shooting, rebounds split, fouls)
                    "avg": a}
    out = {k: v for k, v in out.items() if k == "_season" or v["g"]}
    json.dump(out, open(ROOT / "data" / "player_stats.json", "w"), separators=(",", ":"))
    print(len(out) - 1, "players", season, file=sys.stderr)


if __name__ == "__main__":
    main()
