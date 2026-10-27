#!/usr/bin/env python3
"""Build dashboard/index.html from data/standings.csv + data/matchups.csv + data/owners.csv.

data/owners.csv maps (season, team name) -> owner. Missing rows are appended with a
best-guess owner (confirmed=0); edit the file and re-run to correct. Never overwritten.
"""
import shutil, csv, datetime, json, re, sys, zoneinfo
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"

GUESS = {  # normalized team name -> owner (first pass, to be confirmed)
    "tyhoward": "T-How", "thow": "T-How", "t-how": "T-How",
    "xrossbone": "Jackson", "jackson": "Jackson",
    "bucky conway": "Conway", "conway": "Conway",
    "salty": "Salty", "saltys aspirations": "Salty",
    "guckien": "Guckien", "guckien & giddey & kcp & deni avdija": "Guckien",
    "stephenrooney90": "Rooney", "rooney": "Rooney",
    "blackjack": "Blackjacks", "blackjacks": "Blackjacks", "philadephia blackjacks": "Blackjacks",
    "rileyrojo": "Riley", "rileys hefty leftys": "Riley", "riley mcelwembanyama": "Riley",
    "picurtis": "Pierson", "piersons autodrafters": "Pierson",
    "ejbuser": "Buser", "buser has wemby": "Buser", "halibuser": "Buser",
}


def norm(s):
    return re.sub(r"[’']", "", s or "").strip().lower()


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_owners(standings):
    """Map (season, team name) -> owner via data/owners.csv.

    New team names are resolved automatically when possible:
      1. same Fantrax team_id already mapped this season (a mid-season rename) -> inherit that owner
      2. name matches the GUESS table -> that owner, flagged confirmed=0 for review
    Anything else is left as its own name and reported by check_owners(), which fails the build.
    """
    p = D / "owners.csv"
    rows = list(csv.DictReader(open(p))) if p.exists() else []
    tid = {(r["season"], r["team"]): r["team_id"] for r in standings}
    for r in rows:
        r.setdefault("team_id", ""); r["team_id"] = r["team_id"] or tid.get((r["season"], r["team"]), "")
    have = {(r["season"], r["team"]) for r in rows}
    by_id = {(r["season"], r["team_id"]): r["owner"] for r in rows if r["team_id"]}
    for r in standings:
        key = (r["season"], r["team"])
        if key in have:
            continue
        if (r["season"], r["team_id"]) in by_id:  # renamed mid-season
            o, conf = by_id[(r["season"], r["team_id"])], "1"
            print(f"  rename detected: {r['season']} {r['team']!r} -> {o}")
        elif GUESS.get(norm(r["team"])):
            o, conf = GUESS[norm(r["team"])], "0"
        else:
            o, conf = r["team"], "0"
        rows.append({"season": r["season"], "team": r["team"], "owner": o, "confirmed": conf, "team_id": r["team_id"]})
        have.add(key)
        by_id[(r["season"], r["team_id"])] = o
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, ["season", "team", "owner", "confirmed", "team_id"])
        w.writeheader()
        w.writerows(rows)
    known = {r["owner"] for r in rows if r["confirmed"] == "1"}
    unmapped = [(r["season"], r["team"]) for r in rows if r["owner"] not in known]
    review = [(r["season"], r["team"], r["owner"]) for r in rows if r["confirmed"] != "1" and r["owner"] in known]
    if review:
        print("NOTE auto-mapped, please review data/owners.csv (set confirmed=1):", review)
    if unmapped:
        sys.exit("ERROR: unmapped team names - add them to data/owners.csv, then re-run: " + str(unmapped))
    return {(r["season"], r["team"]): r["owner"] for r in rows}


def check_history(standings, matchups, current):
    """Finished seasons must keep their scores; a damaged history must never be published."""
    for se in sorted({r["season"] for r in standings} - {current}):
        scored = sum(1 for m in matchups if m["season"] == se and m["away_pts"] not in ("", None) and float(m["away_pts"]) > 0)
        if scored < 100:
            sys.exit(f"ERROR: {se} has only {scored} scored matchups (expected 100+). History looks damaged; refusing to build.")


def clean_name(n):
    return " ".join(reversed([x.strip() for x in n.split(",", 1)])) if "," in n else n


def tracker_and_recap(standings, own, played):
    """Player ownership history (weekly rosters + draft) and per-week player scoring."""
    tid_owner = {(r["season"], r["team_id"]): own[(r["season"], r["team"])] for r in standings}
    ids = json.load(open(D / "players_ids.json"))
    extra = json.load(open(D / "players_extra.json")) if (D / "players_extra.json").exists() else {}
    names = {}
    for k, v in ids.items():
        names[k] = [clean_name(v["name"]), v.get("position", "")]
    for k, v in extra.items():
        names[k] = [v[0], v[2] or ""]

    # ownership stints: consecutive periods on one team within a season
    by = defaultdict(list)
    for r in csv.DictReader(open(D / "rosters.csv")):
        by[(r["season"], r["team_id"], r["player_id"])].append(int(r["period"]))
    stints = defaultdict(list)
    for (se, tid, pid), ps in by.items():
        o = tid_owner.get((se, tid))
        if not o:
            continue
        ps.sort()
        a = b = ps[0]
        for x in ps[1:] + [None]:
            if x is not None and x == b + 1:
                b = x
                continue
            stints[pid].append([se, o, a, b])
            if x is not None:
                a = b = x
    for v in stints.values():
        v.sort(key=lambda x: (x[0], x[2]))
    picks = defaultdict(list)
    for r in csv.DictReader(open(D / "draft.csv")):
        o = tid_owner.get((r["season"], r["team_id"]))
        if o:
            picks[r["player_id"]].append([r["season"], o, int(r["round"]), int(r["pick"])])
    pids = sorted(set(stints) | set(picks))
    players = {pid: names.get(pid, ["#" + pid, ""]) for pid in pids}
    # weekly counted-lineup scoring (player level)
    pw = []
    gp = {}
    if (D / "player_games.csv").exists():
        for r in csv.DictReader(open(D / "player_games.csv")):
            gp[(r["season"], int(r["period"]), r["player_id"])] = int(r["g"])
    for r in csv.DictReader(open(D / "player_weeks.csv")):
        o = tid_owner.get((r["season"], r["team_id"]))
        if o:
            pw.append([r["season"], int(r["period"]), o, r["player_id"], float(r["fpts"]), gp.get((r["season"], int(r["period"]), r["player_id"]))])
            players.setdefault(r["player_id"], names.get(r["player_id"], ["#" + r["player_id"], ""]))
    bn = {}
    if (D / "bench.csv").exists():
        for r in csv.DictReader(open(D / "bench.csv")):
            o = tid_owner.get((r["season"], r["team_id"]))
            if o:
                bn.setdefault(f'{r["season"]}|{r["period"]}', {}).setdefault(o, []).append([r["player_id"], float(r["fpts"])])
                players.setdefault(r["player_id"], names.get(r["player_id"], ["#" + r["player_id"], ""]))
        for v in bn.values():
            for lst in v.values():
                lst.sort(key=lambda x: -x[1])
    gl = []
    if (D / "game_log.csv").exists():
        for r in csv.DictReader(open(D / "game_log.csv")):
            gl.append([r["season"], int(r["period"]), r["game_date"], r["player_id"], float(r["fpts"])])
            players.setdefault(r["player_id"], names.get(r["player_id"], ["#" + r["player_id"], ""]))
    hs = json.load(open(D / "headshots.json")) if (D / "headshots.json").exists() else {}
    heads = {}
    for pid in players:
        m = re.search(r"_96_(\d+)\.png", hs.get(pid, ""))
        if m:
            heads[pid] = m.group(1)
    ps = json.load(open(D / "player_stats.json")) if (D / "player_stats.json").exists() else {}
    stats = {k: {x: v[x] for x in ("rk", "g", "fpts", "fpg", "pts", "reb", "ast", "st", "blk", "to", "tm", "pos")} for k, v in ps.items() if k in players and k != "_season"}  # box score detail (tot/avg) goes to data.json only
    # draft boards: per season, teams in round-1 order + every pick with the player's full-season stats (all NBA games, not just games on this team)
    tname = {(r["season"], r["team_id"]): r["team"] for r in standings}
    cur_season = ps.get("_season", "")
    draft = {}
    for r in csv.DictReader(open(D / "draft.csv")):
        se, tid = r["season"], r["team_id"]
        o = tid_owner.get((se, tid))
        if not o:
            continue
        d = draft.setdefault(se, {"teams": {}, "picks": []})
        d["teams"][o] = tname.get((se, tid), o)
        d["picks"].append([int(r["round"]), int(r["pick"]), o, r["player_id"]])
    for se, d in draft.items():
        sf = D / f"player_stats_{se}.json"
        st = json.load(open(sf)) if sf.exists() else (ps if se == cur_season else None)
        d["order"] = [p[2] for p in sorted(d["picks"]) if p[0] == 1]
        d["done"] = se != cur_season
        for p in d["picks"]:
            v = st.get(p[3]) if st else None
            p += [v["g"], v["fpts"], v["fpg"]] if v and v.get("g") else ([0, 0, 0] if st else [None, None, None])
            players.setdefault(p[3], names.get(p[3], ["#" + p[3], ""]))
            if st and v and v.get("pos") and not players[p[3]][1]:
                players[p[3]][1] = v["pos"]
        d["maxg"] = max((v["g"] for k, v in st.items() if k != "_season"), default=0) if st else None
    return {"draft": draft, "players": players, "heads": heads, "stats": stats, "statsSeason": ps.get("_season", ""), "stints": {k: stints[k] for k in pids if k in stints},
            "picks": {k: picks[k] for k in pids if k in picks}, "pw": pw, "bn": bn, "gl": gl,
            "seasonsAll": sorted({r["season"] for r in standings})}


def current_rosters(cur, nm):
    """Each owner's roster in the latest scoring period of the current season (for the site chatbot)."""
    owner_by_tid = {(r["season"], r["team_id"]): r["owner"] for r in csv.DictReader(open(D / "owners.csv")) if r.get("team_id")}
    rows = [r for r in csv.DictReader(open(D / "rosters.csv")) if r["season"] == cur]
    if not rows:
        return {}
    last = max(int(r["period"]) for r in rows)
    out = defaultdict(list)
    for r in rows:
        o = owner_by_tid.get((cur, r["team_id"]))
        if o and int(r["period"]) == last:
            out[o].append({"player": nm(r["player_id"])[0], "player_id": r["player_id"], "status": r["status"]})
    return {o: sorted(v, key=lambda x: x["player"]) for o, v in sorted(out.items())}


BOX = ["pts", "reb", "ast", "st", "blk", "to", "min", "fgm", "fga", "ftm", "fta", "tpm", "tpa", "oreb", "dreb", "pf"]


def export_json(data, cur, path):
    """Readable, self-describing copy of the data for other tools (served at /data.json)."""
    nm = lambda pid: (data["players"].get(pid) or ["#" + pid, ""])
    pl = lambda pid: {"id": pid, "name": nm(pid)[0], "pos": nm(pid)[1]}
    box = lambda r: {k: float(r[k]) if k == "min" else int(float(r[k])) for k in BOX if r.get(k) not in (None, "")}
    full_stats = json.load(open(D / "player_stats.json")) if (D / "player_stats.json").exists() else {}
    out = {
        "about": "Fantrax Platinum league data, rebuilt on every refresh. Scores are Fantrax FPts. Weeks are scoring periods (current season = %s)." % cur,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current_season": cur,
        "owners": data["owners"],
        "seasons": data["seasons"],
        "standings": [{"season": r["s"], "owner": r["o"], "team": r["team"], "rank": r["rk"], "w": r["w"], "l": r["l"], "t": r["t"],
                       "pf": r["pf"], "pa": r["pa"], "finish": r["fin"]} for r in data["rows"]],
        "matchups": [{"season": g["s"], "phase": g["ph"], "week": g["wk"], "away": g["a"], "home": g["h"],
                      "away_pts": g["ap"], "home_pts": g["hp"], "in_progress": g["live"]} for g in data["games"]],
        "players": {pid: {"name": v[0], "pos": v[1]} for pid, v in data["players"].items()},
        "draft": [{"season": se, "round": rd, "pick": pk, "owner": o, "player": pl(pid)["name"], "player_id": pid}
                  for pid, lst in data["picks"].items() for se, o, rd, pk in lst],
        "player_weeks_counted": [{"season": se, "week": wk, "owner": o, "player": nm(pid)[0], "player_id": pid, "fpts": fp, "games": gp}
                                 for se, wk, o, pid, fp, gp in data["pw"]],
        "bench_weeks": [{"season": cur, "week": int(k.split("|")[1]), "owner": o, "player": nm(pid)[0], "player_id": pid, "fpts": fp}
                        for k, v in data["bn"].items() if k.startswith(cur + "|") for o, lst in v.items() for pid, fp in lst],
        "game_log": [{"season": r["season"], "week": int(r["period"]), "date": r["game_date"], "player": nm(r["player_id"])[0],
                      "player_id": r["player_id"], "fpts": float(r["fpts"]), **box(r)}
                     for r in (csv.DictReader(open(D / "game_log.csv")) if (D / "game_log.csv").exists() else [])],
        "player_season_stats": {pid: {"name": nm(pid)[0], **v} for pid, v in full_stats.items() if pid != "_season"},
        "player_season_stats_season": data["statsSeason"],
        "past_season_player_stats": {f.stem.replace("player_stats_", ""): "https://fantrax.whohashim.com/stats/" + f.name
                                     for f in sorted(D.glob("player_stats_20*.json"))},
        "current_rosters": current_rosters(cur, nm),
    }
    path.write_text(json.dumps(out, separators=(",", ":")))


def main():
    standings = list(csv.DictReader(open(D / "standings.csv")))
    matchups = list(csv.DictReader(open(D / "matchups.csv")))
    cur = json.load(open(ROOT / "leagues.json"))["current"]
    check_history(standings, matchups, cur)
    own = load_owners(standings)

    tproj = {(r["season"], int(r["period"]), r["team_id"]): float(r["proj"]) for r in csv.DictReader(open(D / "proj_teams.csv"))} if (D / "proj_teams.csv").exists() else {}
    pj = {}
    if (D / "proj_players.csv").exists():
        for r in csv.DictReader(open(D / "proj_players.csv")):
            pj.setdefault(f'{r["season"]}|{r["period"]}', {})[r["player_id"]] = float(r["proj"])
    games = []
    for m in matchups:
        ap, hp = f(m["away_pts"]), f(m["home_pts"])
        if ap is None or hp is None or ap + hp == 0 or not m["away"] or not m["home"]:
            continue  # unplayed / bye
        s = m["season"]
        games.append({"s": s, "ph": m["phase"], "p": int(m["period"]),
                      "a": own[(s, m["away"])], "h": own[(s, m["home"])], "ap": ap, "hp": hp})
        if m["phase"] == "regular" and (s, int(m["period"]), m["away_id"]) in tproj:
            games[-1]["apx"] = tproj[(s, int(m["period"]), m["away_id"])]
            games[-1]["hpx"] = tproj.get((s, int(m["period"]), m["home_id"]))
    games.sort(key=lambda g: (g["s"], g["ph"] != "regular", g["p"]))
    lastreg = {}
    for g in games:
        if g["ph"] == "regular":
            lastreg[g["s"]] = max(lastreg.get(g["s"], 0), g["p"])
    for g in games:  # scoring period: playoff round r plays in period lastreg + r
        g["wk"] = g["p"] if g["ph"] == "regular" else lastreg[g["s"]] + g["p"]
    # weeks still in progress (current season, period not over in PT) stay out of standings, records and series
    ends = json.load(open(D / "periods.json")) if (D / "periods.json").exists() else {}
    today = datetime.datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles")).date().isoformat()
    curmax = max((g["wk"] for g in games if g["s"] == cur), default=0)
    for g in games:
        end = ends.get(g["s"], {}).get(str(g["wk"]))
        g["live"] = bool(g["s"] == cur and ((end is not None and end >= today) or (end is None and g["wk"] == curmax)))
    final = [g for g in games if not g["live"]]
    # Fantrax projections run high; scale team projections by actual/projected over finished weeks
    pairs = [(g[k + "p"], g[k + "px"]) for g in final for k in "ah" if g.get(k + "px")]
    pcal = round(sum(a for a, _ in pairs) / sum(x for _, x in pairs), 4) if pairs else 1.0
    for g in games:
        for k in "ah":
            if g.get(k + "px") is not None:
                g[k + "px"] = round(g[k + "px"] * pcal, 2)
    print(f"projection calibration x{pcal} from {len(pairs)} team-weeks")
    played = {g["s"] for g in games}
    seasons = sorted(played)

    # season rows
    rows = []
    for r in standings:
        if r["season"] not in played:
            continue
        o = own[(r["season"], r["team"])]
        reg = [g for g in final if g["s"] == r["season"] and g["ph"] == "regular" and o in (g["a"], g["h"])]
        pf = sum(g["ap"] if g["a"] == o else g["hp"] for g in reg)
        pa = sum(g["hp"] if g["a"] == o else g["ap"] for g in reg)
        rows.append({"s": r["season"], "o": o, "team": r["team"], "rk": int(r["rank"]),
                     "w": int(r["w"]), "l": int(r["l"]), "t": int(r["t"]),
                     "pf": round(pf, 2), "pa": round(pa, 2), "fin": "Missed"})
    key = {(r["s"], r["o"]): r for r in rows}

    # playoff finish
    for s in seasons:
        po = [g for g in final if g["s"] == s and g["ph"] == "playoff"]
        if not po:
            continue
        last = max(g["p"] for g in po)
        for g in po:
            for o in (g["a"], g["h"]):
                if key.get((s, o)) and key[(s, o)]["fin"] == "Missed":
                    key[(s, o)]["fin"] = "Semifinal"
        fin = [g for g in po if g["p"] == last][-1]
        win, lose = (fin["a"], fin["h"]) if fin["ap"] > fin["hp"] else (fin["h"], fin["a"])
        key[(s, win)]["fin"] = "Champion"
        key[(s, lose)]["fin"] = "Runner-up"

    owners = sorted({r["o"] for r in rows})

    # all-time + h2h
    at = {o: dict(o=o, w=0, l=0, t=0, pf=0.0, pa=0.0, titles=0, finals=0, playoffs=0,
                  pw=0, pl=0, seasons=0, rks=[]) for o in owners}
    h2h = {a: {b: [0, 0, 0, 0.0, 0.0] for b in owners if b != a} for a in owners}
    for r in rows:
        a = at[r["o"]]
        a["w"] += r["w"]; a["l"] += r["l"]; a["t"] += r["t"]
        a["pf"] += r["pf"]; a["pa"] += r["pa"]; a["seasons"] += 1; a["rks"].append(r["rk"])
        if r["fin"] != "Missed": a["playoffs"] += 1
        if r["fin"] == "Champion": a["titles"] += 1
        if r["fin"] in ("Champion", "Runner-up"): a["finals"] += 1
    for g in final:
        for me, op, mp, op_p in ((g["a"], g["h"], g["ap"], g["hp"]), (g["h"], g["a"], g["hp"], g["ap"])):
            x = h2h[me][op]
            x[0 if mp > op_p else 1 if mp < op_p else 2] += 1
            x[3] += mp; x[4] += op_p
            if g["ph"] == "playoff" and mp != op_p:
                at[me]["pw" if mp > op_p else "pl"] += 1
    for a in at.values():
        a["pf"] = round(a["pf"], 2); a["pa"] = round(a["pa"], 2)
        a["avg_rk"] = round(sum(a["rks"]) / len(a["rks"]), 2)
        del a["rks"]
    for a in h2h.values():
        for x in a.values():
            x[3] = round(x[3], 2); x[4] = round(x[4], 2)

    # records
    def gl(g, side):
        return {"s": g["s"], "ph": g["ph"], "p": g["p"], "o": g[side], "opp": g["h" if side == "a" else "a"],
                "pts": g["ap" if side == "a" else "hp"], "oppts": g["hp" if side == "a" else "ap"]}
    sides = [gl(g, "a") for g in final] + [gl(g, "h") for g in final]
    top = lambda lst, n=10: lst[:n]
    high = top(sorted(sides, key=lambda x: -x["pts"]))
    low = top(sorted(sides, key=lambda x: x["pts"]))
    win_sides = [x for x in sides if x["pts"] > x["oppts"]]
    blow = top(sorted(win_sides, key=lambda x: -(x["pts"] - x["oppts"])))
    close = top(sorted(win_sides, key=lambda x: x["pts"] - x["oppts"]))
    seas_pf = top(sorted(rows, key=lambda r: -r["pf"]))
    seas_rec = top(sorted(rows, key=lambda r: (-(r["w"] / max(1, r["w"] + r["l"] + r["t"])), -r["pf"])))
    # win streaks (regular + playoff, chronological)
    streaks = []
    for o in owners:
        cur = best = 0; best_end = None; cur_start = None; best_start = None
        for g in final:
            if o not in (g["a"], g["h"]):
                continue
            mp, op = (g["ap"], g["hp"]) if g["a"] == o else (g["hp"], g["ap"])
            if mp > op:
                if cur == 0: cur_start = (g["s"], g["p"])
                cur += 1
                if cur > best: best, best_end, best_start = cur, (g["s"], g["p"]), cur_start
            else:
                cur = 0
        streaks.append({"o": o, "n": best, "from": best_start, "to": best_end})
    streaks = top(sorted(streaks, key=lambda x: -x["n"]))

    data = {"owners": owners, "seasons": seasons, "rows": rows, "games": games,
            "alltime": sorted(at.values(), key=lambda a: (-a["titles"], -a["w"])), "h2h": h2h,
            "records": {"high": high, "low": low, "blow": blow, "close": close,
                        "seasPF": seas_pf, "seasRec": seas_rec, "streaks": streaks}}
    data["pj"] = pj
    # unplayed regular-season matchups (current season) for strength-of-schedule
    data["sched"] = [[int(m["period"]), own[(cur, m["away"])], own[(cur, m["home"])]] for m in matchups
                     if m["season"] == cur and m["phase"] == "regular" and (f(m["away_pts"]) or 0) + (f(m["home_pts"]) or 0) == 0
                     and (cur, m["away"]) in own and (cur, m["home"]) in own]
    data.update(tracker_and_recap(standings, own, seasons))
    data["gen"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    html = (ROOT / "scripts" / "template.html").read_text().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html)
    export_json(data, json.load(open(ROOT / "leagues.json"))["current"], out / "data.json")
    (out / "stats").mkdir(exist_ok=True)  # one-time past-season player stats (scripts/pull_past_stats.py), served as static files
    for fp in sorted(D.glob("player_stats_20*.json")):
        shutil.copyfile(fp, out / "stats" / fp.name)
    print(f"{len(games)} games, {len(rows)} season rows, owners={owners}")


if __name__ == "__main__":
    main()
