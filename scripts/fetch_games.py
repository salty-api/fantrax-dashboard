#!/usr/bin/env python3
"""Snapshot each player's games played and FP/G per scoring period for the current season (public, no login).

  data/player_games.csv  season, period, player_id, g, fpg, fpts
  data/game_log.csv      season, period, player_id, game_date, fpts, pts, reb, ast, st, blk, to, min, fgm, fga, ftm, fta, tpm, tpa, oreb, dreb, pf

g = FPts / FP/G from getPlayerStats BY_PERIOD (all players with games). Used to turn counted FPts into FPts per game,
which adjusts for scheduling differences. A period is refreshed while it is live and for two days after it ends.

Fantrax has no per-game stats, so game_log.csv is built by snapshots: when a player's game count is exactly one more
than the games already logged, the new game's score is period FPts minus the logged scores. Gaps of 2+ games are skipped.
game_date is the Pacific game night of the snapshot (the first run falls back to the date in the player's news icon).
"""
import csv, datetime, json, re, sys, zoneinfo
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import ROOT
from fantrax_stats import fetch_all

D = ROOT / "data"


STAT_COLS = ["pts", "reb", "ast", "st", "blk", "to", "min", "fgm", "fga", "ftm", "fta", "tpm", "tpa", "oreb", "dreb", "pf"]


def period_totals(r):
    """Cumulative period box score: view 5 gives totals, the other views are per-game averages (counts round back exactly)."""
    t, a, g = r["tot"], r["avg"], r["g"]
    out = {k: int(round(t[k] or 0)) for k in ("pts", "reb", "ast", "st", "blk", "to")}
    out["min"] = round((a["min"] or 0) * g, 1)
    for k in ("fgm", "fga", "ftm", "fta", "tpm", "tpa", "oreb", "dreb", "pf"):
        out[k] = int(round((a[k] or 0) * g))
    return out


def main():
    cfg = json.load(open(ROOT / "leagues.json"))
    season = cfg["current"]
    lid = cfg["leagues"][season]
    ends = json.load(open(D / "periods.json")).get(season, {}) if (D / "periods.json").exists() else {}
    now = datetime.datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles"))
    today, night = now.date(), (now - datetime.timedelta(hours=9)).date()  # games end by ~1am PT, so 9am PT starts a new day
    lpath = D / "game_log.csv"
    fresh_log = not lpath.exists()
    log = list(csv.DictReader(open(lpath))) if lpath.exists() else []
    periods = sorted({int(r["period"]) for r in csv.DictReader(open(D / "player_weeks.csv")) if r["season"] == season})
    path = D / "player_games.csv"
    old = list(csv.DictReader(open(path))) if path.exists() else []
    have = {int(r["period"]) for r in old if r["season"] == season}
    new, newlog = [], []
    for p in periods:
        end = ends.get(str(p))
        recent = end is not None and datetime.date.fromisoformat(end) + datetime.timedelta(days=2) >= today
        if p in have and not recent:
            continue
        try:
            snap = fetch_all(lid, {"timeframeTypeCode": "BY_PERIOD", "period": str(p)})
        except Exception as e:  # nice-to-have; never break the refresh
            print(f"period {p}: skipped ({e})")
            continue
        got = []
        for pid, r in snap.items():
            g, fpts, fpg = r["g"], r["fpts"] or 0.0, r["fpg"] or 0.0
            if not g:
                continue
            got.append({"season": season, "period": p, "player_id": pid, "g": g, "fpg": fpg, "fpts": fpts})
            cum = period_totals(r)
            mine = [x for x in log + newlog if x["season"] == season and int(x["period"]) == p and x["player_id"] == pid]
            if len(mine) == 1 and g == 1 and not mine[0].get("pts"):  # legacy row logged before box scores: this is its only game
                mine[0].update(cum)
            if g - len(mine) == 1:
                gd = night
                if fresh_log:
                    if 9 <= now.hour < 17:  # daytime: no games are being played, so anything seen was last night's
                        gd = night - datetime.timedelta(days=1)  # first run: use the date in the player's latest game news if there is one
                    for ic in r["icons"]:
                        m = re.match(r"(\w{3}) (\d{1,2}), .*(?:point|ended|finished)", ic.get("tooltip", ""))
                        if m:
                            try:
                                hd = datetime.datetime.strptime(f"{m[1]} {m[2]} {today.year}", "%b %d %Y").date()
                            except ValueError:
                                continue
                            if night - datetime.timedelta(days=3) <= hd <= night:
                                gd = hd
                                break
                row = {"season": season, "period": p, "player_id": pid, "game_date": gd.isoformat(),
                       "fpts": round(fpts - sum(float(x["fpts"]) for x in mine), 2)}
                if all(x.get("pts") not in (None, "") for x in mine):  # box score = period totals minus games already logged
                    for k in STAT_COLS:
                        v = cum[k] - sum(float(x[k]) for x in mine)
                        row[k] = round(v, 1) if k == "min" else int(round(v))
                newlog.append(row)
        old = [r for r in old if not (r["season"] == season and int(r["period"]) == p)]
        new += got
        print(f"{season} period {p}: {len(got)} players")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, ["season", "period", "player_id", "g", "fpg", "fpts"])
        w.writeheader()
        w.writerows(old + new)
    with open(lpath, "w", newline="") as f:
        w = csv.DictWriter(f, ["season", "period", "player_id", "game_date", "fpts"] + STAT_COLS)
        w.writeheader()
        w.writerows(log + newlog)
    print(f"{len(newlog)} new games logged")


if __name__ == "__main__":
    main()
