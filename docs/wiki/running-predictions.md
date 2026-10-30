# Running predictions for an upcoming gameweek

Recipe for GW N (the next deadline). Windows / PowerShell, run from the repo root with the venv
(`.venv\Scripts\fpl`). `FPL_ENTRY_ID` must be set in the user environment (never write it in the repo).
Predictor background: [glossary.md](glossary.md); `xp` leak caveat: [decisions.md](decisions.md) and the
`xp` timing entry in [task-log.md](task-log.md).

## 1. Refresh data (before the deadline, ideally the day of)
```
fpl snapshot          # freezes bootstrap-static + fixtures (prices, injuries, ep, fixtures)
fpl entry             # your picks / bank / transfers / chips (default $env:FPL_ENTRY_ID)
```
- Both are read-only calls to the official API. Run `fpl snapshot` again just before the deadline if
  injury news is moving.
- `fpl entry` only has picks up to the last *finished* deadline. A transfer made for GW N is **not**
  stored until GW N's deadline passes, so apply it by hand (see step 4).
- vaastav history lags (2026-27 stopped at GW6 on 2026-10-25); the adapter fills the gap from
  `element_history`, so run `fpl history` if played-GW rows are missing.

## 2. Check state
```
fpl replay            # real free transfers per GW + chips used (bench boost etc. left)
```

## 3. Best moves from your squad
```
fpl transfers --gw N --horizon 4                       # default predictor lgbm, --free derived
fpl transfers --gw N --horizon 1 --max-transfers 1     # this-GW only
```
- Output per transfer count k: net points (gross minus 4 per transfer beyond the free ones), who goes
  out / in, `<-- best`, chips left, and the GW-N captain.
- Predictors (`--predictor`): `lgbm` (default, leak-free), `lgbm_xp` (uses FPL `ep` as `xp`; unproven, see decisions), `fpl_ep`,
  `rolling_mean_5`. Compare `lgbm` against `lgbm_xp` when the answer matters.
- Horizon > 1 uses each player's flat per-fixture prediction x fixture count: it **ignores fixture
  difficulty**. Check fixtures separately for longer plans.
- The squad is the latest stored picks (<= N). After a transfer already made for N, the unchanged-squad
  line is stale; in the plan, treat the matching transfer as done and rerun from the new squad with
  `--free 0` (see the snippet below).
- `--chips` also evaluates every chip you have left in every horizon GW (use `--horizon 6` or more and
  `--max-transfers 1`, about a minute). Gains are vs the best chip-free plan and ignore what the chip
  could do later, so compare chips with each other and look at double / blank weeks yourself.
- A hit is worth it only if net beats the 0-transfer line by clearly more than noise (about 1-2 pts).

## 4. Lineup and captain for GW N
The `fpl transfers` output prints the captain only. For the full XI / bench, call the planner in Python
(a transfer made but not yet stored: replace the player in `squad` and use its bank):
```python
from fpl.store import Store
from fpl.optimizer import Player
from fpl.planner import horizon_predictions, plan_transfers

con = Store("data/processed/fpl.duckdb").con
sid, = con.execute("SELECT MAX(snapshot_id) FROM snapshots").fetchone()
info = con.execute("SELECT element_id, web_name, position, team_id, now_cost "
                   "FROM player_snapshots WHERE snapshot_id = ?", [sid]).fetchall()
pool = [Player(i, pos, team, cost, 0.0) for i, _, pos, team, cost in info]
eid, G = int(os.environ["FPL_ENTRY_ID"]), 8                         # G = latest stored picks GW
squad_ids = [r[0] for r in con.execute(
    "SELECT element_id FROM entry_picks WHERE entry_id = ? AND gameweek = ?", [eid, G]).fetchall()]
bank_tenths = con.execute(
    "SELECT bank FROM entry_gameweeks WHERE entry_id = ? AND gameweek = ?", [eid, G]).fetchall()[0][0]
pts = horizon_predictions(con, "2026-27", N, 1, "lgbm")        # pts[0][id] = predicted GW-N points
plan = plan_transfers(pool, pts, squad_ids, bank=bank_tenths, free_transfers=0, max_transfers=0)[0]
plan.xi[0], plan.captain[0]                                         # element ids; bench = squad - xi
```
Add `import os`. Names come from `player_snapshots` (`info`). Use `.fetchall()`, not `.fetchone()`, for
the last query before `horizon_predictions`: an unfinished DuckDB result on the shared connection makes
it fail with `ResourceInUseException`. Checked 2026-10-28: unchanged GW8 squad scored 43.9 for GW9.

## 5. Best 15-man squad from scratch (planning, ignores your squad)
```python
from fpl.optimizer import optimize_squad
tot = {}                                   # sum predicted points over the horizon
for g in horizon_predictions(con, "2026-27", N, 4, "lgbm"):
    for i, v in g.items():
        tot[i] = tot.get(i, 0) + v
pool = [Player(i, pos, team, cost, tot[i]) for i, _, pos, team, cost in info if i in tot]
sel = optimize_squad(pool, budget=1000)    # sel.squad, sel.xi, sel.captain, sel.cost (tenths)
```
It ignores selling prices and the cost of getting there: use it as a target to plan toward, then step 3
for the actual route. Chips are not modelled (the planner reports chips left only).

## 6. Freeze and score (builds the live track record)
```
fpl blind-pick --gw N --model          # freezes predictions + picks to data/processed/blind_gw<N>.json
                                       # (--model adds lgbm_xp fed ep; ~15 s to train; add --entry-id for your picks)
# ... after GW N finishes and the data has caught up:
fpl snapshot
fpl blind-score --gw N                 # achieved vs hindsight ceiling, captured fraction per predictor
fpl blind-score --all                  # all finished GWs with means
```
Freeze **before the first kickoff** or the comparison is not blind. Record the numbers in
[task-log.md](task-log.md); the live `ep` history is the only clean test of the `xp` question.

## Gotchas
- Season strings are `2026-27`; the CLI default `--season` is the current one.
- Prices are tenths of a million (`now_cost` 62 = 6.2m); `bank` too.
- `fpl.live` features for an unplayed GW come from TEMP tables; the main tables are untouched.
- Predictions are noisy per player (MAE about 1+ pts per player-GW); read differences of a few points
  across a squad as ties.
