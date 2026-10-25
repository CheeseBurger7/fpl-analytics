# Project wiki

Goal: FPL team-selection platform: squad optimizer (ILP), transfer planner (multi-GW, hits, chips),
captain/differentials, explorer, historical analysis. Model: gradient-boosted expected points per
player, horizon 1-6 GWs, walk-forward backtest.

Repo: github.com/CheeseBurger7/fpl-analytics (public, MIT). Local: `C:\Projects\fpl-analytics`.

| Page | Contents |
|---|---|
| [status.md](status.md) | What exists, what is next, open questions. **Start here.** |
| [architecture.md](architecture.md) | Modules, public functions, CLI, how data flows |
| [data.md](data.md) | DuckDB tables, data gotchas, local data state |
| [decisions.md](decisions.md) | Modelling and evaluation decisions, with reasons |
| [task-log.md](task-log.md) | One entry per finished task / PR, newest first |

## Maintaining the wiki
At the end of every task, in the same PR as the code:
1. `task-log.md`: add an entry (date, branch/PR, what changed, results/numbers, caveats).
2. `status.md`: move the task from "Next" to "Done", refresh "Next" and "Open questions".
3. `architecture.md` / `data.md` / `decisions.md`: update only if the task changed them.
4. Record numbers (metrics, row counts) rather than adjectives. Never put secrets, the entry id or
   data files in the wiki.

Keep pages short; link to code (`src/fpl/...`) instead of copying it.
