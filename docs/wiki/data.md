# Data

DuckDB file `data/processed/fpl.duckdb` (gitignored). Do not commit anything under `data/`.

## Tables
- Historical (vaastav, 2016-17..2025-26): `hist_teams`; `hist_players` (`code` is the cross-season
  key, plus `position` and `team_id`, the end-of-season team); `hist_player_gw` (253,831 rows, one
  per player per fixture; `value` is the price in tenths at that fixture; `xp` is FPL's own
  expected points).
- Live (official API): `snapshots`, `player_snapshots`, `team_snapshots`, `event_snapshots`,
  `fixture_snapshots`, `element_history`, `entry_gameweeks`, `entry_picks`, `entry_transfers`.
  **As of 2026-10-24 all live tables are empty locally.** Populate them with `fpl snapshot`,
  `fpl history` and `fpl entry` (the entry id comes from env var `FPL_ENTRY_ID`).

## Gotchas
- `element_id` / `team_id` are only stable within a season; the cross-season key is `hist_players.code`.
- DGW = two rows in the same round; blank = no row; 0-minute rows exist when the team played.
- `expected_*` and `starts` exist only from 2022-23; `xp` from 2020-21; no xG before 2022-23.
- No per-GW fixture difficulty in `hist_player_gw`.
- 2019-20 `round` runs to 47 (COVID); always order GWs by earliest kickoff, not `round`.
- A player's team is end-of-season, so mid-season movers get wrong team-form features and a
  slightly wrong club in the optimizer's 3-per-club rule.
