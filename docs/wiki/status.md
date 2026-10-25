# Status (last updated: 2026-10-25, after PR #8)

## Done
| PR | What |
|---|---|
| #1 | License, CI, contributing notes, disclaimer |
| #2 | Historical import from the vaastav dataset (2016-17..2025-26) |
| #3 | Leakage-free per-fixture feature builder (`fpl.features`) |
| #4 | Walk-forward backtest harness + baseline predictors (`fpl.backtest`) |
| #5 | MILP squad/lineup optimizer + captured-fraction metric (`fpl.optimizer`) |
| #8 | Live adapter `fpl.live` + `fpl blind-pick`; GW8 2026-27 picks frozen |

## Next: score the blind GW8 picks
Picks are frozen in `data/processed/blind_gw8.json` (predictors rolling_mean_5 and fpl_ep; fresh
squad and the user's own squad). The adapter is merged (PR #8); start the scorer from `main`.
No trained model exists yet: only rolling_mean_5 and fpl_ep
(LightGBM is under Later). GW8 was still in progress on 2026-10-25, so wait for it to finish.
1. Once GW8 is finished: `fpl snapshot` + `fpl history`, then read GW8 actuals from `element_history`.
2. Add a scorer: `score_selection` of each frozen XI/captain on actual points, versus the hindsight
   ceiling (`optimize_squad` on actuals, same pool and budget). Report captured fraction per predictor.
3. Then repeat each GW (`fpl blind-pick --gw N`) to build a live track record.

## Later
- LightGBM predictor (optional extra); report with and without `xp` as a feature.
- Lagged ICT / xG / xA / xGI features (xG only from 2022-23).
- Transfer planner (multi-GW, hits, chips), differentials, explorer.
- Fix mid-season-mover team features (see data.md).

## Open questions
- How does vaastav record `xp` on double-gameweek rows? The harness sums it per fixture row.
- vaastav has 2026-27 only to GW6 (checked 2026-10-25); how quickly does it catch up? The adapter
  covers the gap from `element_history`.
- Is `ep_this` really per-GW? It equalled `ep_next` in every spot check.
