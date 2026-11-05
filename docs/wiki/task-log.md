# Task log: next task and improvements

Forward-looking only. Finished work lives in [status.md](status.md) (Done table, one line per PR) and
[decisions.md](decisions.md) (conclusions and numbers). The long per-task entries up to 2026-11-03 were
removed on 2026-11-04; recover them with `git log -p -- docs/wiki/task-log.md` (last full version: commit
`55b5c13`, plus the GW9 notes below).

## Next task: collect `ep`, then news / fixture-aware chip timing
Start from `main`; read `status.md`, `glossary.md`, `decisions.md`.
1. **Every GW (standing chore):** `fpl snapshot` before the deadline, `fpl blind-pick --gw N --model`
   before the first kickoff (add the user's squad as `entry`, see below), `fpl transfers --gw N`; after
   the GW `fpl snapshot`, `fpl blind-score --gw N` and `--all`. Record the numbers in `status.md`. The live
   `ep` history is the only clean test of the `xp` / `ep`-as-`xp` question; GW8-9 exist so far.
2. **GW10 (deadline after 2026-11-03):** transfer options for GW10-12 are below; the user had not decided.

## Current-GW notes (GW10-12, run 2026-11-03, squad = GW9 picks, bank 1.7, 1 free, bench boost left)
- `lgbm` (default): hold 150.7; best 1 transfer Gibbs-White -> Mbeumo 155.7 (+5.0); 2 transfers 155.3;
  3 transfers 154.1. Captain GW10 Haaland.
- `fpl_ep`: hold 232.5; Calvert-Lewin -> N.Jackson 244.5 (+12.0); best 3 transfers 253.0 (two hits, +3.5
  over 2). Captain Konsa. Totals run ~80 above `lgbm` (flat `ep`), compare differences only.
- `lgbm_xp`: Davis -> De Cuyper 181.2, best 3 transfers 200.4 (+49.5): not credible.
- No transfer is shared by `lgbm` and `fpl_ep`. Tiebreaker not done yet: fixtures for Mbeumo, Gibbs-White,
  N.Jackson, Calvert-Lewin over GW10-12 (the horizon ignores fixture difficulty).
- Gabriel (ARS DEF, 8.0m): `lgbm` 13.1 over GW10-12 (rank 6), `fpl_ep` 24.6 (rank 4), `lgbm_xp` 11.3
  (rank 40). Not affordable with 1.7 bank in any single defender swap (nearest: Calafiori, 0.4m short), and
  no planner line picks him. Arsenal FDR GW10-12: 2 / 3 / 4. Idea: free bank with a downgrade, then
  Calafiori -> Gabriel without a hit.
- GW9 blind-score (2026-11-03): see `status.md`. Plain `lgbm` was not in the GW9 freeze, so it is unscored.

## Improvements to consider (none started)
Model
- **Availability news as a trained feature:** snapshots hold `chance_of_playing_next_round` only from GW8;
  today it is a live multiplier on GW1 of `lgbm` / `rolling_mean_5`. Train on it once many GWs are stored.
- **Model trained on stored live `ep`** (`lgbm_ep`): needs many GWs of snapshots; vaastav has no clean
  historical `ep` (its `xp` / `xP{N}` files leak the GW result).
- **Fixture-aware later-GW predictions:** horizon > 1 is persistence x fixture count and ignores
  difficulty; a rating from `fixture_snapshots` difficulty fields is untried.
- Untried baselines: RF / Ridge, an ensemble. Odds features were no gain (+0.015, noise); if revisited:
  odds-only training from 2019-20, Poisson solve for xG instead of the linear Over/Under approximation.
  Live odds for upcoming GWs are not available until a few days before kickoff (check
  football-data `fixtures.csv`).
- Fix mid-season-mover team features (see `data.md`).
Planner / chips
- Chip timing: fixture-aware predictions so timing can beat "play early"; gain net of normal transfers;
  selling-price-aware chip squads. **No blank or double gameweeks exist yet** (every team plays once in
  each of the 38 GWs in snapshot 9); re-check after each snapshot before planning bench boost.
- Multi-step transfer plans; live selling prices from `entry` data (the backtest already models them).
- The planner backtest was not rerun after the DGW `xp` fix; absolute totals stay optimistic.
Tooling
- `fpl lineup` / `fpl squad` CLI command to replace the Python snippets in `running-predictions.md`.
- `blind-pick` cannot see a transfer not yet stored (no GW N picks until the deadline passes); add the
  user's squad to `entry` by hand, or let `blind-pick` take an explicit squad.
- Differentials and explorer (original scope).

## Open questions
- Does `ep`-as-`xp` (`lgbm_xp(ep)`) beat `fpl_ep` and `lgbm` over several GWs? GW8 0.828 vs 0.566 (fresh,
  different computation); GW9 fresh 0.454 vs 0.554. Needs more GWs.
- After `fpl entry` on 2026-10-30, `entry_transfers` had no GW9 row although the Pedro -> Evanilson
  transfer was made; unverified whether the public endpoint only lists transfers after the deadline.
