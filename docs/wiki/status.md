# Status (last updated: 2026-10-25, LightGBM added)

## Done
| PR | What |
|---|---|
| #1 | License, CI, contributing notes, disclaimer |
| #2 | Historical import from the vaastav dataset (2016-17..2025-26) |
| #3 | Leakage-free per-fixture feature builder (`fpl.features`) |
| #4 | Walk-forward backtest harness + baseline predictors (`fpl.backtest`) |
| #5 | MILP squad/lineup optimizer + captured-fraction metric (`fpl.optimizer`) |
| #8 | Live adapter `fpl.live` + `fpl blind-pick`; GW8 2026-27 picks frozen |
| #10 | `fpl blind-score` scorer |
| (feat/lightgbm) | `fpl.model` LightGBM predictors; lgbm_xp captured fraction 0.793 vs fpl_xp 0.618 (2024-25) |

## Next: run the blind GW8 scorer
Picks are frozen in `data/processed/blind_gw8.json` (rolling_mean_5 and fpl_ep; fresh squad and the
user's own squad). The scorer (`fpl blind-score --gw 8`) is written and tested but uncommitted;
it refuses until all GW8 fixtures are finished (all 10 were open on 2026-10-25).
LightGBM exists (`fpl.model`) but is not wired into `blind-pick` yet: live rows have `ep`, not `xp`.
1. Commit the scorer on a branch, open a PR.
2. Once GW8 is finished: `fpl snapshot`, `fpl history`, `fpl blind-score --gw 8`; record captured
   fraction per predictor (fresh and own squad) in the task log.
3. Then repeat each GW (`fpl blind-pick --gw N` before the deadline, `blind-score` after) to build
   a live track record. Take the snapshot before kickoffs this time (GW8's was taken late).

## Later
- LightGBM follow-ups: tune; horizon 1-6 targets (needed by the planner); add `lgbm_xp` to
  `blind-pick` using `ep`; lagged ICT / xG features.
- Lagged ICT / xG / xA / xGI features (xG only from 2022-23).
- Transfer planner (multi-GW, hits, chips), differentials, explorer.
- Fix mid-season-mover team features (see data.md).

## Open questions
- How does vaastav record `xp` on double-gameweek rows? The harness sums it per fixture row.
- vaastav has 2026-27 only to GW6 (checked 2026-10-25); how quickly does it catch up? The adapter
  covers the gap from `element_history`.
- Is `ep_this` really per-GW? It equalled `ep_next` in every spot check.
