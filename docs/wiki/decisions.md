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
- **`ep` stands in for `xp` live (provisional).** One-GW test (GW8): `lgbm_xp` fed `ep` captured
  0.828 vs `fpl_ep` 0.566, so `fpl transfers` defaults to `lgbm_xp` and `blind-pick --model` records
  it. Later horizon GWs have no `ep` and use persistence. Revisit once several GWs of `ep` exist.
