# Status (last updated: 2026-10-29, open-questions pass, `xp` DGW fix, odds ingest, on branch feat/xp-fix-odds)

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
| (branch feat/chips-planner) | Chips in the planner: 3xc / bboost / freehit / wildcard in `plan_transfers`, `fpl transfers --chips`, chip policy in the planner backtest (+8-11 pts per chip; timing no better than early) |
| (not merged) | Component models + lagged goal/assist/xG rates tried and reverted: no gain vs `lgbm` |
| #17 | `fpl.horizon` per-horizon models (better MAE, no planner gain; opt-in); LightGBM tuning sweep: defaults kept |
| #16 | Planner backtest: selling price + auto-subs, sell-price budget fix; ICT features (no gain) |

How to produce a GW's predictions / lineup / transfers: [running-predictions.md](running-predictions.md).
(A `fpl lineup` / `fpl squad` CLI command would replace the Python snippets there; not built.)

## Next: odds-derived features + backtest (start here)
Full brief: the "NEXT TASK" entry in [task-log.md](task-log.md); the older `ep` / chip-timing brief is
the "Backlog" entry below it. Summary:
1. Chips are modelled (planner + `fpl transfers --chips` + backtest policy). Open: fixture-aware
   later-GW predictions so chip timing can beat "play early"; free hit / wildcard in the backtest.
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
- **Match odds as fixture-strength features:** ingested 2026-10-29 (`fpl import-odds`, table `match_odds`,
  11 seasons). Next: implied win / draw probabilities, expected goals from Over/Under + handicap,
  implied clean-sheet probability as features, backtest vs `lgbm`. Open: odds for upcoming GWs.
- Multi-step transfer plans, live selling prices from `entry` data (the backtest already models them).
- Lagged goal / assist / xG features and component models: tried 2026-10-28, no gain, code reverted.
  ICT done 2026-10-27: no gain. Untried: availability news as a feature (needs a stored history of
  `chance_of_playing`; snapshots have it from now on), RF / Ridge baselines, ensemble.
- Differentials, explorer.
- Fix mid-season-mover team features (see data.md).
- Tried 2026-10-29, no gain, reverted: clean-sheet and venue-split (home / away) opponent features.
  The model is limited by missing news, not by fixture context; a fixture-difficulty rating from
  the FPL `fixtures` difficulty field (`fixture_snapshots`) is untried.

## Open questions
Answered 2026-10-29 (task log): DGW `xp` is the round total repeated per fixture row (harness fixed);
`ep_this` is `ep_next` with this-round availability, not a separate forecast; vaastav lags ~2.5 weeks in
batches (GW6 on 2026-10-29).
- How much of `xp`'s backtest value is leak? After the DGW fix `lgbm_xp` captures 0.87-0.88 vs 0.38-0.42
  leak-free (`lgbm`, `lgbm_xp_prev`). Live `ep` vs backtest `xp` are close over 2 GWs; needs more GWs of `ep`.
- (Defaults now leak-free `lgbm`, 2026-10-29.) Does `ep` as `xp` hold up beyond GW8? One gameweek: lgbm_xp(ep) 0.828 vs fpl_ep 0.566. Needs the `ep`
  history from the standing chores.
