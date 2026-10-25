# Task log (newest first)

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
