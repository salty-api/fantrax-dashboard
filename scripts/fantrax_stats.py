"""Shared getPlayerStats reader that maps columns by header name (never by position).

Fantrax category views (scoringCategoryType):
  5 = Tracked totals (GP, PTS, REB, AST, ST, BLK, TO)
  1 = Standard, per-game averages (MIN, FGM, FGA, FTM, FTA, 3PTM, ...)
  2 = Extra (3PTA, OREB, DREB, PF, ... plus 2DO / 3D as totals)
League scoring uses PTS, REB, AST, ST, BLK, TO only, so view 5 fully explains FPts.
"""
from fetch_history import call

VIEWS = ("5", "1", "2")


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def fetch_view(lid, cat, timeframe):
    """Return {player_id: {"_tm", "_pos", "<ShortName>": float|None, ...}} for every player in one category view."""
    out, page = {}, 1
    while True:
        req = {"statusOrTeamFilter": "ALL", "maxResultsPerPage": "500", "pageNumber": str(page), "scoringCategoryType": cat, **timeframe}
        try:
            d = call(lid, "getPlayerStats", req, auth=False)
        except RuntimeError as e:  # older private seasons need the login cookie (~/.fantrax_cookie or FANTRAX_COOKIE)
            if "NOT_LOGGED_IN" not in str(e):
                raise
            d = call(lid, "getPlayerStats", req, auth=True)
        names = [h.get("shortName") for h in d["tableHeader"]["cells"]]
        for r in d["statsTable"]:
            c = [x["content"] for x in r["cells"]]
            sc = r["scorer"]
            row = {n: num(v) for n, v in zip(names, c) if n and n not in ("Sta",)}
            row["_tm"], row["_pos"], row["_name"] = sc.get("teamShortName"), sc.get("posShortNames"), sc.get("name")
            row["_icons"] = sc.get("icons", [])
            out[sc["scorerId"]] = row
        if page >= d["paginatedResultSet"]["totalNumPages"]:
            return out
        page += 1


def fetch_all(lid, timeframe):
    """Merge the three views: {pid: {..., 'tot': totals, 'avg': per-game averages}}."""
    v5, v1, v2 = (fetch_view(lid, c, timeframe) for c in VIEWS)
    out = {}
    for pid, a in v5.items():
        g = int(a.get("GP") or 0)
        b, e = v1.get(pid, {}), v2.get(pid, {})
        out[pid] = {
            "rk": int(a["Rk"]) if a.get("Rk") else None, "g": g, "fpts": a.get("FPts"), "fpg": a.get("FP/G"),
            "name": a["_name"], "tm": a["_tm"], "pos": a["_pos"], "icons": a["_icons"],
            "tot": {"pts": a.get("PTS"), "reb": a.get("REB"), "ast": a.get("AST"), "st": a.get("ST"), "blk": a.get("BLK"), "to": a.get("TO"),
                    "dd": e.get("2DO"), "td": e.get("3D")},
            "avg": {"min": b.get("MIN"), "fgm": b.get("FGM"), "fga": b.get("FGA"), "ftm": b.get("FTM"), "fta": b.get("FTA"),
                    "tpm": b.get("3PTM"), "tpa": e.get("3PTA"), "oreb": e.get("OREB"), "dreb": e.get("DREB"), "pf": e.get("PF")},
        }
    return out
