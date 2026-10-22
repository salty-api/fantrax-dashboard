#!/usr/bin/env python3
"""Snapshot each player's games played and FP/G per scoring period for the current season (public, no login).

  data/player_games.csv  season, period, player_id, g, fpg

g = FPts / FP/G from getPlayerStats BY_PERIOD (all rostered players). Used to turn counted FPts into FPts per game,
which adjusts for scheduling differences. A period is refreshed while it is live and for two days after it ends.
"""
import csv, datetime, json, sys, zoneinfo
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import call, ROOT

D = ROOT / "data"


def num(s):
    try:
        return float((s or "").replace(",", ""))
    except ValueError:
        return 0.0


def main():
    cfg = json.load(open(ROOT / "leagues.json"))
    season = cfg["current"]
    lid = cfg["leagues"][season]
    ends = json.load(open(D / "periods.json")).get(season, {}) if (D / "periods.json").exists() else {}
    today = datetime.datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles")).date()
    periods = sorted({int(r["period"]) for r in csv.DictReader(open(D / "player_weeks.csv")) if r["season"] == season})
    path = D / "player_games.csv"
    old = list(csv.DictReader(open(path))) if path.exists() else []
    have = {int(r["period"]) for r in old if r["season"] == season}
    new = []
    for p in periods:
        end = ends.get(str(p))
        recent = end is not None and datetime.date.fromisoformat(end) + datetime.timedelta(days=2) >= today
        if p in have and not recent:
            continue
        try:
            page, rows = 1, []
            while True:
                d = call(lid, "getPlayerStats", {"statusOrTeamFilter": "ALL_TAKEN", "timeframeTypeCode": "BY_PERIOD", "period": str(p),
                         "maxResultsPerPage": "500", "pageNumber": str(page)}, auth=False)
                rows += d["statsTable"]
                if page >= d["paginatedResultSet"]["totalNumPages"]:
                    break
                page += 1
        except Exception as e:  # nice-to-have; never break the refresh
            print(f"period {p}: skipped ({e})")
            continue
        got = []
        for r in rows:
            c = r["cells"]
            fpts, fpg = num(c[3]["content"]), num(c[4]["content"])
            got.append({"season": season, "period": p, "player_id": r["scorer"]["scorerId"],
                        "g": round(fpts / fpg) if fpg else 0, "fpg": fpg})
        old = [r for r in old if not (r["season"] == season and int(r["period"]) == p)]
        new += got
        print(f"{season} period {p}: {len(got)} players")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, ["season", "period", "player_id", "g", "fpg"])
        w.writeheader()
        w.writerows(old + new)


if __name__ == "__main__":
    main()
