# Task log (newest first)

## NEXT TASK (not started; brief written 2026-10-26): backtest the transfer planner, then `ep` as `xp`
Start from `main` on a new branch (e.g. `feat/planner-backtest`). Read `status.md`, `glossary.md`
and the `planner.py` / `backtest.py` / `model.py` sections of `architecture.md` first.

**Goal.** Find out whether `fpl.planner` makes better transfers than doing nothing, scored on actual
points, before anyone trusts `fpl transfers`. Primary metric: total actual points over a season
(or per-GW mean) of a squad managed by the planner versus baselines, hits included.

**Part 1: planner backtest (new module, e.g. `fpl.planbacktest`, CLI `fpl backtest-planner`).**
- Simulation: start each evaluated season from a fixed legal squad (e.g. `optimize_squad` on GW1
  predictions at 100m, or the real GW1 squad from `entry_picks` for 2026-27). Each GW g: get
  predicted points for GWs g..g+h-1, call `plan_transfers`/`best_plan`, apply the chosen transfers
  (track bank and free transfers: 1 per GW, unused banked up to 5, spent ones consumed), then score
  the post-transfer squad's best XI + captain on the actual GW g points with `score_selection`
  (`pick_lineup` on actuals is NOT allowed for the score: choose the XI from predictions, score on
  actuals), minus 4 per hit. Sale price = current price (known simplification).
- Policies to compare on identical predictions: `hold` (never transfer), `planner` (best_plan,
  margin 1.0), `planner_hits` (margin 0, max_transfers 3), and the hindsight ceiling
  (`optimize_squad` on actuals each GW, fresh squad, for context only). Use `fpl_xp` and `lgbm_xp`
  as predictors (they have `xp`; `lgbm` without xp is the weak variant).
- Predictions for future GWs in the sim: the walk-forward dataset's feature rows for GW g+j are
  built from results before g+j, i.e. they would include GW g..g+j-1 results the planner could not
  know at GW g (leak). Decide and record in `decisions.md`: either horizon 1 only (no leak, start
  here), or for j>0 reuse the GW g-based prediction of the player's next fixture(s) (persistence),
  or compute features as-of g (needs a feature-builder cut-off argument). Prefer horizon 1 first,
  then horizon 3-4 with persistence, and report both.
- Season/time cost: `plan_transfers` is ~1-3 s per call; 38 GWs x a few policies is fine. Train
  `lgbm_xp` once per season (`--step 0` style) as in the existing backtest, not per GW.
- Real-squad replay (sanity check only, 2026-10: 8 GWs of `entry_picks`/`entry_transfers`): what
  would the planner have done each GW versus what the user did, scored on actuals. Too short for
  conclusions; do not use the entry id in committed files or the wiki.
- Report: points per GW, total, hits taken, transfers per GW, for each policy, per season
  (suggest 2023-24 and 2024-25). Put numbers in the task log; add the metric definitions to
  `glossary.md`.

**Part 2: can `ep` stand in for `xp` live?** The strong model (`lgbm_xp`, captured fraction 0.793)
needs `xp`, but live rows only have FPL's `ep` (`ep_this` / `ep_next`; they equalled each other in
every spot check, see Open questions). Check from data, not assumption: over 2026-10 live snapshots
(`player_snapshots.ep_next` vs the later `element_history` actuals, and vs vaastav `xp` for the
overlapping GWs 1-6 of 2026-27 if rows align by player/fixture), compare distribution, mean and
correlation of `ep` against `xp` and against actual points. If close: add a `lgbm_xp` option to
`horizon_predictions` / `fpl transfers` / `blind-pick` feeding `ep` as `xp` for the first GW only
(later GWs have no `ep`; say how they are handled, e.g. NaN). If not: record why and what is needed
(e.g. snapshot `ep_next` every GW to build our own `xp` history).

**Done when.** Planner policies compared with numbers in the task log; decision on `ep` recorded;
wiki (`status.md`, `architecture.md`, `decisions.md`, `glossary.md`, this log) updated in the same
PR; tests for the simulation (bank/free-transfer bookkeeping, hit accounting, no use of actuals
before scoring) with in-memory DuckDB and no live API calls; ruff clean. No Co-Authored-By or
Generated-with lines; do not commit `data/` or the entry id.

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
