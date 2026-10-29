# Decisions

- **Per-fixture rows.** Model per fixture; sum predictions per (player, GW) for the optimizer
  (blank = 0, DGW = sum). Backtests may only use the fixture schedule known at prediction time.
- **Main metric is decision-level regret.** Per GW: the hindsight-optimal squad (ILP on actual
  points) versus the squad the optimizer picks from predictions, both scored on actual points.
  Report the captured fraction (achieved / ceiling) averaged over GWs and seasons, and compare
  baselines through the same procedure. MAE and per-GW Spearman / top-k hit rate are diagnostics.
  Mini-league results are not a dev metric (noisy, one season).
- **Common-row comparison.** All predictors are scored on the same player-GWs with
  `n_prior_fixtures >= min_history` (default 5), so a baseline missing data (e.g. `xp` before
  2020-21) does not skew comparisons.
- **Deferred features.** ICT, xG/xA/xGI and FPL xp are further lagged rolling columns. If `xp` is
  used as a feature, report results with and without it.
- **Optimizer is a fresh-squad problem first** (no transfers, hits or chips); the captured
  fraction measures prediction quality, not season-long play.
- **Training cutoff.** Training rows must kick off strictly before the evaluated block's first GW.
- **Tooling.** Features in DuckDB SQL; metrics in plain Python (no numpy/pandas yet); scipy only
  for the optimizer. Add heavier dependencies as optional extras when needed. LightGBM (numpy) is the extra `model`.
- **Planner scope.** Transfers made now only, squad fixed over the horizon, hit subtracted after the
  per-k solve, `best_plan` needs a 1-point margin per extra transfer (predictions are noisy).
  Chips and later transfers are out of scope until the planner is backtested.
- **LightGBM target/loss.** Per-fixture points, L2 loss, summed per GW by the harness; always report
  `lgbm` and `lgbm_xp` side by side because `xp` carries most of the gain.
- **Zero-`xp` rounds are missing, not 0.** A round where every `xp` is 0 is NULL in the dataset
  (vaastav gap). Rounds with no forecast are skipped in the planner backtest for all policies.
- **Planner backtest design.** Policies share predictions; lineup chosen from predictions, scored on
  actuals; hits and free transfers tracked; horizon 1 is the reference (no leak). Horizon > 1 uses
  persistence (latest per-fixture prediction x known fixture count) because dataset rows of later
  GWs contain results the planner could not know. Horizon 4 did not beat horizon 1. Compare
  policies/predictors only; absolute points are optimistic (see task log caveats).
- **Default predictor is leak-free `lgbm` (2026-10-29, supersedes "`ep` stands in for `xp`").**
  `lgbm_xp` learned to trust a leaky `xp` (captured 0.87-0.88 vs 0.38-0.42 leak-free; `xp_prev` adds
  nothing), so it likely over-weights live `ep`. `fpl transfers` and `fpl backtest-planner` now default
  to `lgbm`; `lgbm_xp` / `fpl_xp` stay opt-in. `blind-pick --model` still records `lgbm_xp(ep)` next to
  `fpl_ep` and `rolling_mean_5` so `blind-score --all` builds the live evidence (one GW so far: GW8
  `lgbm_xp(ep)` 0.828 vs `fpl_ep` 0.566). Promote `ep`-based models only if they beat `lgbm` and
  `fpl_ep` over several GWs; the long-term fix is a model trained on stored live `ep`.
- **Availability news is a live multiplier, not a feature (2026-10-29).** Snapshots hold
  `chance_of_playing_next_round` from GW8 only, so no model can learn it yet. `horizon_predictions`
  multiplies the first GW of `lgbm` / `rolling_mean_5` by chance/100 (`news=False` turns it off).
- **Horizon models are opt-in.** Per-horizon LightGBM (`fpl.horizon`) lowers MAE vs persistence
  (h3 1.121 vs 1.175, 2024-25) but did not improve planner totals (worse on 2024-25), so the
  planner keeps persistence by default.
- **LightGBM defaults kept.** A 7-variant sweep (rate, rounds, leaves, min_data, l2, huber) moved
  captured fraction by <= 0.011 on 2022-25; not distinguishable from noise.
- **Component models and lagged rates are not adopted.** Captured fraction on 2022-25 (leak-free):
  lgbm 0.400 mean vs comp_x 0.402; per-season differences within +-0.03 noise. Code reverted;
  `lgbm` stays the leak-free model. Lever left is news, not form (task log 2026-10-28).
- **Chip timing: no clever rule yet.** Backtest (2023-25): waiting for the best predicted gain within 6 or
  19 GWs (+23..+44 per season) is not distinguishable from playing the chip at once (+31 / +32);
  later-GW predictions are persistence x fixture count, which cannot see much. Keep the chips as an
  option in the planner; decide timing by hand with `fpl transfers --chips --horizon 8`.
- **`xp` is suspect; `xp_prev` is the leak-free check.** vaastav `xp` of a gameweek appears to include
  that gameweek's result (haul test, task log 2026-10-27). Report `lgbm` and `lgbm_xp` (and `xp_prev`
  variants via `--lag-xp`) together; never quote `lgbm_xp` / planner totals as realistic.
- **`xp` is split over DGW fixture rows.** vaastav repeats the round `xp` on each row; dividing by the
  row count makes it a per-fixture forecast that sums to the round (2026-10-29).
