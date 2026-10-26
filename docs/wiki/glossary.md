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
  `fpl_ep` in `blind-pick`. Whether `ep` is statistically the same quantity as `xp` is unverified.
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

## Reference numbers (2024-25, one fit per season)
| predictor | MAE | Spearman | top10 | captured fraction |
|---|---|---|---|---|
| rolling_mean_5 | 1.109 | 0.685 | 0.176 | 0.371 |
| fpl_xp | 0.943 | 0.756 | 0.350 | 0.618 |
| lgbm | 1.058 | 0.692 | 0.195 | 0.404 |
| lgbm_xp | 0.759 | 0.765 | 0.545 | 0.793 |
