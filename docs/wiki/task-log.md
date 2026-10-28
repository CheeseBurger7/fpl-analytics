# Task log (newest first)

## NEXT TASK (written 2026-10-28): chips in the planner
Start from `main`. Read `status.md`, `glossary.md`, `decisions.md` and the `xp` timing entry below.
1. Model chips (wildcard, free hit, bench boost, triple captain) in `plan_transfers` / the planner
   backtest; `fpl.replay.chips_left` already says which are available.
2. Collect `ep`: after GW9 (`fpl snapshot`, `fpl blind-score --gw 9` / `--all`) and every GW. The
   live `ep` track record is the only clean arbiter for `xp` (see below).

## 2026-10-28: Real free-transfer / chip history (branch feat/real-replay)
- New `fpl.replay` + `fpl replay`: reconstructs free transfers per GW from `entry_gameweeks`
  (transfers, hit cost, active chip). Rule found by fitting the recorded costs: unused free transfers
  bank (cap 5), +1 per GW, a wildcard / free-hit week uses none and adds none. It reproduces the
  recorded hit in all 8 GW of 2026-27 (hits GW4 8, GW8 4). Free transfers going into GW9: 1.
- Chips used 2026-27: free hit GW3, triple captain GW4, wildcard GW5; bench boost left (first half).
- `fpl transfers --free` now defaults to the derived value; output lists chips left. Chip plays are
  not planned yet. The replay of the squad itself already worked (`entry_picks` feeds `fpl transfers`).
- Caveats: the cap-5 and no-add-after-chip rules rest on 8 GW of one entry (the chip rule is checked by
  GW4 / GW6 / GW8 hits only); the half-season chip windows (GW1-19 / 20-38) are from the 2025-26 rules.
  7 new tests in `tests/test_replay.py`; 94 pass.

## 2026-10-28: GW9 transfer question, Joao Pedro out (no code changes)
- Ran `fpl snapshot` (snapshot 6) and `fpl entry`. Joao Pedro: thigh injury, no return date, 0% chance,
  902k transfers out, price -0.1. Candidates: N.Jackson 6.8m (+0.2m this GW, 823k in), Evanilson 6.2m
  (+0.1m, 282k in), Neto 6.6m. GW9 deadline 31 Oct 11:00.
- `fpl transfers --gw 9 --horizon 4` (lgbm_xp, bank 0.1, 1 free): best single transfer Pedro -> Evanilson
  (net 195.8 vs 175.7 hold); predicted GW9-12 points Evanilson 25.6, Neto 25.6, Jackson 24.4 (flat
  persistence, so blind to fixtures). 3-transfer plan with 8-pt hit includes Jackson.
- Fixtures GW9-14: mean FDR equal (about 2.67); GW15 Evanilson Arsenal (A, FDR 5) vs Jackson Coventry
  (A, 2). Opponents' goals conceded/game GW9-14: Jackson 1.69, Evanilson 1.19 (about 8 matches each).
- Career splits by opponent tier (top7 / mid / bottom6 of that season's table, appearances only):
  Evanilson 3.40 / 3.44 / 4.29 pts per game (n 25/27/21); Jackson 4.12 / 3.92 / 4.05 (n 26/24/20).
  Jackson's goals per game vs top 7 0.42 vs 0.20; samples small, differences within noise.
- Outcome (user, 2026-10-28): made Pedro -> Evanilson for GW9 (the planner's best single transfer; Jackson
  and Neto-for-Rogers left for later). Evanilson vs Jackson long term: Evanilson 678 min, 5.7 pts/90, xG/90
  0.41, 6.2m; Jackson 547 min, 5.6 pts/90, xG/90 0.30, 6.8m; a lean, not a verdict.
- Original advice: Pedro out now; Evanilson now / Jackson around GW11-12 is reasonable. Not executed
  by this repo; the user decides.

## 2026-10-27: Is vaastav `xp` recorded before the deadline? (branch feat/xp-timing)
**Evidence says no, at least partly; magnitude unknown.**
- *Haul test* (single-fixture players, 2020-21..2026-27, n=1512 with pts >= 10): `xp_g - xp_{g-1}` =
  +2.80 and `xp_{g+1} - xp_g` = -0.36, i.e. the jump from a haul is already in `xp_g`. The
  trusted live `ep` behaves the opposite way: GW8 haulers (n=15) went from the frozen pre-deadline
  `ep` (GW8) to `ep_next` (GW9, snapshot 3) by +1.83. Blankers (<=1 pt): -0.20 / +0.02 in vaastav, +0.03 live.
- *Absence test:* regular starters (mins_per_fix_5 >= 60) who played 0 minutes had `xp` <= 0.5 in
  45-57% of cases (2020-26) vs 3-6% for those who played; live frozen `ep` GW8: 36% (n=22) vs 3%.
  Not conclusive: many absences are known injuries.
- *Leak-free proxy:* `xp_prev` (new dataset column: per-fixture `xp` of the player's latest earlier GW with
  an `xp`; `fpl backtest --lag-xp`). Captured fraction (`--model --captured --step 0`, 2022-23 /
  2023-24 / 2024-25): fpl_xp 0.679 / 0.629 / 0.667 -> fpl_xp_prev 0.374 / 0.331 / 0.370 (= rolling_mean_5
  0.390 / 0.334 / 0.376); lgbm_xp 0.770 / 0.805 / 0.833 -> lgbm_xp_prev 0.419 / 0.381 / 0.415 (= lgbm
  0.418 / 0.374 / 0.420). Last GW's `xp` adds nothing, as a stale forecast would not.
- *Counter-evidence that the leak may be small:* live frozen `fpl_ep` captured 0.607 (GW8 fresh) /
  0.566 vs backtest `fpl_xp` 0.63-0.68; live `lgbm_xp(ep)` 0.828 (GW8) vs backtest 0.77-0.83. Two
  gameweeks, noise +-0.03/GW, so this neither clears nor convicts `xp`.
- **Consequence:** absolute backtest numbers for `fpl_xp` / `lgbm_xp` / planner (74-85 pts/GW) cannot be
  trusted as deadline-available performance; `lgbm` (no `xp`) and `rolling_mean_5` are leak-free.
  Comparisons between policies fed the same `xp` are still fair relative to each other. Decide on
  `ep`-as-`xp` only with live `ep` history (more GWs).
- Code: `backtest.load_dataset` adds `xp_prev` (not a required column); `LightGBMPredictor(xp_column=)`;
  `fpl backtest --lag-xp`. New test `test_xp_prev_is_the_latest_earlier_xp_per_fixture...`; 87 pass.

## 2026-10-27: Horizon-aware predictions (branch feat/next-task)
- **New `fpl.horizon`**: `HorizonPredictor(h, use_xp)` predicts the points of a fixture h GWs after
  the decision from the player's *source row* (latest row in a GW <= decision GW, same season) plus
  the target's `was_home` and the GW gap. Opponent form is dropped (no opponent id to look it up
  as of the decision), own-team form comes from the source row. `PersistencePredictor` is the
  reference (base model on the source row = the planner's persistence). Leak-free by construction.
- `fpl backtest --model --horizons H --step 0` adds both per h; `GwInput.ahead` +
  `season_inputs(ahead_models=...)` + `fpl backtest-planner --horizon-models` feed them to the
  planner backtest (`horizon_points` prefers `ahead`). 7 new tests, 86 pass.
- **Prediction quality, 2024-25, per-GW MAE / Spearman** (step 0): h1 lgbm_xp persistence
  1.081 / 0.680 vs lgbm_xp_h1 1.060 / 0.691; h2 1.124 / 0.651 vs 1.095 / 0.663; h3 1.175 / 0.618
  vs 1.121 / 0.641. Without xp, horizon models ~ persistence (h3 lgbm 1.138 vs 1.135).
  So the horizon model helps a little at the metric level.
- **Planner backtest, lgbm_xp only, total points (planner / planner_hits), persistence vs
  horizon models:** horizon 3: 2023-24 3028 / 3010 vs 3009 / 3033; 2024-25 3228 / 3195 vs
  2874 / 2961. Horizon 4, 2024-25: 3170 / 3180 vs 2932 / 3028. Horizon 1, 2024-25: 3050 / 3109.
  **The horizon models did not help the planner and were worse on 2024-25**, despite better
  MAE. Likely cause: their later-GW forecasts are flatter than the current-GW `xp`-fed ones, so
  the plan weighs the first GW more and transfers less (88-96 vs 105-108). Persistence stays the
  default; `--horizon-models` is opt-in. Horizon 6 (planner / planner_hits, persistence vs models): 2023-24 3025 / 3025 vs 2975 / 2875; 2024-25 3107 / 3117 vs 2958 / 3005. Horizon 1, 2023-24: 2990 / 3025. Persistence wins or ties in every comparison.
- Caveat: numbers with only `lgbm_xp` use a larger eligible pool than the earlier two-predictor
  tables, so they are not comparable with them.
- Horizon-model live wiring (`planner.horizon_predictions`) NOT done: no planner gain.

## 2026-10-27: FPL influence / creativity / threat as features (PR #16)
- `features.py`: `influence_5/10`, `creativity_5/10`, `threat_5/10` = lagged per-fixture means
  (`ICT_WINDOWS`), leak-free like the other rolls. Data: populated in `hist_player_gw` for every
  season since 2016-17 (xG only since 2022-23). `live._shadow` now copies the three from
  `element_history.raw` for played-but-missing fixtures; `live_features(2026-27, 9)` has them for
  669/669 players. New test `test_ict_features_are_lagged_means_per_fixture`.
- **Result: no measurable gain.** `fpl backtest --model --captured --step 0` before -> after
  (captured fraction; MAE unchanged to 3 d.p.): 2024-25 lgbm 0.409 -> 0.416, lgbm_xp 0.814 -> 0.815;
  2023-24 lgbm 0.360 -> 0.370, lgbm_xp 0.784 -> 0.789; 2025-26 (11 GWs) lgbm 0.371 -> 0.357,
  lgbm_xp 0.837 -> 0.810. Differences are within season-to-season noise. Kept (cheap, leak-free);
  `xp` already carries most of this signal. Frozen GW9 picks were made before this change.

## 2026-10-26: Planner backtest realism: selling price, auto-subs (PR #16)
- `planner.plan_transfers`: **budget bug fixed** when `sell_prices` is given: a kept player now costs
  his selling price (before, kept players cost market price against a selling-price credit).
- `planbacktest`: `selling_price(buy, now)` (half of a rise, rounded down), purchase prices tracked
  per squad member; `autosub_points` (bench GK only for GK, outfield bench by predicted points, formation
  stays legal, vice-captain = highest-predicted player who played) used when `GwInput.minutes` is set
  (`season_inputs` fills it from `hist_player_gw.minutes`). 4 new tests, 79 pass.
- Results, total points, `fpl backtest-planner` (both predictors; was -> now):
  2023-24 fpl_xp planner 2786 -> 2757, lgbm_xp planner 2992 -> 2913, planner_hits 3068 -> 3066;
  2024-25 fpl_xp planner 2579 -> 2587, lgbm_xp planner 2896 -> 2855. Per GW still 74-83 for the
  planner, so selling price and auto-subs are small effects; the optimism is elsewhere (see caveats).
- Caveats / still open: `xp` timing not verified (main suspect for 74-83/GW vs ~60-70 for top real
  managers); no real free-transfer/chip history; real-squad replay from `entry_picks` not done.
- Not done from the post-GW9 plan: run `fpl snapshot`, `fpl blind-score --gw 9` and `--all` after
  GW9 finishes.

## 2026-10-26: GW9 pre-deadline run (no code changes)
- Ran `fpl snapshot` (snapshot 5: 669 players, 380 fixtures), `fpl entry` (8 GWs of picks),
  `fpl blind-pick --gw 9 --model` (frozen to `data/processed/blind_gw9.json`), `fpl transfers --gw 9`.
- Predicted XI points (in-sample, pre-deadline): rolling_mean_5 85.8, fpl_ep 95.0, lgbm_xp(ep) 67.2
  (captains Haaland / Konsa / Neto). Score after GW9 with `fpl blind-score --gw 9`.
- `transfers` (lgbm_xp, GW9-12, bank 0.1, 1 free): hold 174.2; 1 transfer (Rogers -> Neto) 191.9;
  2 (+4 hit) 204.6; 3 (-8 hit) 213.8 = Rogers, Joao Pedro, Gibbs-White -> Evanilson, Henderson, Neto
  (`best_plan` pick). Captain Neto. Not executed; the user decides.
- First `ep_next` snapshot taken for GW9 on a fresh GW (snapshot 5), continuing the `ep` log.

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
- Added `fpl blind-score --all` (multi-GW live track record; means per predictor/who). Use it
  after each GW once `blind-pick --model` files exist (GW9 onwards are the clean pre-kickoff ones).
- Tests: 75 pass (new: `tests/test_planbacktest.py` for bank/free-transfer/hit bookkeeping,
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
