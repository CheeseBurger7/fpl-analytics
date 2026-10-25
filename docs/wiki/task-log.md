# Task log (newest first)

## 2026-10-25: Live-data adapter and frozen blind GW8 picks (branch feat/live-adapter)
- Data: vaastav already has 2026-27 but only to GW6 (3,883 rows). Imported it, then ran
  `fpl snapshot` (snapshot 1, 669 players, 380 fixtures, taken 2026-10-25 02:43 with GW8 current)
  and `fpl history` (5,220 `element_history` rows, GW1-7) and `fpl entry` (8 GWs of picks).
- Added `fpl.live`: `live_features(con, season, gw)` shadows `hist_*` with TEMP tables (adds
  GW7 from `element_history`, plus target-less rows for GW8 fixtures) and runs the unchanged
  `feature_sql`; `predictions` (rolling_mean_5, FPL `ep`), `player_pool`. New CLI
  `fpl blind-pick --gw N` writes `data/processed/blind_gw<N>.json` (gitignored).
- GW8 result: 669 player-fixture rows, 662 with >= 5 prior fixtures. Frozen predicted XI points
  (fresh squad): rolling_mean_5 87.6, fpl_ep 92.0; user's own squad: 70.4 / 65.3.
- Tests: `tests/test_live.py` (56 tests pass, ruff clean).
- Caveats: the snapshot was taken after GW8 kickoffs began, so it is not a pre-deadline freeze;
  only price, club, position and `ep_this` were read from it (not its running totals). No GW8
  actuals were looked at. `ep_this` equalled `ep_next` for every player spot-checked.
- Still to do: after GW8 finishes, `fpl history`, then score the frozen picks against the
  hindsight ceiling (not built yet).

## 2026-10-24: Squad/lineup optimizer and captured-fraction metric (PR #5, merged)
- Added `fpl.optimizer` (scipy milp), `CapturedFractionHook`, `fpl backtest --captured` and the
  `optimize` extra.
- 2024-25, step 0, captured fraction (average ceiling 151.3 pts/GW): constant_2 0.102,
  rolling_mean_5 0.371, career_mean 0.354, fpl_xp 0.618 (93.2 pts/GW achieved).
- Caveats: fresh squad each GW, no auto-subs, end-of-season club.

## 2026-10-24: Walk-forward backtest harness (PR #4)
- Added `fpl.backtest` and `fpl backtest`. Baselines on 2023-24 / 2024-25 (fixture MAE, Spearman):
  constant_2 1.95/1.94, 0.09/0.10; rolling_mean_5 1.04/1.10, 0.67/0.69; career_mean 1.27/1.29,
  0.48/0.51; fpl_xp 0.86/0.93, 0.75/0.76. `fpl_xp` is the number to beat.
- Caveat: `xp` is summed across DGW rows; vaastav's DGW semantics are unverified.

## Earlier
- PR #3 leakage-free feature builder; PR #2 vaastav history import (2016-17..2025-26);
  PR #1 license, CI and docs.
