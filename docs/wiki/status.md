# Status (last updated: 2026-11-27, GW12 transfers + frozen; earlier: 2026-11-25, GW11 scored; earlier: 2026-11-20, GW11 rerun + frozen; earlier: 2026-11-09 GW10 scored; earlier: 2026-11-05 GW10 frozen, Mbeumo transfer chosen; earlier: 2026-11-03 GW9 scored; earlier: 2026-10-29 open-questions pass, `xp` DGW fix, odds ingest)

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
| (this PR) | `blind-score` prints per-player MAE / Spearman and scores the hand-added `manual` team as predictor `manual` (GW10: 48 / 71 = 0.676); tests added; GW11 predictions run 2026-11-09 (see model-scoreboard.md ledger) |
| (this PR) | New [model-scoreboard.md](model-scoreboard.md): per-model live scores and transfer ledger; `blind-pick --model` now also freezes plain `lgbm` (was missing: GW8-10 have no live `lgbm` score); GW10 scored 2026-11-09 (fresh rolling_mean_5 0.547, fpl_ep 0.466, lgbm_xp(ep) 0.399; user's real team 48 pts, 18 on bench); 3-GW means in the standing chores |
| #29 | GW10 frozen (`blind_gw10.json`, snapshot 12) and transfer decision logged: Gibbs-White -> Mbeumo (`lgbm` +5.0 over GW10-12) |
| #27 | GW9 scored (fresh rolling_mean_5 0.446, fpl_ep 0.554, lgbm_xp(ep) 0.454; entry 0.784 / 0.784 / 0.886); task-log.md reduced to next task + improvements |
| #11 | `fpl.model` LightGBM; lgbm_xp captured fraction 0.793 vs fpl_xp 0.618 (2024-25) |
| #12 | `fpl.planner` + `fpl transfers`, glossary, GW8 blind score recorded |
| #14 | `fpl.planbacktest` + `fpl backtest-planner`; zero-`xp` rounds fixed; `ep` as `xp` for `lgbm_xp` live |
| #15 | `fpl blind-score --all` |
| #18 | LightGBM tuning sweep: defaults kept |
| (branch feat/xp-timing) | `xp` timing investigation: `xp` leaks; `xp_prev` leak-free proxy |
| (branch feat/real-replay) | `fpl.replay` + `fpl replay`: real free-transfer / chip history; `fpl transfers` derives `--free` |
| (branch feat/chips-planner) | Chips in the planner: 3xc / bboost / freehit / wildcard in `plan_transfers`, `fpl transfers --chips`, chip policy in the planner backtest (+8-11 pts per chip; timing no better than early) |
| (not merged) | Odds-derived features (1X2, xG, clean sheet): captured 0.400 -> 0.415, noise, reverted |
| (not merged) | Component models + lagged goal/assist/xG rates tried and reverted: no gain vs `lgbm` |
| #17 | `fpl.horizon` per-horizon models (better MAE, no planner gain; opt-in); LightGBM tuning sweep: defaults kept |
| #16 | Planner backtest: selling price + auto-subs, sell-price budget fix; ICT features (no gain) |

How to produce a GW's predictions / lineup / transfers: [running-predictions.md](running-predictions.md).
(A `fpl lineup` / `fpl squad` CLI command would replace the Python snippets there; not built.)

## Next: collect `ep`, then news / fixture-aware chip timing (start here)
Odds features were tried 2026-10-29: captured 0.400 -> 0.415, inside noise, not adopted (decisions.md).
Next task and improvement ideas: [task-log.md](task-log.md). Summary:
1. Chips are modelled (planner + `fpl transfers --chips` + backtest policies). Free hit / wildcard are in
   the season backtest (`--swap-chips`, 2026-10-30): no clear gain over `planner` (+20 / -7 / +3 mean
   points per season for `--chip-min` 0 / 3 / 6). Open: fixture-aware later-GW predictions so chip timing
   can beat "play early"; gain net of normal transfers; selling-price-aware chip squads.
   **`xp` timing was investigated 2026-10-27: vaastav `xp` very likely partly leaks the GW result**
   (decisions.md). Treat `fpl_xp` / `lgbm_xp` / planner absolute numbers as optimistic.
Standing chores (do whenever a GW passes):
- GW9 scored 2026-11-03: fresh `lgbm_xp(ep)` 0.454 vs `fpl_ep` 0.554 vs rolling_mean_5 0.446;
  entry 0.886 / 0.784 / 0.784. Next: the same for GW10 (freeze with `--model` before kickoff, then
  `fpl snapshot`, `fpl blind-score --gw N`, `--all`). Plain `lgbm` is not in the GW9 file.
- GW10 lineup run 2026-11-06 (snapshot 13, GW9 picks, bank 1.7m, no transfer): lgbm 3-5-2, captain Haaland
  (5.62 xp); lgbm_xp(ep) picks Evanilson (5.54) with Haaland 4.44. Frozen 2026-11-06 (`blind-pick --gw 10 --model`, snapshot 13); the user's real team is stored under a
  hand-added `manual` key in `blind_gw10.json` (3-4-3: Raya; Konsa, Calafiori, Van Hecke; Palmer, Rogers,
  Tavernier, Mbeumo; Haaland (C), Calvert-Lewin, Evanilson; bench Muharemović, Davis, Gomez, Bentley).
  `blind-score` reads `manual` since 2026-11-09. `blind-pick` overwrites an existing file: check first.
  Rerun after the user's real transfer (Gibbs-White -> Mbeumo): lgbm 3-5-2 with Mbeumo 5.22 (captain
  Haaland 5.62); lgbm_xp Mbeumo 6.84 (captain Mbeumo). Playing Calvert-Lewin (3-4-3) costs 0.3-0.75 pts.
  Tip: `python -X utf8` is needed to print names like Muharemović on Windows (cp1252 otherwise).
- **GW10 scored 2026-11-09** (snapshot 14, `fpl history` first; hindsight ceiling 148): fresh rolling_mean_5
  81 = 0.547, fpl_ep 69 = 0.466, lgbm_xp(ep) 59 = 0.399. Means over GW8-10 (fresh): rolling_mean_5 0.439
  (n=3), fpl_ep 0.542 (n=3), lgbm_xp(ep) 0.426 (n=2): `ep`-as-`xp` is not beating `fpl_ep`. Per-player
  GW10 (players predicted >= 1.0): MAE 2.13 / 2.22 / 2.18, Spearman 0.327 / 0.317 / 0.245
  (rolling_mean_5 / fpl_ep / lgbm_xp). No `entry` rows for GW10: the frozen file's `entry` is the GW9
  squad; the `manual` team scores 48 / 71 = 0.676. Plain `lgbm` is not in the file.
- **GW11 rerun + frozen 2026-11-20 (snapshot 16, `blind_gw11.json`, all four predictors incl. `lgbm`):**
  same state (GW10 squad, bank 1.6m, 1 free, bench boost). All four models still pick Calvert-Lewin ->
  N.Jackson as the best single transfer (`lgbm` +5.9 over GW11-14, +1.8 for GW11); no hit worth it for
  `lgbm` (+0.3). `fpl_ep` / `lgbm_xp` now like a Haaland hit (`ep_next` 4.0, no injury flag: form only).
  `lgbm` XI after the transfer: Raya; Calafiori, Konsa, Van Hecke; Tavernier, Rogers, Palmer, Mbeumo;
  N.Jackson, Evanilson, Haaland; captain Palmer 5.52 (Haaland 5.3); 53.7 pts. Others captain N.Jackson
  (`fpl_ep`, `lgbm_xp`) or Konsa (`rolling_mean_5`). Add the real team as `manual` once chosen.
  Haaland check (2026-11-20): 2, 2 pts in GW9-10, 9 goals on 7.06 xG, 78.8% owned; fixtures GW11-14 FUL(h,2)
  ARS(a,5) LEE(h,3) BRE(a,4). Single-transfer gains GW11-14 (XI/captain aware): Haaland out is +1.9 (Isak) for
  `lgbm`, +29.2 / +10.4 (N.Jackson) for `fpl_ep` / `rolling_mean_5`, but it competes with Calvert-Lewin ->
  N.Jackson (+5.9 / +33.2 / +18.4). Advice: keep Haaland for FUL at home, revisit before GW12 (Haaland -> Isak).
  Other candidates: Gomez -> Groß +5.0, Calafiori / Muharemović -> Tarkowski +4.3 (`lgbm`); Davis -> Vuskovic
  +13.6 (`rolling_mean_5`; also helps the bench boost).
  **User's GW11 choice:** no transfer (2 free in GW12), captain Haaland, Palmer + Mbeumo start. Stored as
  `manual` in `blind_gw11.json`: 4-4-2 Raya; Konsa, Van Hecke, Calafiori, Muharemović; Tavernier, Rogers,
  Palmer, Mbeumo; Haaland (C), Evanilson (V); bench Gomez, Calvert-Lewin, Davis, Bentley.
  Tavernier -> Groß checked 2026-11-20 (GW11-14 gain): `lgbm` +3.0, `fpl_ep` -5.2, `rolling_mean_5` -3.2,
  `lgbm_xp` -5.8: not recommended. Calvert-Lewin -> N.Jackson stays the GW12 priority (+5.9 / +33.2 / +18.4 / +32.4).
- **GW11 scored 2026-11-25** (snapshot 17, `fpl history`, `fpl entry`; ceiling 154): fresh rolling_mean_5
  27 = 0.175, fpl_ep 55 = 0.357, lgbm 40 = 0.260 (first live `lgbm`), lgbm_xp(ep) 58 = 0.377. Means (fresh):
  rolling_mean_5 0.373 (n=4), fpl_ep 0.496 (n=4), lgbm_xp(ep) 0.410 (n=3), lgbm 0.260 (n=1). Per-player:
  `lgbm` best (MAE 2.12, Spearman 0.328). User 44 pts (= FPL), 44 / 54 = 0.815; real XI was 3-4-3 with
  Calvert-Lewin (9) starting, Mbeumo vice, Muharemović benched: the hand-added `manual` key was wrong
  (ids 301 / 359 are a different Palmer / Gomez) and was rebuilt from `entry_picks`. Holding Calvert-Lewin
  beat N.Jackson by 7 in GW11; Mbeumo vs Gibbs-White is -4 after two GWs.
- **GW12 plan 2026-11-25** (snapshot 17, 2 free, bank 1.6m): models split (`lgbm` Raya + Calafiori -> A.Becker +
  Gabriel +10.5; `ep` / form models Mbeumo -> Wirtz). Recommended Raya + Mbeumo -> A.Becker + Wirtz: positive
  under all four (+6.4 / +37.6 / +14.0 / +33.6), ~2.6m left, fixes Raya's injury (50%). Details:
  model-scoreboard.md section 4. **Done 2026-11-27:** user made Raya -> A.Becker, Mbeumo -> Wirtz (both free);
  GW12 frozen (snapshot 20, `blind_gw12.json`, all four predictors). After the deadline: rebuild `manual` from
  `entry_picks` (`fpl entry`), then after GW12 `fpl snapshot`, `fpl history`, `fpl blind-score --gw 12`.
- GW11 run 2026-11-09 (snapshot 15): squad = GW10
  picks, bank 1.6m, 1 free, bench boost left, no blank / double GWs in the schedule. Calvert-Lewin ->
  N.Jackson is the best single transfer for `lgbm` (+5.9), `fpl_ep` and `rolling_mean_5`; no hit is worth
  it (`lgbm` 2 transfers +0.3 net). Details and captains: model-scoreboard.md section 4. Freeze with
  `fpl blind-pick --gw 11 --model` close to the deadline (fresh injury news), after `fpl snapshot`. User's real GW10 team
  (`manual`): 48 pts (matches the FPL total), 18 on the bench (Muharemović 10, Gomez 9, Davis -1);
  Haaland (C) 2 pts, Mbeumo 2, Calvert-Lewin 2, Palmer 2; Evanilson 9, Konsa 8. Overall rank 1.93m.
- Log `ep` every GW: `fpl snapshot` before each deadline, `fpl blind-pick --gw N --model` (before
  kickoffs; `--model` freezes `lgbm` + `lgbm_xp(ep)` since 2026-11-09, GW8-10 files have no `lgbm`), `fpl transfers`, then `fpl blind-score --gw N`. No `ep` history exists yet, so the
  `ep`-as-`xp` decision rests on one gameweek (GW8).
Still open from the planner-realism task (selling price and auto-subs DONE, small effect):
verifying `xp` timing (absolute backtest points of 74-83/GW are optimistic). Real free-transfer/chip
history and the squad replay are done (2026-10-28).

## Later
- **Match odds:** ingested 2026-10-29 (`fpl import-odds`, table `match_odds`, 11 seasons). Features
  (win / draw / loss probability, xG from Over/Under + handicap, clean-sheet probability) tried: mean
  captured +0.015, within noise, reverted. Odds for upcoming GWs are still missing, so no live use.
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
Answered 2026-10-29 (decisions.md / data.md): DGW `xp` is the round total repeated per fixture row (harness fixed);
`ep_this` is `ep_next` with this-round availability, not a separate forecast; vaastav lags ~2.5 weeks in
batches (GW6 on 2026-10-29).
- How much of `xp`'s backtest value is leak? After the DGW fix `lgbm_xp` captures 0.87-0.88 vs 0.38-0.42
  leak-free (`lgbm`, `lgbm_xp_prev`). Live `ep` vs backtest `xp` are close over 2 GWs; needs more GWs of `ep`.
- (Defaults now leak-free `lgbm`, 2026-10-29.) Does `ep` as `xp` hold up beyond GW8? One gameweek: lgbm_xp(ep) 0.828 vs fpl_ep 0.566. Needs the `ep`
  history from the standing chores.
