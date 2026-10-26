# Glossary: terms in the results tables

## Which number to target
**Captured fraction is the primary metric** (higher is better, 1.0 = hindsight-perfect). It measures
what we ultimately do: pick a squad from predictions. MAE and Spearman are diagnostics for why a
predictor is good or bad; do not optimise them at the expense of captured fraction. A predictor with
a better MAE can still pick worse squads if it mis-ranks the top players.

## Predictors
- **`xp`**: FPL's own expected points per player-fixture in the historical vaastav data (from
  2020-21). Baseline `fpl_xp`, and an input to `lgbm_xp`.
- **`ep`**: the same idea from the live API (`ep_this` / `ep_next` in the snapshot). Baseline
  `fpl_ep` in `blind-pick`. Only one-GW evidence that `ep` can replace `xp` (task log).
- **`rolling_mean_5`**: mean points over the player's last 5 fixtures played (`pts_per_fix_5`).
- **`career_mean`**: mean points over all prior fixtures. **`constant_2`**: predicts 2 for everyone.
- **`lgbm`**: LightGBM regressor ([`fpl.model`](../../src/fpl/model.py)) on our own features
  (playing time, recent points, position, price, home/away, team goals for/against).
  **`lgbm_xp`** is the same plus `xp` as an input. Fixture predictions are summed per gameweek, so a
  double gameweek counts both fixtures.

## Metrics
- **MAE**: mean absolute error between predicted and actual points per player per gameweek
  (`mae_fixture`: per fixture). Lower is better. 0.76 = off by 0.76 points on average.
- **Spearman**: rank correlation of predicted vs actual points across players within a gameweek,
  averaged over gameweeks. -1..1, higher is better. Only the ordering matters, not the values.
- **top10 / top20**: share of the predicted top 10 / 20 players who are in the actual top 10 / 20
  (ties at the cutoff count as hits).
- **Captured fraction** = `achieved_points / ceiling_points`, per gameweek, averaged.
  - `achieved_points`: the XI (captain doubled, no auto-subs) that `optimize_squad` builds from the
    predictions under 100m budget, 2/5/5/3 squad, max 3 per club and legal formation, scored on
    actual points.
  - `ceiling_points`: the same optimizer fed the actual points (hindsight).
  - Fresh squad every gameweek, so it measures prediction quality, not season-long play.
- **Net / gross (transfer planner)**: `gross` is predicted points over the horizon (captain doubled)
  for the post-transfer squad; `net` = `gross` minus 4 per transfer beyond the free ones. Compare
  plans by `net`; the 0-transfer plan is the baseline. These are predictions, not results.

## Planner backtest (`fpl backtest-planner`)
- **total / per_gw**: actual points of the policy's XI + captain (no auto-subs) summed / averaged
  over evaluated GWs, after hit points. **hit_pts**: 4 per transfer beyond the free ones.
  **transfers**: players brought in. **ceiling**: hindsight fresh squad each GW (context only).
- **hold**: never transfer (GW1 squad all season). **planner**: `best_plan` margin 1.0, up to 3
  transfers. **planner_hits**: margin 0. **`lgbm_xp(ep)`**: `lgbm_xp` fed FPL's live `ep` as `xp`.
- Compare policies and predictors with each other; absolute points are optimistic.

## Reference numbers (2024-25, one fit per season; after the zero-`xp` fix, 35 GWs)
| predictor | MAE | Spearman | top10 | captured fraction |
|---|---|---|---|---|
| rolling_mean_5 | 1.107 | 0.683 | 0.171 | 0.372 |
| fpl_xp | 0.915 | 0.756 | 0.380 | 0.664 |
| lgbm | 1.054 | 0.692 | 0.197 | 0.409 |
| lgbm_xp | 0.719 | 0.784 | 0.574 | 0.814 |
