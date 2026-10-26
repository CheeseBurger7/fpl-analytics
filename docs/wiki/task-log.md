# Task log (newest first)

## NEXT TASK (not started; written 2026-10-26): make the planner trustworthy, collect `ep`
Start from `main`. Read `status.md`, `glossary.md`, `decisions.md` first. Candidates, in order:
1. **Log `ep` every gameweek.** Run `fpl snapshot` before each deadline (and `blind-pick --model`,
   `transfers`) so that `ep_next` history exists for the GW it forecasts; there is none today
   (all 3 snapshots hold GW9's `ep_next`). With a few GWs, redo the `ep` vs `xp` check below.
2. **Realism of the planner backtest.** Real selling price (half of the profit), real free
   transfers/chips, auto-subs; replay the real squad from `entry_picks` for 2026-27 (not done yet;
   8 GWs). Also check whether vaastav `xp` is recorded before the deadline (absolute points are
   optimistic, see below).
3. Horizon-aware targets (1-6 GWs) instead of persistence; tune LightGBM; chips.

## 2026-10-26: Planner backtest, `ep` as `xp`, zero-`xp` rounds (branch feat/planner-backtest)
- **New** `fpl.planbacktest` + `fpl backtest-planner [--season S] [--predictor fpl_xp|lgbm_xp]
  [--horizon H]`: one squad per policy through a season, start squad = `optimize_squad` on GW1
  predictions at 100m, first GW no transfers, then 1 free transfer per GW (bank up to 5), 4 per
  extra, sale price = current price, XI + captain chosen from predictions, scored on actuals
  (`score_selection`, no auto-subs) minus hits. Policies: `hold`, `planner` (`best_plan` margin
  1.0, max 3 transfers), `planner_hits` (margin 0). One fit per season (as in `backtest`).
- **Data bug found and fixed.** vaastav stores a missing `xp` as 0 for a whole round (27 of 38
  rounds in 2025-26; 2023-24 GW26; 2024-25 GW22/32/34; 2026-27 GW2/6). `load_dataset` now maps a
  round whose `xp` is 0 for everyone to NULL. This changes earlier numbers: 2024-25 reference
  table in `glossary.md` (fpl_xp 0.618 -> 0.664, lgbm_xp 0.793 -> 0.814). Planner seasons skip
  rounds with no forecast (37 GWs in 2023-24, 35 in 2024-25), identically for all policies.
- **Results, total actual points over the season (hit points / transfers in brackets), horizon 1:**

  | season | predictor | hold | planner | planner_hits |
  |---|---|---|---|---|
  | 2023-24 (37 GWs, ceiling 5852) | fpl_xp | 1624 | 2786 (144/73) | 2824 (160/77) |
  | | lgbm_xp | 1582 | 2992 (176/81) | 3068 (236/96) |
  | 2024-25 (35 GWs, ceiling 5236) | fpl_xp | 1673 | 2579 (92/58) | 2550 (140/70) |
  | | lgbm_xp | 958 | 2896 (156/74) | 2964 (220/90) |

  Horizon 4 (persistence beyond GW g): 2023-24 fpl_xp 1623 / 2765 (252/100) / 2755; lgbm_xp 1582 /
  2952 (276/106) / 2952. 2024-25 fpl_xp 1673 / 2582 (240/95) / 2582; lgbm_xp 958 / 2913 (260/100)
  / 2920 (264/101). Points per GW are totals / 35-37 (planner 70-85, hold 27-48).
- **Reading.** The planner beats hold by 900-2000 points (net of hits) in every cell. `lgbm_xp` beats
  `fpl_xp` as the planner's input by 206 (2023-24) and 317 (2024-25) points. `planner_hits`
  (margin 0) vs `planner`: +38/-29 (fpl_xp), +76/+68 (lgbm_xp) at horizon 1, i.e. no reliable gain
  from taking hits. Horizon 4 with persistence does not beat horizon 1 (-40..+17 for lgbm_xp,
  +/-20 for fpl_xp) and makes 25-30 more transfers, so keep horizon 1 as the reference.
- **Caveats (read before trusting absolute numbers).** 70-85 points/GW is above what real top
  managers score, so the absolute level is optimistic: sale price = current price (no 50% profit
  rule), unlimited fresh information at each deadline (vaastav `xp` is assumed pre-deadline,
  unverified), fixture counts known, club = end-of-season club, no chips. `hold` is a weak
  baseline (a GW1 squad never changed; lgbm_xp's 2024-25 start squad is poor, 958, because GW1
  `xp` is unreliable: corr with points 0.40 vs 0.75 later). Compare policies and predictors with
  each other, not with real FPL scores. No real-squad replay was done.
- **`ep` as `xp` (Part 2).** No `ep` history exists (3 snapshots, all GW9's `ep_next`; vaastav
  2026-27 stops at GW6), so `xp`-vs-`ep` could only be checked on GW8 using the frozen
  `ep_this` (snapshot 1) against actuals: 662 players, mean ep 1.07 vs actual 1.40 (xp in 2026-27
  GW3-5 averages 1.36-1.43), MAE 1.070, Pearson 0.56. Decision test: `lgbm_xp` fed `ep` as `xp`
  for GW8 captured 120/145 = 0.828, vs `fpl_ep` 82 (0.566), `lgbm` 35 (0.241), rolling_mean_5 47
  (0.324); MAE 0.939 vs 1.070, Spearman 0.742 vs 0.731. (`fpl_ep` is 82 here, 88 in the GW8 entry
  below: same pool restriction as the other rows, re-optimised.) One gameweek only, but a large
  gap, so `ep` is used as `xp` for the first GW. See `decisions.md`.
- **Wired in:** `fpl transfers --predictor lgbm_xp` (now the default), `horizon_predictions(...,
  "lgbm_xp")` (first GW `ep` as `xp`, later GWs persistence), `fpl blind-pick --model` (adds
  `lgbm_xp(ep)`), `live.ep_model_predictions`. First live run: GW9-11, 3 transfers, predicted +27.7
  over holding (predictions only).
- Tests: 74 pass (new: `tests/test_planbacktest.py` for bank/free-transfer/hit bookkeeping,
  scoring on actuals only, persistence, season inputs; zero-`xp` round; `ep_model_predictions`).
  ruff clean. Each horizon-1 run takes ~45 s per season and predictor for fpl_xp (~10 min total
  with lgbm_xp, both seasons).

## 2026-10-26: Transfer planner, GW8 blind score, glossary (branch feat/transfer-planner)
- Added `fpl.planner` (`plan_transfers`, `best_plan`, `horizon_predictions`) and `fpl transfers
  --gw N` (flags: `--horizon 4 --free 1 --max-transfers 3 --discount 1.0 --predictor lgbm`).
  One MILP per transfer count k: fixed post-transfer squad over the horizon, XI and captain per
  GW, hit = 4 x (k - free) subtracted afterwards. `best_plan` takes the fewest transfers within
  1.0 point of the top net. `LightGBMPredictor.predict_rows` predicts from live feature dicts;
  `lgbm` for the planner is trained on all of `hist_player_gw` (about 12 s).
- First live run (GW9, horizon 4, lgbm, 0.1m bank, 1 free): unchanged squad 194.2 predicted pts;
  1 transfer (Gibbs-White -> Mbeumo) 199.9; 3 transfers 200.6 net of an 8-pt hit, so the planner
  recommends the single transfer. Predictions only; no result to compare yet.
- Caveats: not backtested (planned: replay past GWs against `entry_picks`); squad is fixed over the
  horizon (no later transfers, chips, auto-subs); sale price = current price (real selling price is
  lower after rises); later-GW features only see results to GW-1; `lgbm` here has no `xp`, the
  weaker variant (captured fraction 0.404 vs 0.793 with xp); free transfers are a flag, not derived.
- GW8 blind score (`fpl blind-score --gw 8`, picks frozen after GW8 kickoffs began, so not a clean
  pre-deadline test). Fresh squad achieved/ceiling 145.0: rolling_mean_5 47.0 (0.324), fpl_ep 88.0
  (0.607). The user's own squad, lineup choice only (ceiling = best XI from the same 15, 78.0):
  rolling_mean_5 69.0 (0.885), fpl_ep 72.0 (0.923). The `entry` fractions are NOT comparable to
  the `fresh` ones (different ceilings).
- Added `glossary.md`. Tests: 66 pass, ruff clean.

## 2026-10-25: LightGBM predictor (branch feat/lightgbm)
- Added `fpl.model.LightGBMPredictor` (per-fixture L2 regression on `FEATURE_COLUMNS`, optional
  `xp`; 300 rounds, lr 0.05, 31 leaves, refit per backtest block) and `fpl backtest --model`
  (adds `lgbm` and `lgbm_xp`). Extra `model` in pyproject (also in `dev`).
- Backtest, one fit per season, vs baselines (MAE / Spearman / top-10 hit):
  2023-24: fpl_xp 0.876/0.747/0.363, lgbm 0.991/0.678/0.145, lgbm_xp 0.730/0.747/0.516.
  2024-25: fpl_xp 0.943/0.756/0.350, lgbm 1.058/0.692/0.195, lgbm_xp 0.759/0.765/0.545.
  Captured fraction (ceiling 151.3): rolling_mean_5 0.371, fpl_xp 0.618 (93.2 pts), lgbm 0.404
  (61.7), lgbm_xp 0.793 (119.9).
- Reading: without `xp` the model only slightly beats rolling_mean_5; nearly all the gain comes from
  `xp` (FPL's news-aware availability/fixture info) plus recalibration. Caveats: hyperparameters
  untuned, single-fixture target (no horizon yet), xp missing before 2020-21 so those training
  rows use NaN, live use needs `ep` as the stand-in for `xp` (not the same field).
- Tests: `tests/test_model.py` (60 pass, ruff clean).

## 2026-10-25: Blind-pick scorer built, GW8 not yet scorable (branch not yet created)
- Added `fpl.live.score_blind` and `fpl blind-score --gw N`: scores each frozen XI/captain
  (`score_selection`, no auto-subs) on `element_history` points for that round, against the
  hindsight ceiling (`optimize_squad` on actuals over the same pool and snapshot prices; for the
  user's squad, best lineup via `pick_lineup`). Raises unless every fixture of the GW is `finished`
  in the latest snapshot.
- Refreshed data: snapshot 2 and `fpl history` (5,220 rows; GW8 rows partial). Snapshot 2 shows all
  10 GW8 fixtures unfinished (last kickoff 2026-10-25 16:30), so the scorer correctly refuses.
  No GW8 actuals were looked at; no GW8 result yet.
- Tests: 2 new in `tests/test_live.py` (58 pass, ruff clean).

## 2026-10-25: Live-data adapter and frozen blind GW8 picks (PR #8)
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
- Frozen fpl_ep XI: Raya, Gabriel, Konsa, N.Jackson, Evanilson, De Cuyper, Vuskovic, Henderson,
  Neto, Doku, Haaland (C Konsa). rolling_mean_5 captain is a defender (Vuskovic), worth a look.
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
