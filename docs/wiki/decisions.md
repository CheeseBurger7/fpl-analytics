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
  for the optimizer. Add heavier dependencies (LightGBM) as optional extras when needed.
