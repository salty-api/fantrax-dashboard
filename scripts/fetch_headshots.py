#!/usr/bin/env python3
"""Fetch each player's real headshot URL (suffix varies per player) and fill in names that
data/players_ids.json lacks. Scans the full player pool of every season in leagues.json, so
retired and rookie players are covered. Older private seasons use the login cookie if present.
Writes data/headshots.json (id -> url) and merges missing names into data/players_extra.json.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import call, ROOT


def pool(lid):
    for auth in (False, True):
        try:
            page, out = 1, []
            while True:
                d = call(lid, "getPlayerStats", {"statusOrTeamFilter": "ALL", "maxResultsPerPage": "500",
                         "pageNumber": str(page), "timeframeTypeCode": "YEAR_TO_DATE"}, auth=auth)
                out += [r["scorer"] for r in d["statsTable"]]
                if page >= d["paginatedResultSet"]["totalNumPages"]:
                    return out
                page += 1
        except RuntimeError:
            continue
    return []


def main():
    cfg = json.load(open(ROOT / "leagues.json"))["leagues"]
    ids = json.load(open(ROOT / "data" / "players_ids.json"))
    ep = ROOT / "data" / "players_extra.json"
    extra = json.load(open(ep)) if ep.exists() else {}
    heads = {}
    for s in sorted(cfg, reverse=True):  # newest first so current headshots win
        for sc in pool(cfg[s]):
            pid = sc["scorerId"]
            if sc.get("headshotUrl"):
                heads.setdefault(pid, sc["headshotUrl"])
            if pid not in ids and pid not in extra:
                extra[pid] = [sc["name"], sc.get("teamShortName"), sc.get("posShortNames")]
        print(s, len(heads), file=sys.stderr)
    json.dump(heads, open(ROOT / "data" / "headshots.json", "w"), separators=(",", ":"))
    json.dump(extra, open(ep, "w"), indent=0)
    print(len(heads), "headshots,", len(extra), "extra names", file=sys.stderr)


if __name__ == "__main__":
    main()
