# Status (last updated: 2026-10-26, PR #12 merged, next task briefed)

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
| #10 | `fpl blind-score` scorer; GW8 scored (fresh fpl_ep 0.607, rolling_mean_5 0.324) |
| #11 | `fpl.model` LightGBM; lgbm_xp captured fraction 0.793 vs fpl_xp 0.618 (2024-25) |
| #12 | `fpl.planner` + `fpl transfers`, glossary, GW8 blind score recorded |

## Next: validate the planner and feed it better predictions
Full brief: top entry of [task-log.md](task-log.md) ("NEXT TASK"). Summary:
1. Backtest the planner: replay past GWs from `entry_picks` (or a simulated squad), compare the
   planner's transfers with the real ones and with doing nothing, scored on actual points.
2. Make `lgbm_xp` usable live: check whether `ep` can stand in for `xp` (distribution / calibration
   vs `xp`), then use it in `blind-pick` and `transfers`. Without `xp`, `lgbm` is weak (0.404).
3. Horizon-aware predictions (1-6 GW targets), tune LightGBM.
4. Keep the live track record: `fpl blind-pick --gw N` before the deadline (snapshot before
   kickoffs), `fpl blind-score --gw N` after. Also log `fpl transfers` output per GW.

## Later
- Chips (wildcard, free hit, bench boost, triple captain), multi-step transfer plans, real
  selling prices, auto-subs in the planner.
- Lagged ICT / xG / xA / xGI features (xG only from 2022-23).
- Differentials, explorer.
- Fix mid-season-mover team features (see data.md).

## Open questions
- How does vaastav record `xp` on double-gameweek rows? The harness sums it per fixture row.
- vaastav has 2026-27 only to GW6 (checked 2026-10-25); how quickly does it catch up? The adapter
  covers the gap from `element_history`.
- Is `ep_this` really per-GW? It equalled `ep_next` in every spot check.
