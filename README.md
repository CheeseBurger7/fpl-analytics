# FPL Analytics Platform

[![CI](https://github.com/CheeseBurger7/fpl-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/CheeseBurger7/fpl-analytics/actions/workflows/ci.yml)

Analytical platform for Fantasy Premier League team selection.

> **Disclaimer:** this is an unofficial, independent project. It is not affiliated with,
> endorsed by, or connected to the Premier League or Fantasy Premier League. It reads the
> publicly available FPL API at a conservative request rate; please keep it that way if you
> fork it. No credentials are needed or stored. Predictions are for research and entertainment
> and come with no guarantee of results.

## Core jobs
1. **Squad optimizer**: best 15 + starting XI within budget.
2. **Transfer planner**: multi-gameweek, free transfers, -4 hits, chip timing.
3. **Captain and differential picks**.
4. **Player explorer**: compare players, fixtures, xG/xA, form, price changes.
5. **Historical analysis**: retrospective on past picks, season-over-season trends.

Status: the data layer (API ingestion and point-in-time DuckDB snapshots) is done. The model,
optimizer and planner are next.

## Quick start
```
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

fpl snapshot                    # freeze bootstrap-static + fixtures into DuckDB (+ Parquet)
fpl history                     # per-fixture history for every player (~670 requests)
fpl entry <your-entry-id>       # your picks, transfers and chips; or set FPL_ENTRY_ID
```
Data lands in `data/processed/fpl.duckdb` (gitignored).

## Layout
- `src/fpl/`: package code (`api`, `store`, `ingest`, `cli`)
- `data/raw`, `data/processed`: source and derived data (gitignored)
- `notebooks/`, `tests/`, `docs/`

## Contributing
Contributions are welcome.

1. Fork the repo and create a short-lived branch (`feat/...`, `fix/...`).
2. Set up as in Quick start, then make your change.
3. Before opening a PR, run:
   ```
   ruff check .
   pytest
   ```
   CI runs the same checks on Python 3.11 and 3.13.
4. Add tests for new behaviour. API calls are mocked with `httpx.MockTransport`; tests must not
   hit the live FPL API.
5. Open a PR against `main` describing what changed and why. For larger ideas, open an issue
   first.

## License
[MIT](LICENSE)
