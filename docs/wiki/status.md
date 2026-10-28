# Status (last updated: 2026-10-28, real free-transfer / chip history on branch feat/real-replay)

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
| #14 | `fpl.planbacktest` + `fpl backtest-planner`; zero-`xp` rounds fixed; `ep` as `xp` for `lgbm_xp` live |
| #15 | `fpl blind-score --all` |
| #18 | LightGBM tuning sweep: defaults kept |
| (branch feat/xp-timing) | `xp` timing investigation: `xp` leaks; `xp_prev` leak-free proxy |
| (branch feat/real-replay) | `fpl.replay` + `fpl replay`: real free-transfer / chip history; `fpl transfers` derives `--free` |
| #17 | `fpl.horizon` per-horizon models (better MAE, no planner gain; opt-in); LightGBM tuning sweep: defaults kept |
| #16 | Planner backtest: selling price + auto-subs, sell-price budget fix; ICT features (no gain) |

How to produce a GW's predictions / lineup / transfers: [running-predictions.md](running-predictions.md).
(A `fpl lineup` / `fpl squad` CLI command would replace the Python snippets there; not built.)

## Next: chips in the planner (start here)
Full brief: top entry of [task-log.md](task-log.md) ("NEXT TASK"). Summary:
1. Model chips (wildcard, free hit, bench boost, triple captain) in the planner; `fpl.replay.chips_left`
   gives availability (bench boost is the only first-half chip left for the 2026-27 entry).
   **`xp` timing was investigated 2026-10-27: vaastav `xp` very likely partly leaks the GW result**
   (task-log). Treat `fpl_xp` / `lgbm_xp` / planner absolute numbers as optimistic.
Standing chores (do whenever a GW passes):
- **After GW9 finishes:** `fpl snapshot`, `fpl blind-score --gw 9`, `fpl blind-score --all`, record the
  numbers (GW9 snapshot / blind-pick / transfers were done 2026-10-26; GW9 picks predate the ICT features).
- Log `ep` every GW: `fpl snapshot` before each deadline, `fpl blind-pick --gw N --model` (before
  kickoffs), `fpl transfers`, then `fpl blind-score --gw N`. No `ep` history exists yet, so the
  `ep`-as-`xp` decision rests on one gameweek (GW8).
Still open from the planner-realism task (selling price and auto-subs DONE, small effect):
verifying `xp` timing (absolute backtest points of 74-83/GW are optimistic). Real free-transfer/chip
history and the squad replay are done (2026-10-28).

## Later
- Chips (wildcard, free hit, bench boost, triple captain), multi-step transfer plans, live selling
  prices from `entry` data (the backtest already models them).
- Lagged xG / xA / xGI features (xG only from 2022-23). ICT done 2026-10-27: no gain.
- Differentials, explorer.
- Fix mid-season-mover team features (see data.md).

## Open questions
- How does vaastav record `xp` on double-gameweek rows? The harness sums it per fixture row.
- vaastav has 2026-27 only to GW6 (checked 2026-10-25); how quickly does it catch up? The adapter
  covers the gap from `element_history`.
- Is `ep_this` really per-GW? It equalled `ep_next` in every spot check.
- How much of `xp`'s backtest value is leak? Live `ep` vs backtest `xp` are close over 2 GWs; need more GWs.
- Does `ep` as `xp` hold up beyond GW8? One gameweek: lgbm_xp(ep) 0.828 vs fpl_ep 0.566.
