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
| 11 | 154 | 27 = 0.175 | 55 = 0.357 | 40 = 0.260 | 58 = 0.377 |
| **Mean** | | 0.373 (n=4) | 0.496 (n=4) | 0.260 (n=1) | 0.410 (n=3) |

Same GWs only (GW9-11): rolling_mean_5 0.389, fpl_ep 0.459, lgbm_xp(ep) 0.410.
GW11 was a low-predictability week: top scorers were mostly predicted 1-3 pts (Lewis-Potter 16, Okafor 15,
Williams-Barnett 13, Ngumoha 13); every fresh XI started Gabriel (1) and N.Jackson (2, captain for two models).
`lgbm` is frozen from GW11 on (`blind-pick --model`, fixed 2026-11-09); GW8-10 cannot be backfilled blind.

## 2. Scoreboard: the user's squad (`entry`), captured fraction
The predictor picks XI + captain from the user's actual squad. Only exists when the squad was stored
at freeze time. The frozen `manual` key is scored by `blind-score` as predictor `manual`.

| GW | rolling_mean_5 | fpl_ep | lgbm | lgbm_xp(ep) |
|---|---|---|---|---|
| 8 | 69 / 78 = 0.885 | 72 / 78 = 0.923 | n/a | n/a |
| 9 | 69 / 88 = 0.784 | 69 / 88 = 0.784 | n/a | 78 / 88 = 0.886 |
| 10 | none (file held the GW9 squad) | none | n/a | none |
| 11 | 37 / 54 = 0.685 | 38 / 54 = 0.704 | 44 / 54 = 0.815 | 46 / 54 = 0.852 |

GW11 `entry` row computed by hand (not in the frozen file: the squad was not stored at freeze time):
`pick_lineup` on each predictor's frozen GW11 predictions over the user's real 15. Captains: Konsa (1) for
three models, Palmer (2) for `lgbm`.

The user's real team is scored by `blind-score` as predictor `manual` (hand-added key in the frozen
file): GW10 48 / 71 = 0.676, GW11 44 / 54 = 0.815 (best XI + captain from the same 15, no auto-subs).
GW11 hindsight: Calvert-Lewin (9) as captain instead of Haaland (2) was the main gap (+7). Use it to see how much
lineup / captain choice cost, independent of which model was followed.

User's real points: GW8 63, GW9 77, GW10 48 (18 on the bench: Muharemović 10, Gomez 9, Davis -1), GW11 44
(6 on the bench; overall rank 1.93m -> 1.61m).

## 3. Per-player accuracy (players predicted >= 1.0 pts; MAE and Spearman vs actual)
Printed by `fpl blind-score` since 2026-11-09 (`fpl.live.blind_accuracy`).

| GW | metric | rolling_mean_5 | fpl_ep | lgbm | lgbm_xp(ep) |
|---|---|---|---|---|---|
| 8 | n / MAE / Spearman | 282 / 2.42 / 0.206 | 230 / 2.22 / 0.210 | n/a | n/a |
| 9 | n / MAE / Spearman | 288 / 2.00 / 0.423 | 273 / 1.95 / 0.384 | n/a | 254 / 1.80 / 0.400 |
| 10 | n / MAE / Spearman | 299 / 2.13 / 0.327 | 279 / 2.22 / 0.317 | n/a | 268 / 2.18 / 0.245 |
| 11 | n / MAE / Spearman | 298 / 2.37 / 0.266 | 271 / 2.43 / 0.281 | 307 / 2.12 / 0.328 | 263 / 2.22 / 0.318 |

MAE and Spearman are within noise of each other on every GW so far; `lgbm_xp(ep)` had the best MAE in
GW9 and the worst Spearman in GW10. GW11 (first live `lgbm`): `lgbm` best on both MAE and Spearman, yet
its fresh squad was the second worst (40): per-player accuracy and squad captured fraction disagree.

## 4. Transfer ledger: which model proposed what, and what happened
Record each real transfer and the plan lines of every model at decision time, then fill "realised" once
the horizon is over (compare the transfer's player points with the sold player's, not with the model total).

| GW | Real transfer | Proposed by | Predicted gain (horizon) | Realised |
|---|---|---|---|---|
| 10 | Gibbs-White -> Mbeumo | `lgbm` (+5.0 over GW10-12; `fpl_ep` did not propose it) | +5.0 over GW10-12 (Mbeumo 15.4 vs Gibbs-White 9.6) | GW10: Mbeumo 2, Gibbs-White 5 (-3). GW11: Mbeumo 1 (21 min), Gibbs-White 2 (-1). Running -4, GW12 pending |
| 11 | **None** (user kept Calvert-Lewin, rolled the free transfer; counterfactual: Calvert-Lewin -> N.Jackson) | `lgbm` +5.9, `fpl_ep` +20.0, `rolling_mean_5` +18.4 (all best 1-transfer); `lgbm_xp` proposed Rogers -> Neto instead | +5.9 (`lgbm`) over GW11-14 if made | GW11: Calvert-Lewin 9, N.Jackson 2: holding gained +7. GW12-14 pending |
| 12 | **Raya -> A.Becker, Mbeumo -> Wirtz** (both free, made 2026-11-27; bank ~2.5m) | Hybrid of `lgbm` (keeper: Raya shoulder 50%) and the `ep` models (Wirtz); cross-scored on snapshot 19: `lgbm` +7.5, `fpl_ep` +37.6, `rolling_mean_5` +14.0, `lgbm_xp` +33.3. Rejected: `lgbm`'s Raya + Calafiori -> A.Becker + Gabriel (+10.5, ~0.2m short), Palmer -> B.Fernandes, Mbeumo -> Groß | +7.5 (`lgbm`) over GW12-15 | pending: A.Becker + Wirtz vs Raya + Mbeumo GW12-15 |

Model plans at the GW12 decision (2026-11-25, snapshot 17, squad = GW11 picks, bank 1.6m, 2 free, GW12-15;
hold = `lgbm` 200.6 / `fpl_ep` 262.0 / `rolling_mean_5` 291.6 / `lgbm_xp` 175.0). Best per model: `lgbm` Raya +
Calafiori -> A.Becker + Gabriel (+10.5; bank 0.2 at `now_cost`, about -0.2 after selling prices: Raya bought 6.0,
sells 6.1); `fpl_ep` Mbeumo + Bentley -> Wirtz + Roefs (+48.4; `lgbm` +4.9); `rolling_mean_5` Palmer + Davis ->
Wirtz + Hill (+34.4); `lgbm_xp` Haaland + Mbeumo -> Barry + Wirtz (+43.5). Cross-scored gains (lgbm / fpl_ep /
rm5 / lgbm_xp): `lgbm` plan +10.5 / +12.0 / +13.2 / +7.6; Raya + Mbeumo -> A.Becker + Wirtz +6.4 / +37.6 / +14.0 /
+33.6 (bank ~2.6); Mbeumo -> Wirtz alone +2.6 / +28.4 / +16.8 / +27.0; 3 with a hit (+Calafiori -> Gabriel)
+9.0 / +36.4 / +26.0 / +29.6. Context: Raya shoulder 50%, Bentley 0 minutes all season, Davis calf 75%;
Calvert-Lewin -> N.Jackson no longer in any plan. GW12 captain: `lgbm` Haaland 5.0 (at ARS, FDR 5), the
`ep` models Wirtz.

Palmer -> B.Fernandes checked 2026-11-26 (snapshot 18; Raya now 6.2, still 50%): Bruno 11.6m vs Palmer 9.8m,
GW12-15 `lgbm` 20.6 vs 20.2. Alone it is ~0.2m short and +0.9 / +2.8 / +0.0 / +8.9 (lgbm / fpl_ep / rm5 /
lgbm_xp). With Raya -> A.Becker +5.2 / +12.0 / -2.8 / +15.5; with Mbeumo -> Wirtz +3.5 / +30.0 / +16.8 / +35.9;
the Raya + Mbeumo -> A.Becker + Wirtz recommendation is +6.9 / +37.6 / +14.0 / +33.6 on the same snapshot. Palmer's
fixtures turn hard in GW14-15 (LIV h, MCI a) vs Bruno COV h, CRY a: revisit then, not now.

GW12 frozen 2026-11-27 (snapshot 20, `blind_gw12.json`, all four predictors; squad in the file = GW11 picks, so no
`entry` rows). Lineup for the new squad from the frozen predictions: `lgbm` captain Haaland 5.0 (Wirtz 4.9), bench
Bentley, Gomez, Muharemović, Davis; `fpl_ep` / `lgbm_xp` captain Wirtz; `rolling_mean_5` Konsa. Davis back to 100%.

Mbeumo -> Groß checked 2026-11-27 (snapshot 19): Groß 6.3m, GW12-15 `lgbm` 19.1 vs Wirtz 19.5 / Mbeumo 16.4.
Gains (lgbm / fpl_ep / rm5 / lgbm_xp): Mbeumo -> Groß +2.7 / +5.2 / +1.6 / +3.1 vs -> Wirtz +3.2 / +28.4 / +16.8 / +26.7;
Raya + Mbeumo -> A.Becker + Groß +7.0 / +14.4 / -1.2 / +9.7 (bank 3.7) vs + Wirtz +7.5 / +37.6 / +14.0 / +33.3 (bank 2.5).
Mbeumo + Palmer -> Groß + B.Fernandes (affordable, bank 1.3) only +1.8 / +5.2 / +1.6 / +4.2. Wirtz beats Groß under
every model; Groß's only edge is 1.2m more bank.

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

## 5. Reading the evidence so far (2026-11-25, after GW11)
- `fpl_ep` leads on fresh squads over 4 GWs (0.496), but its per-player ranking is no better than the
  others (Spearman 0.21-0.38 for every model), and it is flat across the horizon (ignores fixtures).
- `lgbm_xp(ep)` is second on fresh squads (0.410, n=3) and best on the user's squad (GW9 0.886, GW11 0.852).
- `lgbm` (what `fpl transfers` uses): first live GW11 = worst-but-one fresh (0.260) and best per-player
  (MAE 2.12, Spearman 0.328). One GW; no conclusion yet.
- Lineup choice from the user's squad: models captured 0.69-0.85 in GW11, the user 0.815.
- Backtest numbers (leak-free `lgbm` 0.38-0.42, `xp` leaks) are in [decisions.md](decisions.md); live
  scores here are the only clean test. A difference needs several GWs (10+) before it is more than noise.

## 6. Recording (every GW, same PR as the wiki update)
1. Before kickoff: `fpl snapshot`, then `fpl blind-pick --gw N --model` (adds `lgbm` and `lgbm_xp(ep)`);
   check all four predictors printed. If the user made a transfer not yet stored, add it to the file under
   `manual` (xi / captain / bench) as for GW10. After the deadline, rebuild `manual` from `entry_picks`
   (the GW11 hand entry had two wrong ids: the 4.0m GK Palmer (301) and DEF Gomez (359), and a stale XI;
   `blind-score` then fails with an infeasible lineup).
2. After the GW: `fpl snapshot`, `fpl history`, `fpl blind-score --gw N`, `--all`. Add rows to sections 1-2
   and update the means. Add the user's real points (from `entry_gameweeks`) and the `manual` XI score.
3. Section 3 is printed by `blind-score` (`per-player` lines); copy n / MAE / Spearman. The `manual` line
   gives the user's own team (needs the `manual` key in the frozen file).
4. Section 4: when a transfer is chosen, add a row with every model's plan line; when its horizon ends,
   fill "Realised". Also note transfers each model proposed but the user did not make (counterfactual).
5. Never put the entry id or `data/` files in this page.
