#!/usr/bin/env python3
"""Snapshot bench players (rostered but not in the counted lineup) with their weekly FPts for the current season.

  data/bench.csv  season, period, team_id, player_id, fpts, status

Fantrax only reports who was on each roster for the current period, so a period is refreshed while it is live
and for two days after it ends (late stat corrections); after that it is left as stored.
Counted players come from data/player_weeks.csv (run fetch_players.py first).
"""
import csv, datetime, json, urllib.request, zoneinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
URL = "https://www.fantrax.com/fxpa/req?leagueId={}"


def call(league, method, data):
    body = json.dumps({"msgs": [{"method": method, "data": data}]}).encode()
    req = urllib.request.Request(URL.format(league), body, {"Content-Type": "text/plain", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)["responses"][0]
    if "pageError" in resp:
        raise RuntimeError(f"{method}: {resp['pageError']['code']}")
    return resp["data"]


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
    counted = {}
    for r in csv.DictReader(open(D / "player_weeks.csv")):
        if r["season"] == season:
            counted.setdefault(int(r["period"]), set()).add((r["team_id"], r["player_id"]))
    path = D / "bench.csv"
    old = list(csv.DictReader(open(path))) if path.exists() else []
    have = {int(r["period"]) for r in old if r["season"] == season}
    new = []
    for p in sorted(counted):
        end = ends.get(str(p))
        recent = end is not None and datetime.date.fromisoformat(end) + datetime.timedelta(days=2) >= today
        if p in have and not recent:
            continue
        if end is None and p != max(counted):
            continue
        try:
            page, rows = 1, []
            while True:
                # BY_PERIOD ignores `period` once a week is over; BY_DATE with the week's own dates works for any week
                pe = datetime.date.fromisoformat(end)
                ps = datetime.date.fromisoformat(ends[str(p - 1)]) + datetime.timedelta(days=1) if str(p - 1) in ends else pe - datetime.timedelta(days=6)
                d = call(lid, "getPlayerStats", {"statusOrTeamFilter": "ALL_TAKEN", "timeframeTypeCode": "BY_DATE", "startDate": ps.isoformat(),
                                                  "endDate": pe.isoformat(), "maxResultsPerPage": "500", "pageNumber": str(page)})
                hdr = [h.get("shortName") for h in d["tableHeader"]["cells"]]
                assert hdr[:3] == ["Sta", "Ros", "FPts"], f"unexpected columns {hdr[:3]}"
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
            tid, pid = c[0].get("teamId"), r["scorer"]["scorerId"]  # BY_DATE columns: Sta, Ros, FPts, FP/G (no Rk)
            if tid and (tid, pid) not in counted[p]:
                got.append({"season": season, "period": p, "team_id": tid, "player_id": pid, "fpts": num(c[2]["content"]), "status": c[1]["content"]})
        if got:
            old = [r for r in old if not (r["season"] == season and int(r["period"]) == p)]
            new += got
            print(f"{season} period {p}: {len(got)} bench players")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, ["season", "period", "team_id", "player_id", "fpts", "status"])
        w.writeheader()
        w.writerows(old + new)


if __name__ == "__main__":
    main()
