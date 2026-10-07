#!/usr/bin/env python3
"""Fetch Fantrax Platinum league history from the public Fantrax API.

Reads leagues.json (season -> leagueId) and writes, per season:
  data/standings.csv  season, rank, team, team_id, w, l, t, pf, pa
  data/matchups.csv   season, phase, period, away, away_pts, home, home_pts
  data/playoffs.csv   season, round, ...  (folded into matchups.csv with phase=playoff)
Add older seasons to leagues.json and re-run.
Usage: fetch_history.py [--current | --seasons 2025-26 ...]  (default: all seasons)
Only the targeted seasons are rewritten; every other season is kept as stored.
"""
import csv, json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://www.fantrax.com/fxpa/req?leagueId={}"


def call(league, method, data, auth=True):
    body = json.dumps({"msgs": [{"method": method, "data": data}]}).encode()
    hdr = {"Content-Type": "text/plain", "User-Agent": "Mozilla/5.0"}
    ck = os.environ.get("FANTRAX_COOKIE")  # browser Cookie header value, never committed
    cf = Path.home() / ".fantrax_cookie"
    if auth and not ck and cf.exists():
        ck = cf.read_text().strip()
    if ck and auth:
        hdr["Cookie"] = ck
    req = urllib.request.Request(URL.format(league), body, hdr)
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    resp = out["responses"][0]
    if "pageError" in resp:
        raise RuntimeError(f"{method}: {resp['pageError']['code']}")
    return resp["data"]


def num(s):
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def pairs(table):
    for r in table.get("rows", []):
        c = r["cells"]
        yield (c[0]["content"], c[0].get("teamId"), num(c[1]["content"]),
               c[2]["content"], c[2].get("teamId"), num(c[3]["content"]))


def fxea(league, method):
    req = urllib.request.Request(
        f"https://www.fantrax.com/fxea/general/{method}?leagueId={league}",
        headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fallback(lid, season, standings, matchups):
    """Public fxea API: final standings (record, PF) and pairings, but no scores."""
    for r in fxea(lid, "getStandings"):
        w, l, t = r["points"].split("-")
        standings.append([season, r["rank"], r["teamName"], r["teamId"], w, l, t,
                          r["totalPointsFor"], None])
    info = fxea(lid, "getLeagueInfo")
    last_reg = info["playoffs"]["lastRegularSeasonPeriod"]
    for m in info["matchups"]:
        phase = "regular" if m["period"] <= last_reg else "playoff"
        for g in m["matchupList"]:
            a, h = g.get("away") or {}, g.get("home") or {}
            nm = lambda x: x.get("name") or info["teamInfo"].get(x.get("id"), {}).get("name")
            matchups.append([season, phase, m["period"], nm(a), a.get("id"), None,
                             nm(h), h.get("id"), None])


def read_rows(path):
    return list(csv.reader(open(path)))[1:] if path.exists() else []


def target_seasons(cfg, argv):
    """--current: only the live season; --seasons A B: those; default: every season."""
    if "--current" in argv:
        return [cfg["current"]]
    if "--seasons" in argv:
        return argv[argv.index("--seasons") + 1:]
    return list(cfg["leagues"])


def main():
    cfg = json.load(open(ROOT / "leagues.json"))
    targets = target_seasons(cfg, sys.argv[1:])
    standings, matchups = [], []
    for season, lid in cfg["leagues"].items():
        if season not in targets:
            continue
        print(season, lid, file=sys.stderr)
        try:
            d = call(lid, "getStandings", {"view": "REGULAR_SEASON"})
        except RuntimeError as e:
            print(f"  {season}: {e}; using fxea fallback (no scores/playoffs)", file=sys.stderr)
            fallback(lid, season, standings, matchups)
            continue
        for r in d["tableList"][0]["rows"]:
            f, c = r["fixedCells"], r["cells"]
            standings.append([season, f[0]["content"], f[1]["content"], f[1].get("teamId"),
                              c[0]["content"], c[1]["content"], c[2]["content"],
                              num(c[5]["content"]), num(c[6]["content"])])
        periods = d["displayedLists"]["periods"]
        last = periods[-1]["object1"] if periods else 1
        s = call(lid, "getStandings", {"view": "SCHEDULE", "period": last})
        for t in s["tableList"]:
            n = int(t["caption"].rsplit(" ", 1)[1])
            for a, at, ap, h, ht, hp in pairs(t):
                matchups.append([season, "regular", n, a, at, ap, h, ht, hp])
        p = call(lid, "getStandings", {"view": "PLAYOFFS"})
        for t in p["tableList"]:
            cap = t["caption"]
            if not cap.startswith("Playoffs - Round"):
                continue
            n = int(cap.rsplit(" ", 1)[1])
            for a, at, ap, h, ht, hp in pairs(t):
                matchups.append([season, "playoff", n, a, at, ap, h, ht, hp])
    out = ROOT / "data"
    out.mkdir(exist_ok=True)
    # seasons not being refreshed are kept exactly as stored (never rewritten)
    keep_s = [r for r in read_rows(out / "standings.csv") if r[0] not in targets]
    keep_m = [r for r in read_rows(out / "matchups.csv") if r[0] not in targets]
    standings = sorted(keep_s + standings, key=lambda r: str(r[0]))
    matchups = sorted(keep_m + matchups, key=lambda r: str(r[0]))
    with open(out / "standings.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["season", "rank", "team", "team_id", "w", "l", "t", "pf", "pa"])
        w.writerows(standings)
    with open(out / "matchups.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["season", "phase", "period", "away", "away_id", "away_pts", "home", "home_id", "home_pts"])
        w.writerows(matchups)
    print(f"{len(standings)} standings rows, {len(matchups)} matchups", file=sys.stderr)


if __name__ == "__main__":
    main()
