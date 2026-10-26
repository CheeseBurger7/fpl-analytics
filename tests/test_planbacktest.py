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
    horizon_points,
    next_free_transfers,
    season_inputs,
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
