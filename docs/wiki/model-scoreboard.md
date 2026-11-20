# Model scoreboard (live, blind) and transfer ledger

Purpose: rate each predictor on real gameweeks so future transfers can be weighed by which model has
earned trust. **Append to this page every GW** (see "Recording"). Metric definitions: [glossary.md](glossary.md).
Numbers come from `fpl blind-score --all` on the frozen `data/processed/blind_gw<N>.json` files
(freeze recipe: [running-predictions.md](running-predictions.md) step 6).

## 1. Scoreboard: fresh squad, captured fraction (achieved / hindsight ceiling)
"Fresh" = the predictor's own best 15 from scratch; the hindsight ceiling is the best squad on actuals.

| GW | ceiling | rolling_mean_5 | fpl_ep | lgbm | lgbm_xp(ep) |
|---|---|---|---|---|---|
| 8 | 145 | 47 = 0.324 | 88 = 0.607 | n/a (not frozen) | n/a (not in file; earlier run 0.828 was a different computation) |
| 9 | 130 | 58 = 0.446 | 72 = 0.554 | n/a (not frozen) | 59 = 0.454 |
| 10 | 148 | 81 = 0.547 | 69 = 0.466 | n/a (not frozen) | 59 = 0.399 |
| **Mean** | | 0.439 (n=3) | 0.542 (n=3) | none yet | 0.426 (n=2) |
| 11 | | | | | |

Same GWs only (GW9-10): rolling_mean_5 0.497, fpl_ep 0.510, lgbm_xp(ep) 0.426.
`lgbm` is frozen from GW11 on (`blind-pick --model`, fixed 2026-11-09); GW8-10 cannot be backfilled blind.

## 2. Scoreboard: the user's squad (`entry`), captured fraction
The predictor picks XI + captain from the user's actual squad. Only exists when the squad was stored
at freeze time. The frozen `manual` key is not scored by `blind-score` yet.

| GW | rolling_mean_5 | fpl_ep | lgbm | lgbm_xp(ep) |
|---|---|---|---|---|
| 8 | 69 / 78 = 0.885 | 72 / 78 = 0.923 | n/a | n/a |
| 9 | 69 / 88 = 0.784 | 69 / 88 = 0.784 | n/a | 78 / 88 = 0.886 |
| 10 | none (file held the GW9 squad) | none | n/a | none |

The user's real team is scored by `blind-score` as predictor `manual` (hand-added key in the frozen
file): GW10 48 / 71 = 0.676 (best XI + captain from the same 15, no auto-subs). Use it to see how much
lineup / captain choice cost, independent of which model was followed.

User's real points: GW8 63, GW9 77, GW10 48 (18 on the bench: Muharemović 10, Gomez 9, Davis -1).

## 3. Per-player accuracy (players predicted >= 1.0 pts; MAE and Spearman vs actual)
Printed by `fpl blind-score` since 2026-11-09 (`fpl.live.blind_accuracy`).

| GW | metric | rolling_mean_5 | fpl_ep | lgbm | lgbm_xp(ep) |
|---|---|---|---|---|---|
| 8 | n / MAE / Spearman | 282 / 2.42 / 0.206 | 230 / 2.22 / 0.210 | n/a | n/a |
| 9 | n / MAE / Spearman | 288 / 2.00 / 0.423 | 273 / 1.95 / 0.384 | n/a | 254 / 1.80 / 0.400 |
| 10 | n / MAE / Spearman | 299 / 2.13 / 0.327 | 279 / 2.22 / 0.317 | n/a | 268 / 2.18 / 0.245 |
| 11 | | | | | |

MAE and Spearman are within noise of each other on every GW so far; `lgbm_xp(ep)` had the best MAE in
GW9 and the worst Spearman in GW10.

## 4. Transfer ledger: which model proposed what, and what happened
Record each real transfer and the plan lines of every model at decision time, then fill "realised" once
the horizon is over (compare the transfer's player points with the sold player's, not with the model total).

| GW | Real transfer | Proposed by | Predicted gain (horizon) | Realised |
|---|---|---|---|---|
| 10 | Gibbs-White -> Mbeumo | `lgbm` (+5.0 over GW10-12; `fpl_ep` did not propose it) | +5.0 over GW10-12 (Mbeumo 15.4 vs Gibbs-White 9.6) | GW10: Mbeumo 2, Gibbs-White 5 (-3). GW11-12 pending |
| 11 | Calvert-Lewin -> N.Jackson (recommended 2026-11-09; user to confirm) | `lgbm` +5.9, `fpl_ep` +20.0, `rolling_mean_5` +18.4 (all best 1-transfer); `lgbm_xp` proposed Rogers -> Neto instead | +5.9 (`lgbm`) over GW11-14 | pending |

Rerun 2026-11-20 (snapshot 16, same squad / bank): `lgbm` and `rolling_mean_5` unchanged (207.1 -> 212.9;
305.6 -> 324.0, 2-transfer best Calafiori + Calvert-Lewin -> Vuskovic + N.Jackson +4 net). `fpl_ep` 306.8 ->
340.0 (+33.2), best 2 = Calvert-Lewin + Haaland -> N.Jackson + Barry (+16 net over 1). `lgbm_xp` 216.1 -> 248.5,
best 2 = Calafiori + Haaland -> Gabriel + N.Jackson (+17.4 net). GW11 captains: `lgbm` Palmer 5.52, `fpl_ep` /
`lgbm_xp` N.Jackson (11.0 / 9.6), `rolling_mean_5` Konsa 9.0. Frozen as `blind_gw11.json`.

Model plans at the GW11 decision (snapshot 15, squad = GW10 picks, bank 1.6m, 1 free, GW11-14): 0 transfers
`lgbm` 207.1 / `fpl_ep` 323.2 / `rolling_mean_5` 305.6 / `lgbm_xp` 289.5. 2 transfers (one hit): `lgbm`
Calafiori + Calvert-Lewin -> Tarkowski + N.Jackson +6.1 (net +0.3 over the single transfer); `fpl_ep`
Palmer + Calvert-Lewin -> Ayari + N.Jackson (+10 net); `rolling_mean_5` Calafiori + Calvert-Lewin ->
Vuskovic + N.Jackson (+4 net); `lgbm_xp` Rogers + Palmer -> Neto + Iwobi. Captain GW11: `lgbm` Palmer
5.5 (Haaland 5.3), `fpl_ep` / `rolling_mean_5` Konsa, `lgbm_xp` Evanilson.

Model plans at the GW10 decision (2026-11-03/05): `lgbm` Gibbs-White -> Mbeumo +5.0; `fpl_ep`
Calvert-Lewin -> N.Jackson +12.0 (totals ~80 above `lgbm`, compare differences only); `lgbm_xp` Davis ->
De Cuyper (+49.5 for 3 transfers: not credible).

GW10 outcomes for the other candidates (actual vs [rolling_mean_5 / fpl_ep / lgbm_xp] predicted):
- N.Jackson 11 [7.8 / 8.2 / 7.5]; Calvert-Lewin 2 [3.4 / 2.8 / 2.8]: `fpl_ep`'s transfer would have gained 9.
- Vuskovic 12 [6.8 / 6.5 / 5.1]; De Cuyper 6 [7.4 / 7.8 / 9.6]; Davis -1 [1.2 / 1.0 / 1.2].
- Mbeumo 2 [4.2 / 4.8 / 6.8]; Gibbs-White 5 [1.6 / 1.5 / 2.1] (he was predicted very low).
- Groß 10 [5.4 / 3.2 / 3.4].
One GW per line: do not conclude from a single row. The ledger exists so the sums over many GWs are honest.

## 5. Reading the evidence so far (2026-11-09)
- `fpl_ep` leads on fresh squads over 3 GWs (0.542), but its per-player ranking is no better than
  `rolling_mean_5` (GW10 Spearman 0.317 vs 0.327), and it is flat across the horizon (ignores fixtures).
- `lgbm_xp(ep)` trails both baselines on fresh squads (0.426 over 2 GWs) and has the weakest ranking.
- `lgbm` (what `fpl transfers` uses) has no live score; the first one arrives with GW11.
- Backtest numbers (leak-free `lgbm` 0.38-0.42, `xp` leaks) are in [decisions.md](decisions.md); live
  scores here are the only clean test. A difference needs several GWs (10+) before it is more than noise.

## 6. Recording (every GW, same PR as the wiki update)
1. Before kickoff: `fpl snapshot`, then `fpl blind-pick --gw N --model` (adds `lgbm` and `lgbm_xp(ep)`);
   check all four predictors printed. If the user made a transfer not yet stored, add it to the file under
   `manual` (xi / captain / bench) as for GW10.
2. After the GW: `fpl snapshot`, `fpl history`, `fpl blind-score --gw N`, `--all`. Add rows to sections 1-2
   and update the means. Add the user's real points (from `entry_gameweeks`) and the `manual` XI score.
3. Section 3 is printed by `blind-score` (`per-player` lines); copy n / MAE / Spearman. The `manual` line
   gives the user's own team (needs the `manual` key in the frozen file).
4. Section 4: when a transfer is chosen, add a row with every model's plan line; when its horizon ends,
   fill "Realised". Also note transfers each model proposed but the user did not make (counterfactual).
5. Never put the entry id or `data/` files in this page.
