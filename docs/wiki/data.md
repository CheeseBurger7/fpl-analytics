# Data

DuckDB file `data/processed/fpl.duckdb` (gitignored). Do not commit anything under `data/`.

## Tables
- Historical (vaastav, 2016-17..2025-26): `hist_teams`; `hist_players` (`code` is the cross-season
  key, plus `position` and `team_id`, the end-of-season team); `hist_player_gw` (253,831 rows, one
  per player per fixture; `value` is the price in tenths at that fixture; `xp` is FPL's own
  expected points).
- Live (official API): `snapshots`, `player_snapshots`, `team_snapshots`, `event_snapshots`,
  `fixture_snapshots`, `element_history`, `entry_gameweeks`, `entry_picks`, `entry_transfers`.
  As of 2026-10-25 they are populated (snapshot 1, `element_history` GW1-7+, entry picks).
  Refresh with `fpl snapshot`, `fpl history` and `fpl entry` (entry id from env var `FPL_ENTRY_ID`).
  Snapshot running totals (`minutes`, `total_points`...) include the current GW: never use them
  as features. vaastav 2026-27 imported through GW6 only.

- Odds: `match_odds` (football-data.co.uk): one row per match, 2016-17..2026-27, with `home_team_id` /
  `away_team_id` = `hist_teams.team_id` of the season. Refresh with `fpl import-odds` (always re-fetches
  the current season). Not available for unplayed GWs yet (see task log).

## Gotchas
- `element_id` / `team_id` are only stable within a season; the cross-season key is `hist_players.code`.
- DGW = two rows in the same round; blank = no row; 0-minute rows exist when the team played.
- **`xp` missing = 0 for whole rounds** in vaastav (2025-26: 27 of 38 rounds; 2026-27: GW2, GW6;
  also 2023-24 GW26, 2024-25 GW22/32/34, a few earlier). `load_dataset` turns an all-zero round into
  NULL; raw `hist_player_gw.xp` still has the zeros. `xp` in GW1 is poor (corr with points 0.4).
- Live `ep_next` exists only in snapshots (3 so far, all GW9); there is no per-GW `ep` history.
- `expected_*` and `starts` exist only from 2022-23; `xp` from 2020-21; no xG before 2022-23.
- No per-GW fixture difficulty in `hist_player_gw`.
- 2019-20 `round` runs to 47 (COVID); always order GWs by earliest kickoff, not `round`.
- A player's team is end-of-season, so mid-season movers get wrong team-form features and a
  slightly wrong club in the optimizer's 3-per-club rule.

- **vaastav `xp` on double gameweeks** is the round total repeated on both fixture rows (never summed
  per row; `load_dataset` divides by the row count). vaastav 2026-27 arrives in batches ~2.5 weeks late
  (GW6 on 2026-10-29). Live `ep_this` = `ep_next` scaled by this round's `chance_of_playing`; use `ep_next`.
- **`ep_next` = `form` x availability** (92% exact equality, rest scaled by `chance_of_playing`): FPL's
  expected points carry no fixture information. Its only new information over our features is
  availability news.
- **vaastav `xp` timing:** appears recorded after the gameweek (a haul is already in `xp_g`). Use
  `xp_prev` (previous known `xp`) when a leak-free forecast input is needed.
