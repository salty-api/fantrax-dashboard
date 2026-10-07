# Big Baller Brand - Fantasy Basketball History

League history dashboard for the Fantrax league, served by GitHub Pages from `docs/` at fantrax.whohashim.com.

- `leagues.json` - season to Fantrax league ID
- `scripts/fetch_history.py` - pulls standings and matchups into `data/` (older seasons need a Fantrax login cookie in `~/.fantrax_cookie` or `FANTRAX_COOKIE`; never commit it)
- `data/owners.csv` - maps each season's team name to an owner; new names are added with `confirmed=0`
- `scripts/build_dashboard.py` + `scripts/template.html` - build `docs/index.html`
- `docs/logos/` - owner logos (from the 2025-26 season)

## Automatic weekly refresh

`.github/workflows/refresh.yml` runs every Monday 7am PT (and on demand from the Actions tab). It re-fetches only the
**current season** (`"current"` in `leagues.json`), rebuilds the site and share cards, and commits if anything changed.

- **Old seasons are protected:** `--current` never rewrites other seasons, and the build refuses to publish if a finished season has lost its scores.
- **Team names:** a renamed team (same Fantrax team ID) inherits its owner automatically. A brand-new name that can't be matched makes the run fail and email you: add the row to `data/owners.csv` (owner name, `confirmed=1`) and re-run the workflow.
- **New season each October:** Fantrax creates a new league ID. Add it to `leagues.json` under `leagues` and change `current`.
- **Share cards** are only redrawn when a player's name, team, or owner history changes (`data/cards.json`), to keep the repo small. `python3 scripts/build_share.py --force` redraws all (about 5 MB added to history).

Manual refresh: run the same steps as the workflow locally. Older private seasons need a Fantrax cookie in `~/.fantrax_cookie` (only for backfilling; the weekly job doesn't need it).
