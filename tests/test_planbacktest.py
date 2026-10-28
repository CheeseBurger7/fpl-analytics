from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fpl.backtest import ColumnPredictor, Dataset
from fpl.features import FEATURE_COLUMNS
from fpl.planbacktest import (
    HOLD,
    PLANNER,
    GwInput,
    Policy,
    autosub_points,
    chip_gains,
    chip_week_points,
    horizon_points,
    next_free_transfers,
    season_inputs,
    selling_price,
    simulate,
    start_squad,
)

POS = [1] * 2 + [2] * 5 + [3] * 5 + [4] * 3
# ids 1-15 form a legal squad (price 50, club = id % 5); 16 is a strong midfielder, 17 a pricey one
INFO = {i + 1: (POS[i], (i % 5) + 1) for i in range(15)} | {16: (3, 6), 17: (3, 7)}
PRICE = {i: 50 for i in range(1, 17)} | {17: 90}


def _gw(rnd: int, pred: dict[int, float], actual: dict[int, float] | None = None, fixtures=None):
    base = {i: 3.0 for i in range(1, 16)}
    pred = base | pred
    return GwInput(
        ("s", rnd), pred, fixtures or {i: 1 for i in pred}, PRICE, actual or dict(pred),
    )  # fmt: skip


def _start():
    first = _gw(1, {})
    sel, bank = start_squad(first, INFO)
    return sel, bank


def test_free_transfer_bookkeeping():
    assert next_free_transfers(1, 0) == 2  # banked
    assert next_free_transfers(1, 1) == 1
    assert next_free_transfers(2, 3) == 1  # hit transfers do not go negative
    assert next_free_transfers(5, 0) == 5  # capped


def test_hold_never_transfers_and_scores_actuals():
    gws = [_gw(1, {}), _gw(2, {16: 9.0}, {16: 9.0} | {i: 1.0 for i in range(1, 16)})]
    run = simulate(gws, INFO, HOLD)
    assert run.transfers == 0 and run.hits == 0
    # GW1 starting squad from predictions: the 16 players have equal predictions, XI of 3s + captain
    assert run.results[0].points == pytest.approx(12 * 3.0)
    assert run.results[1].points == pytest.approx(12 * 1.0)  # actuals, not the 3.0 prediction


def test_planner_transfers_from_second_gw_and_accounts_free_transfers_and_hits():
    gws = [_gw(1, {}), _gw(2, {16: 8.0, 10: 1.0}), _gw(3, {16: 8.0, 10: 1.0, 9: 1.0, 17: 9.0})]
    sel, bank = _start()
    run = simulate(gws, INFO, Policy("p", max_transfers=2, margin=0.0), start=(sel, 1000 - 750 + 0))
    r1, r2, r3 = run.results
    assert r1.transfers == 0 and r1.free_transfers == 1  # no transfers in the first gameweek
    assert r2.free_transfers == 2  # the unused one banked
    assert r2.hit == 0 and r2.transfers >= 1
    assert r3.hit == 4 * max(0, r3.transfers - r3.free_transfers)
    assert r1.bank == 250 and r2.bank + sum(PRICE[i] for i in r2.into) == r1.bank + sum(
        PRICE[i] for i in r2.out
    )  # fmt: skip


def test_scoring_ignores_actuals_when_choosing():
    # the prediction says 16 is great, the actual says 0: the planner still buys him and scores 0
    gws = [_gw(1, {}), _gw(2, {16: 9.0, 10: 0.5}, {16: 0.0} | {i: 3.0 for i in range(1, 16)})]
    sel, _ = _start()
    run = simulate(gws, INFO, PLANNER, start=(sel, 250))
    assert 16 in run.results[1].into
    assert run.results[1].points < 12 * 3.0


def test_persistence_uses_known_fixture_counts_for_later_gameweeks():
    gws = [
        _gw(1, {16: 6.0}, fixtures={16: 1}),
        _gw(2, {}, fixtures={16: 2, 1: 0}),  # 16 has a double, 1 blanks
        _gw(3, {}, fixtures={16: 0}),
    ]
    pts = horizon_points(gws, 0, 3, {16: 6.0, 1: 3.0})
    assert pts[0][16] == 6.0
    assert pts[1][16] == 12.0 and pts[1][1] == 0.0
    assert pts[2][16] == 0.0
    assert len(horizon_points(gws, 2, 5, {})) == 1  # truncated at the end of the season


def _dataset(n_prior: int = 5) -> Dataset:
    """Two gameweeks of one season, players 1-3, each one fixture per gameweek."""
    t0 = datetime(2025, 8, 1)
    rows = []
    for rnd in (1, 2):
        for el in (1, 2, 3):
            rows.append({
                "season": "s", "round": rnd, "gw_ordinal": rnd, "gw_start": t0 + timedelta(7 * rnd),
                "kickoff_time": t0 + timedelta(7 * rnd, hours=el), "element_id": el,
                "fixture_id": rnd * 10 + el, "target": float(el * rnd), "xp": float(el),
                "n_prior_fixtures": n_prior,
            })  # fmt: skip
    cols = {k: [r.get(k) for r in rows] for k in rows[0]}
    for c in FEATURE_COLUMNS:
        cols.setdefault(c, [None] * len(rows))
    return Dataset(cols)


def test_season_inputs_builds_gameweeks_from_walk_forward_data(store):
    store.con.execute(
        "INSERT INTO hist_players (season, element_id, code, position, team_id) "
        "VALUES ('s', 1, 101, 1, 1), ('s', 2, 102, 3, 2), ('s', 3, 103, 4, 3)"
    )
    data = _dataset()
    for rnd in (1, 2):
        for el in (1, 2, 3):
            store.con.execute(
                "INSERT INTO hist_player_gw (season, element_id, round, fixture_id, kickoff_time, "
                "value) VALUES ('s', ?, ?, ?, ?, ?)",
                [el, rnd, rnd * 10 + el, data.columns["kickoff_time"][(rnd - 1) * 3 + el - 1],
                 40 + 10 * el + rnd],
            )  # fmt: skip
    out, info = season_inputs(data, [ColumnPredictor("fpl_xp", "xp")], "s", store.con)
    gws = out["fpl_xp"]
    assert info == {1: (1, 1), 2: (3, 2), 3: (4, 3)}
    assert [g.key for g in gws] == [("s", 1), ("s", 2)]
    assert gws[1].predicted == {1: 1.0, 2: 2.0, 3: 3.0}  # xp, known before the gameweek
    assert gws[1].actual == {1: 2.0, 2: 4.0, 3: 6.0}
    assert gws[1].fixtures == {1: 1, 2: 1, 3: 1}
    assert gws[1].price[1] == 52 and gws[0].price[1] == 51
    cold, _ = season_inputs(_dataset(n_prior=2), [ColumnPredictor("fpl_xp", "xp")], "s", store.con)
    assert cold["fpl_xp"] == []  # cold starts are masked; rounds without a forecast are skipped


def test_selling_price_keeps_half_of_a_rise_rounded_down():
    assert selling_price(50, 50) == 50
    assert selling_price(50, 53) == 51  # +3 -> +1
    assert selling_price(50, 54) == 52
    assert selling_price(50, 47) == 47  # falls are lost in full


def test_sell_price_limits_what_a_sale_funds():
    gws = [_gw(1, {}), _gw(2, {16: 9.0})]
    g2 = gws[1]
    gws[1] = GwInput(g2.key, g2.predicted, g2.fixtures, PRICE | {1: 60, 16: 60}, g2.actual)
    sel, bank = start_squad(gws[0], INFO)
    run = simulate(gws, INFO, Policy("p", max_transfers=1, margin=0.0), start=(sel, 0))
    # player 1 rose 50 -> 60 but only 55 is banked: selling him cannot fund a 60 midfielder
    assert 16 not in run.results[1].into or 1 not in run.results[1].out


def test_autosubs_replace_non_playing_starter_and_respect_formation():
    pos = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3, 9: 3, 10: 4, 11: 4, 12: 3, 13: 2}
    info = {i: (p, i) for i, p in pos.items()}
    xi = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    bench = [2, 13]
    actual = {i: 2.0 for i in pos} | {13: 5.0, 2: 3.0, 11: 0.0, 10: 6.0}
    pred = {i: float(i) for i in pos}
    mins = {i: 90 for i in pos} | {11: 0}
    # forward 11 did not play; the bench defender comes on (4 DEF, 4 MID, 1 FWD is legal)
    pts = autosub_points(xi, 10, bench, info, pred, actual, mins)
    assert pts == pytest.approx(sum(actual[i] for i in xi if i != 11) + 5.0 + 6.0)
    # captain 10 absent: 13 subs in and, highest predicted among those who played, is vice
    mins2 = dict(mins) | {10: 0, 11: 90}
    pts2 = autosub_points(xi, 10, bench, info, pred, actual, mins2)
    assert pts2 == pytest.approx(sum(actual[i] for i in xi if i != 10) + 5.0 + 5.0)


def test_goalkeeper_only_replaced_by_goalkeeper():
    pos = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3, 9: 3, 10: 4, 11: 4, 12: 2}
    info = {i: (p, i) for i, p in pos.items()}
    xi, bench = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], [2]
    actual = {i: 1.0 for i in pos} | {2: 4.0, 1: 0.0}
    mins = {i: 90 for i in pos} | {1: 0}
    pts = autosub_points(xi, 10, bench, info, {i: 1.0 for i in pos}, actual, mins)
    assert pts == pytest.approx(10 * 1.0 + 4.0 + 1.0)


def test_horizon_points_prefers_ahead_predictions_over_persistence():
    first = _gw(1, {16: 6.0})
    first = GwInput(first.key, first.predicted, first.fixtures, first.price, first.actual,
                    ahead=({16: 2.5},))  # fmt: skip
    gws = [first, _gw(2, {16: 1.0}), _gw(3, {16: 1.0})]
    pts = horizon_points(gws, 0, 3, {16: 6.0})
    assert pts[1] == {16: 2.5}  # model-based
    assert pts[2][16] == 6.0  # persistence beyond the supplied horizon


# ------------------------------------------------------------------------------------- chips


def test_chip_gains_are_captain_points_and_bench_points():
    squad = list(range(1, 16))
    pts = [{i: 3.0 for i in squad} | {5: 7.0, 1: 1.0}]
    g = chip_gains(squad, INFO, pts, ["3xc", "bboost"])
    assert g["3xc"] == [7.0]
    # the bench is the weaker keeper (player 1, 1.0) and three outfielders at 3.0
    assert g["bboost"] == [pytest.approx(1.0 + 3 * 3.0)]


def test_chip_week_points():
    squad, xi = list(range(1, 16)), list(range(1, 12))
    gw = GwInput(("s", 1), {i: 2.0 for i in squad}, {i: 1 for i in squad}, PRICE,
                 {i: 2.0 for i in squad} | {5: 10.0})  # fmt: skip
    # triple captain: base (XI + captain doubled) plus the captain once more
    assert chip_week_points("3xc", 30.0, 0, squad, xi, 5, gw) == 40.0
    # bench boost: all 15 once (14 x 2 + 10) plus the captain's extra, less the hit
    assert chip_week_points("bboost", 30.0, 4, squad, xi, 5, gw) == 14 * 2 + 10 + 10 - 4
    # captain who did not play: the vice-captain (best predicted starter who played) takes it
    gw2 = GwInput(gw.key, {i: float(i) for i in squad}, gw.fixtures, PRICE, gw.actual,
                  minutes={i: 90 for i in squad if i != 5})  # fmt: skip
    assert chip_week_points("3xc", 0.0, 0, squad, xi, 5, gw2) == 2.0 * 0 + gw.actual[11]


def test_triple_captain_is_saved_for_the_double_gameweek():
    flat = {i: 1 for i in range(1, 16)}
    gws = [
        _gw(1, {5: 3.0}), _gw(2, {5: 3.0}),
        _gw(3, {5: 6.0}, fixtures=flat | {5: 2}),  # 5 plays twice, so the same rate scores 6
        _gw(4, {5: 3.0}),
    ]  # fmt: skip
    start = _start()
    hold = simulate(gws, INFO, HOLD, start=start)
    chip = simulate(gws, INFO, Policy("c", chips=("3xc",), chip_window=6), start=start)
    assert [r.chip for r in chip.results] == [None, None, "3xc", None]
    assert chip.total - hold.total == pytest.approx(6.0)  # the captain's points, once more
    # bench boost has the same shape and is also played at most once per half
    both = simulate(gws, INFO, Policy("c", chips=("3xc", "bboost")), start=start)
    assert sum(r.chip is not None for r in both.results) == 2
    assert {r.chip for r in both.results} - {None} == {"3xc", "bboost"}


def test_unused_chip_is_forced_in_the_last_gameweek_of_the_half():
    gws = [_gw(r, {5: 3.0 + (3 - r)}) for r in (1, 2, 3)]  # decaying: "now" is best at GW1
    run = simulate(gws, INFO, Policy("c", chips=("3xc",), chip_min=100.0), start=_start())
    assert [r.chip for r in run.results] == [None, None, "3xc"]  # min never met; forced at the end
