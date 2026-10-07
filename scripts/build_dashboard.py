#!/usr/bin/env python3
"""Build dashboard/index.html from data/standings.csv + data/matchups.csv + data/owners.csv.

data/owners.csv maps (season, team name) -> owner. Missing rows are appended with a
best-guess owner (confirmed=0); edit the file and re-run to correct. Never overwritten.
"""
import csv, json, re
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
    p = D / "owners.csv"
    rows = list(csv.DictReader(open(p))) if p.exists() else []
    have = {(r["season"], r["team"]) for r in rows}
    for r in standings:
        if (r["season"], r["team"]) not in have:
            g = GUESS.get(norm(r["team"]))
            rows.append({"season": r["season"], "team": r["team"], "owner": g or r["team"],
                         "confirmed": "0"})
            have.add((r["season"], r["team"]))
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, ["season", "team", "owner", "confirmed"])
        w.writeheader()
        w.writerows(rows)
    unk = [(r["season"], r["team"]) for r in rows if r["confirmed"] != "1"]
    if unk:
        print("UNCONFIRMED team names (edit data/owners.csv):", unk)
    return {(r["season"], r["team"]): r["owner"] for r in rows}


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
    for r in csv.DictReader(open(D / "player_weeks.csv")):
        o = tid_owner.get((r["season"], r["team_id"]))
        if o:
            pw.append([r["season"], int(r["period"]), o, r["player_id"], float(r["fpts"])])
            players.setdefault(r["player_id"], names.get(r["player_id"], ["#" + r["player_id"], ""]))
    hs = json.load(open(D / "headshots.json")) if (D / "headshots.json").exists() else {}
    heads = {}
    for pid in players:
        m = re.search(r"_96_(\d+)\.png", hs.get(pid, ""))
        if m:
            heads[pid] = m.group(1)
    ps = json.load(open(D / "player_stats.json")) if (D / "player_stats.json").exists() else {}
    stats = {k: v for k, v in ps.items() if k in players and k != "_season"}
    return {"players": players, "heads": heads, "stats": stats, "statsSeason": ps.get("_season", ""), "stints": {k: stints[k] for k in pids if k in stints},
            "picks": {k: picks[k] for k in pids if k in picks}, "pw": pw,
            "seasonsAll": sorted({r["season"] for r in standings})}


def main():
    standings = list(csv.DictReader(open(D / "standings.csv")))
    matchups = list(csv.DictReader(open(D / "matchups.csv")))
    own = load_owners(standings)

    games = []
    for m in matchups:
        ap, hp = f(m["away_pts"]), f(m["home_pts"])
        if ap is None or hp is None or ap + hp == 0 or not m["away"] or not m["home"]:
            continue  # unplayed / bye
        s = m["season"]
        games.append({"s": s, "ph": m["phase"], "p": int(m["period"]),
                      "a": own[(s, m["away"])], "h": own[(s, m["home"])], "ap": ap, "hp": hp})
    games.sort(key=lambda g: (g["s"], g["ph"] != "regular", g["p"]))
    lastreg = {}
    for g in games:
        if g["ph"] == "regular":
            lastreg[g["s"]] = max(lastreg.get(g["s"], 0), g["p"])
    for g in games:  # scoring period: playoff round r plays in period lastreg + r
        g["wk"] = g["p"] if g["ph"] == "regular" else lastreg[g["s"]] + g["p"]
    played = {g["s"] for g in games}
    seasons = sorted(played)

    # season rows
    rows = []
    for r in standings:
        if r["season"] not in played:
            continue
        o = own[(r["season"], r["team"])]
        reg = [g for g in games if g["s"] == r["season"] and g["ph"] == "regular" and o in (g["a"], g["h"])]
        pf = sum(g["ap"] if g["a"] == o else g["hp"] for g in reg)
        pa = sum(g["hp"] if g["a"] == o else g["ap"] for g in reg)
        rows.append({"s": r["season"], "o": o, "team": r["team"], "rk": int(r["rank"]),
                     "w": int(r["w"]), "l": int(r["l"]), "t": int(r["t"]),
                     "pf": round(pf, 2), "pa": round(pa, 2), "fin": "Missed"})
    key = {(r["s"], r["o"]): r for r in rows}

    # playoff finish
    for s in seasons:
        po = [g for g in games if g["s"] == s and g["ph"] == "playoff"]
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
    for g in games:
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
    sides = [gl(g, "a") for g in games] + [gl(g, "h") for g in games]
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
        for g in games:
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
    data.update(tracker_and_recap(standings, own, seasons))
    html = (ROOT / "scripts" / "template.html").read_text().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html)
    print(f"{len(games)} games, {len(rows)} season rows, owners={owners}")


if __name__ == "__main__":
    main()
