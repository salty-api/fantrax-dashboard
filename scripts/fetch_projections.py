#!/usr/bin/env python3
"""Snapshot Fantrax weekly projections for the current season (regular-season periods only).

  data/proj_players.csv  season, period, team_id, player_id, proj  (per-player projected FPts, from getLiveScoringStats)
  data/proj_teams.csv    season, period, team_id, proj          (best counted lineup built from the player projections)

Fantrax's own team projection (getStandings proj=true) ignores the period argument, so team totals are derived:
3 G + 3 F + 2 C + 2 best remaining G/F. This lands within ~1% of Fantrax's figure for the current period.

Fantrax only serves projections for the current/upcoming period, so each run keeps what it has:
  - the first unscored period is refreshed every run (it freezes the moment scores arrive);
  - the last scored period is fetched only if it has no snapshot yet;
  - every other period is left untouched.
"""
import csv, datetime, json, re, urllib.request
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


SLOT = {"PG": "G", "SG": "G", "G": "G", "SF": "F", "PF": "F", "F": "F", "C": "C"}
POS = {k: v.get("position") for k, v in json.load(open(D / "players_ids.json")).items()}


def lineup(ps):
    ps = sorted(ps, key=lambda x: -x[1])
    used, tot = set(), 0.0
    for g, n in (("G", 3), ("F", 3), ("C", 2)):
        for pid, v in [x for x in ps if SLOT.get(POS.get(x[0])) == g][:n]:
            used.add(pid); tot += v
    flex = [x for x in ps if x[0] not in used and SLOT.get(POS.get(x[0])) in ("G", "F")][:2]
    return tot + sum(v for _, v in flex)


def save_period_ends(lid, season):
    """data/periods.json: {season: {period: 'YYYY-MM-DD' last day}} so the dashboard knows when a week is over."""
    try:
        periods = call(lid, "getStandings", {"view": "SCHEDULE", "period": "1"})["displayedLists"]["periods"]
    except Exception as e:
        print(f"period dates skipped ({e})")
        return
    y0 = int(season[:4])
    out = {}
    for x in periods:
        m = re.match(r"(\d+) \((\w+) (\d+) - (\w+) (\d+)\)", x["object2"])
        if not m:
            continue
        em = datetime.datetime.strptime(m.group(4), "%b").month
        sm = datetime.datetime.strptime(m.group(2), "%b").month
        sy = y0 if sm >= 8 else y0 + 1
        ey = sy + (1 if em < sm else 0)
        out[m.group(1)] = f"{ey}-{em:02d}-{int(m.group(5)):02d}"
    path = D / "periods.json"
    allp = json.load(open(path)) if path.exists() else {}
    allp[season] = out
    json.dump(allp, open(path, "w"), indent=0)


def read(path):
    return list(csv.DictReader(open(path))) if path.exists() else []


def main():
    cfg = json.load(open(ROOT / "leagues.json"))
    season = cfg["current"]
    lid = cfg["leagues"][season]
    scored = {}
    for m in csv.DictReader(open(D / "matchups.csv")):
        if m["season"] == season and m["phase"] == "regular":
            scored[int(m["period"])] = scored.get(int(m["period"]), 0) + float(m["away_pts"] or 0) + float(m["home_pts"] or 0)
    unscored = sorted(p for p, v in scored.items() if v == 0)
    done = sorted(p for p, v in scored.items() if v > 0)
    save_period_ends(lid, season)
    teams, players = read(D / "proj_teams.csv"), read(D / "proj_players.csv")
    have = {(r["season"], int(r["period"])) for r in teams}
    todo = []
    if unscored:
        todo.append(unscored[0])
    if done and (season, done[-1]) not in have:
        todo.append(done[-1])
    for p in todo:
        try:
            live = call(lid, "getLiveScoringStats", {"period": str(p)})
        except Exception as e:  # projections are a nice-to-have; never break the refresh
            print(f"period {p}: skipped ({e})")
            continue
        pr = []
        for tid, v in live["statsPerTeam"]["allTeamsStats"].items():
            for pid, x in v.get("ACTIVE", {}).get("calculatedProjectedTotalsMap", {}).items():
                pr.append({"season": season, "period": p, "team_id": tid, "player_id": pid, "proj": round(x, 2)})
        tr = [{"season": season, "period": p, "team_id": tid, "proj": round(lineup([(r["player_id"], r["proj"]) for r in pr if r["team_id"] == tid]), 2)}
              for tid in {r["team_id"] for r in pr}]
        if not tr:
            continue
        teams = [r for r in teams if not (r["season"] == season and int(r["period"]) == p)] + tr
        players = [r for r in players if not (r["season"] == season and int(r["period"]) == p)] + pr
        print(f"{season} period {p}: {len(tr)} teams, {len(pr)} player projections")
    for name, rows, cols in (("proj_teams.csv", teams, ["season", "period", "team_id", "proj"]),
                             ("proj_players.csv", players, ["season", "period", "team_id", "player_id", "proj"])):
        with open(D / name, "w", newline="") as f:
            w = csv.DictWriter(f, cols)
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
