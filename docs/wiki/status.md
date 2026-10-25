# Status (last updated: 2026-10-24, after PR #5)

## Done
| PR | What |
|---|---|
| #1 | License, CI, contributing notes, disclaimer |
| #2 | Historical import from the vaastav dataset (2016-17..2025-26) |
| #3 | Leakage-free per-fixture feature builder (`fpl.features`) |
| #4 | Walk-forward backtest harness + baseline predictors (`fpl.backtest`) |
| #5 | MILP squad/lineup optimizer + captured-fraction metric (`fpl.optimizer`) | |

## Next: live-data adapter and a blind GW8 (2026-27) test
Goal: with only data up to GW7 of 2026-27, predict and pick the best lineup for GW8 (GW8 was in
progress on 2026-10-24), then compare with the hindsight-optimal lineup once results are in. Do not
look at GW8 results while building.

Needed:
1. Live 2026-27 data in DuckDB. The live tables (`snapshots`, `player_snapshots`,
   `fixture_snapshots`, `element_history`, `entry_*`) are **empty locally**. Run `fpl snapshot` and
   `fpl history`, or check whether vaastav already has 2026-27 (`fpl import-history --from 2026-27`).
2. An adapter producing the same feature rows as `build_features` for the upcoming GW8 fixtures,
   from GW1-7 of 2026-27 plus prior seasons (cross-season key = `code`). Upcoming fixtures come
   from `fixture_snapshots`. These rows have no target.
3. Predictors: vaastav-style `xp` does not exist for live rows (the live source is `ep_next` /
   `ep_this` from bootstrap-static); the rolling mean works from features.
4. Pick with `optimize_squad` (fresh squad) and `pick_lineup` (the user's actual squad via
   `fpl entry`), then score against the hindsight ceiling after GW8 finishes.

## Later
- LightGBM predictor (optional extra); report with and without `xp` as a feature.
- Lagged ICT / xG / xA / xGI features (xG only from 2022-23).
- Transfer planner (multi-GW, hits, chips), differentials, explorer.
- Fix mid-season-mover team features (see data.md).

## Open questions
- How does vaastav record `xp` on double-gameweek rows? The harness sums it per fixture row.
- Does vaastav already have 2026-27, and how current is it?
