# Big Baller Brand - Fantasy Basketball History

League history dashboard for the Fantrax league, served by GitHub Pages from `docs/` at fantrax.whohashim.com.

- `leagues.json` - season to Fantrax league ID
- `scripts/fetch_history.py` - pulls standings and matchups into `data/` (older seasons need a Fantrax login cookie in `~/.fantrax_cookie` or `FANTRAX_COOKIE`; never commit it)
- `data/owners.csv` - maps each season's team name to an owner; new names are added with `confirmed=0`
- `scripts/build_dashboard.py` + `scripts/template.html` - build `docs/index.html`
- `docs/logos/` - owner logos (from the 2025-26 season)

Refresh: `python3 -I scripts/fetch_history.py && python3 -I scripts/build_dashboard.py`, then commit and push.
