#!/usr/bin/env python3
"""Save each owner's Fantrax team logo for the current season to docs/logos/<season>/<owner>.webp.

Each season gets its own folder so a team can have a new logo every year (the site falls back to the
default docs/logos/<owner>.webp for seasons without one). A logo is only re-downloaded when its Fantrax
URL changes (tracked in data/logo_urls.json), so a hand-placed file is never overwritten otherwise.
Nice-to-have: never breaks the refresh.
"""
import csv, json, re, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import ROOT, call

D, DOCS = ROOT / "data", ROOT / "docs"


def slug(o):
    return re.sub(r"[^a-z0-9]+", "-", o.lower()).strip("-")


def main():
    cfg = json.load(open(ROOT / "leagues.json"))
    season = cfg["current"]
    own = {r["team_id"]: r["owner"] for r in csv.DictReader(open(D / "owners.csv")) if r["season"] == season}
    info = call(cfg["leagues"][season], "getStandings", {"view": "REGULAR_SEASON"}, auth=False)["fantasyTeamInfo"]
    seen_path = D / "logo_urls.json"
    seen = json.load(open(seen_path)) if seen_path.exists() else {}
    out = DOCS / "logos" / season
    out.mkdir(parents=True, exist_ok=True)
    changed = 0
    for tid, t in info.items():
        o, url = own.get(tid), t.get("logoUrl512")
        if not o or not url:
            continue
        key, dst = f"{season}|{o}", out / f"{slug(o)}.webp"
        if seen.get(key) == url and dst.exists():
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                dst.write_bytes(r.read())
        except Exception as e:
            print(f"{o}: logo skipped ({e})")
            continue
        seen[key] = url
        changed += 1
        print(f"{season} {o}: saved {dst.name}")
    json.dump(seen, open(seen_path, "w"), indent=1, sort_keys=True)
    print(f"{changed} logos updated")


if __name__ == "__main__":
    main()
