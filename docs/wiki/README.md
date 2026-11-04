# Project wiki

Goal: FPL team-selection platform: squad optimizer (ILP), transfer planner (multi-GW, hits, chips),
captain/differentials, explorer, historical analysis. Model: gradient-boosted expected points per
player, horizon 1-6 GWs, walk-forward backtest.

Repo: github.com/CheeseBurger7/fpl-analytics (public, MIT). Local: `C:\Projects\fpl-analytics`.

| Page | Contents |
|---|---|
| [status.md](status.md) | What exists, what is next, open questions. **Start here.** |
| [running-predictions.md](running-predictions.md) | How to run predictions, lineup and transfers for any upcoming GW (commands, steps) |
| [architecture.md](architecture.md) | Modules, public functions, CLI, how data flows |
| [data.md](data.md) | DuckDB tables, data gotchas, local data state |
| [glossary.md](glossary.md) | Meaning of xp, ep, lgbm, MAE, Spearman, captured fraction; which metric to target |
| [decisions.md](decisions.md) | Modelling and evaluation decisions, with reasons |
| [task-log.md](task-log.md) | Next task, improvement ideas, open questions (forward-looking; no history) |

## Maintaining the wiki
At the end of every task, in the same PR as the code:
1. `status.md`: add the PR to "Done" (one line with the key numbers), refresh "Next" and "Open questions".
2. `task-log.md`: keep only the next task, improvement ideas and open questions; delete what is done.
3. `architecture.md` / `data.md` / `decisions.md`: update only if the task changed them (conclusions
   and numbers go in `decisions.md`, not in a log).
4. Record numbers (metrics, row counts) rather than adjectives. Never put secrets, the entry id or
   data files in the wiki.

Keep pages short; link to code (`src/fpl/...`) instead of copying it.
