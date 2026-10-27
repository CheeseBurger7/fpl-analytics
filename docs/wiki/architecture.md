# Architecture

All code is in `src/fpl/`; tests are in `tests/` (in-memory DuckDB, mocked HTTP, no live APIs).

| Module | Role |
|---|---|
| `api.py` | `FPLClient`: httpx client for the official FPL API (throttled, retries) |
| `store.py` | `Store`: DuckDB schema and inserts. `Store(path)` or in-memory. `replace_hist_season` swaps one season atomically |
| `ingest.py` | `take_snapshot`, `export_snapshot_parquet`, `sync_element_history`, `sync_entry` |
| `history.py` | vaastav CSV import: `import_seasons`, `seasons_between` |
| `features.py` | `build_features(con)` returns a DuckDB relation, one row per `hist_player_gw` row; `FEATURE_COLUMNS` |
| `backtest.py` | Walk-forward harness (below) |
| `optimizer.py` | MILP squad/lineup selection via scipy `milp` (below) |
| `model.py` | `LightGBMPredictor` (`lgbm`, `lgbm_xp` via `model_predictors()`), extra `model`; `fpl backtest --model` |
| `planner.py` | Transfer planner (below) |
| `planbacktest.py` | Season-long planner backtest (below) |
| `live.py` | Features for unplayed live-season fixtures (below) |
| `cli.py` | `fpl snapshot`, `history`, `import-history`, `entry`, `backtest`, `blind-pick`, `blind-score`, `transfers`, `backtest-planner` (global `--db`, default `data/processed/fpl.duckdb`) |

## features.py
Features for a row in gameweek G use only gameweeks strictly before G, so both fixtures of a DGW
see identical info. History is keyed on `hist_players.code`; GWs are ordered by earliest kickoff;
windows count fixtures played (blanks skipped). Columns: `mins_per_fix_{3,5,10}`, `start_rate_5`,
`zero_min_rate_5`, `pts_per_fix_{3,5,10,career}`, `pts_per_60_10`, `position`, `price`,
`price_change_5`, `was_home`, `opp_goals_for_6` / `opp_goals_against_6`, `own_goals_for_6` /
`own_goals_against_6`, `n_prior_fixtures`.

## backtest.py
- `load_dataset(con) -> Dataset`: features plus `xp`, a columnar dict of lists, chronological, each
  GW contiguous (`Dataset.gameweeks`). Helpers: `data.column(name, idx)`, `data.rows_before(t)`.
- `walk_forward_splits(data, eval_seasons, step)`: expanding window; train = rows kicking off
  strictly before the block's first GW start; `step=None` means one fit per season.
- `Predictor` protocol: `name`, `fit(data, idx)`, `predict(data, idx) -> list[float | None]`.
  Baselines: `ConstantPredictor`, `ColumnPredictor`; `default_baselines()` gives constant_2,
  rolling_mean_5, career_mean and fpl_xp. A LightGBM model plugs in as another `Predictor`.
- `run_backtest(data, predictors, seasons, step=, min_history=5, top_ks=(10, 20), hooks=())`:
  fixture predictions are summed per (player, GW); all predictors are scored on the same
  player-GWs (a missing prediction drops the player-GW for everyone); `min_history` masks cold
  starts. Per-GW metrics: MAE (player-GW and fixture level), Spearman, top-k hit rate.
  `summary()` is the unweighted mean over GWs (`by_season=True` to split).
- `GwMetricHook(ctx: GwContext) -> {name: float}`: called per predictor per GW with player-GW
  `predicted` / `actual` dicts and the `eligible` set; results are averaged into the summary.

## optimizer.py
- `Player(id, position, team, price, points)`; positions 1 GK, 2 DEF, 3 MID, 4 FWD; price in tenths.
- `optimize_squad(players, budget=1000, fixed_squad=None, bench_weight=0.001) -> Selection`
  (squad, xi, captain, objective, cost). Rules: 15 players as 2/5/5/3, at most 3 per club, XI
  formation bounds, captain doubled. No transfers, hits or chips yet.
- `pick_lineup(players, squad)`: best XI and captain from a fixed 15.
- `score_selection(sel, points)`: XI plus captain bonus, no auto-subs.
- `CapturedFractionHook(con)`: backtest hook giving `achieved_points`, `ceiling_points` and
  `captured_fraction` (fresh squad per GW, same pool and budget, scored on actual points). Position
  and club come from `hist_players`, price from the player's last fixture that GW.
- scipy is the optional extra `optimize` (also in `dev` so CI runs the tests).

## live.py
- `live_features(con, season, gw) -> Live`: shadows `hist_teams/players/player_gw` with TEMP
  tables (main tables untouched), adds played fixtures missing from vaastav (from `element_history`,
  scores from `fixture_snapshots`) and target-less rows for the gameweek's fixtures (price =
  snapshot `now_cost`), then runs `feature_sql`. Adds `ep` (`ep_this` if the gameweek is the
  snapshot's current one, else `ep_next`).
- `predictions(live)`: rolling_mean_5 and fpl_ep on common players; `player_pool(con, live, pts)`.
- `fpl blind-score --all` scores every finished `blind_gw*.json` and prints mean captured
  fraction per predictor (`live.mean_captured`); unfinished gameweeks are skipped.
- `fpl blind-pick --gw N [--entry-id]` freezes predictions and picks to `data/processed/blind_gw<N>.json`.
- `score_blind(con, frozen)` / `fpl blind-score --gw N`: achieved vs hindsight-ceiling points and
  captured fraction per predictor (`fresh`, and `entry` if present); needs the GW finished in the
  latest snapshot and its `element_history` rows.

## planner.py
- `plan_transfers(players, points, squad, bank=, free_transfers=1, max_transfers=3, discount=1.0,
  sell_prices=None) -> list[Plan]`: `points[g][id]` is predicted points in horizon gameweek g. One
  MILP per transfer count k (fixed post-transfer squad, per-GW XI and captain, budget = bank + sale
  value, 3-per-club, quotas); `Plan.net = gross - 4 * max(0, k - free)`.
- `best_plan(plans, margin=1.0)`: fewest transfers within `margin` points of the best net.
- `horizon_predictions(con, season, gw, horizon, predictor)`: `lgbm` (trained on all history),
  `rolling_mean_5` or `fpl_ep` per gameweek via `live_features`.
  `lgbm_xp` feeds `ep` as `xp` for the first GW (`live.ep_model_predictions`) and uses the first
  GW's per-fixture prediction x fixture count for later GWs.
- `fpl transfers --gw N` (default predictor `lgbm_xp`) reads the squad/bank from `entry_picks` / `entry_gameweeks` (latest GW <= N).

## planbacktest.py
- `simulate(gws, info, policy, horizon=1, discount=1.0, start=None) -> SeasonRun`: pure; `gws` is a
  list of `GwInput(key, predicted, fixtures, price, actual)`, `info[id] = (position, team)`.
  `Policy(name, max_transfers, margin)`; `HOLD`, `PLANNER`, `PLANNER_HITS`. Bookkeeping: bank and
  free transfers (`next_free_transfers`, cap 5), hit = 4 per transfer beyond the free ones.
  Lineups come from predictions; `actual` is used only in `score_selection`.
- `selling_price`, `autosub_points` (used when `GwInput.minutes` is set); sale price = FPL selling
  price from tracked purchase prices.
- `horizon_points`: later GWs = latest per-fixture prediction x that GW's fixture count (no leak).
- `season_inputs(data, predictors, season, con)`: fits each predictor once per season, shared
  eligible pool, prices carried over blanks, rounds without any forecast skipped.
  `ceiling_points` = hindsight fresh squad (context). CLI: `fpl backtest-planner`.

## Commands
```
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
fpl backtest --season 2024-25 --step 0 --by-season [--captured]   # --captured takes ~55s per season
fpl backtest-planner [--season S] [--predictor fpl_xp|lgbm_xp] [--horizon 1]   # ~45s per season/predictor
```
