#!/usr/bin/env python3
"""Fetch each player's real headshot URL from Fantrax (suffix varies per player).
Writes data/headshots.json: player_id -> url. Uses the full player pool of the current league.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import call, ROOT


def main():
    lid = json.load(open(ROOT / "leagues.json"))["leagues"]
    lid = lid[sorted(lid)[-2]]  # most recent completed season (public)
    out, page = {}, 1
    while True:
        d = call(lid, "getPlayerStats", {"statusOrTeamFilter": "ALL", "maxResultsPerPage": "500",
                                         "pageNumber": str(page), "timeframeTypeCode": "YEAR_TO_DATE"}, auth=False)
        for r in d["statsTable"]:
            sc = r["scorer"]
            if sc.get("headshotUrl"):
                out[sc["scorerId"]] = sc["headshotUrl"]
        if page >= d["paginatedResultSet"]["totalNumPages"]:
            break
        page += 1
    json.dump(out, open(ROOT / "data" / "headshots.json", "w"), separators=(",", ":"))
    print(len(out), "headshots", file=sys.stderr)


if __name__ == "__main__":
    main()
