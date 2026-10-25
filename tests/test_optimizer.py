from __future__ import annotations

import random
from collections import Counter

import pytest

from fpl.backtest import ColumnPredictor, ConstantPredictor, load_dataset, run_backtest
from fpl.optimizer import (
    MAX_PER_CLUB,
    SQUAD_QUOTA,
    XI_BOUNDS,
    CapturedFractionHook,
    InfeasibleError,
    Player,
    optimize_squad,
    pick_lineup,
    score_selection,
)
from fpl.store import HIST_GW_COLUMNS, Store


def _pool(seed=0, n=150):
    rng = random.Random(seed)
    pos = [1] * 20 + [2] * 50 + [3] * 55 + [4] * 25
    return [
        Player(i, pos[i % len(pos)], rng.randint(1, 12), rng.randint(40, 130),
               round(rng.uniform(0, 9), 2))
        for i in range(n)
    ]


def _check_legal(players, sel, budget=1000):
    by_id = {p.id: p for p in players}
    squad = [by_id[i] for i in sel.squad]
    assert len(set(sel.squad)) == 15
    assert Counter(p.position for p in squad) == SQUAD_QUOTA
    assert max(Counter(p.team for p in squad).values()) <= MAX_PER_CLUB
    assert sel.cost == sum(p.price for p in squad) <= budget
    assert len(sel.xi) == 11 and set(sel.xi) <= set(sel.squad)
    counts = Counter(by_id[i].position for i in sel.xi)
    for pos, (lo, hi) in XI_BOUNDS.items():
        assert lo <= counts[pos] <= hi
    assert sel.captain in sel.xi
    assert len(sel.bench) == 4


@pytest.mark.parametrize("seed", range(4))
def test_selection_is_legal(seed):
    pool = _pool(seed)
    _check_legal(pool, optimize_squad(pool))


def test_captain_is_the_best_xi_player_and_counts_twice():
    pool = _pool(1)
    sel = optimize_squad(pool)
    pts = {p.id: p.points for p in pool}
    assert pts[sel.captain] == max(pts[i] for i in sel.xi)
    assert score_selection(sel, pts) == pytest.approx(
        sum(pts[i] for i in sel.xi) + pts[sel.captain])


def test_budget_binds_and_unconstrained_beats_constrained():
    pool = _pool(2)
    loose = optimize_squad(pool, budget=10_000, bench_weight=0)
    tight = optimize_squad(pool, budget=700, bench_weight=0)
    _check_legal(pool, tight, budget=700)
    assert loose.objective > tight.objective


def test_budget_forces_cheaper_but_worse_pick():
    # one star at 13.0 can't fit alongside a full set of 4.0 fillers at a 100.0 budget
    pool = [Player(i, 1, 100 + i, 40, 1.0) for i in range(3)]
    pool += [Player(10 + i, 2, 110 + i, 40, 1.0) for i in range(6)]
    pool += [Player(20 + i, 3, 120 + i, 40, 1.0) for i in range(6)]
    pool += [Player(30 + i, 4, 130 + i, 40, 1.0) for i in range(4)]
    pool.append(Player(99, 4, 199, 450, 20.0))  # 45.0m star: 14 others cost 56.0 > 55.0 left
    sel = optimize_squad(pool, budget=1000)
    assert 99 not in sel.squad
    assert 99 in optimize_squad(pool, budget=1100).squad


def test_club_cap_limits_a_stacked_team():
    pool = [Player(i, 1 + i % 4 if i % 4 else 4, 1, 40, 9.0) for i in range(40)]
    pool += [p for p in _pool(3)]  # shift ids below
    pool = [Player(i, p.position, p.team, p.price, p.points) for i, p in enumerate(pool)]
    sel = optimize_squad(pool)
    assert sum(1 for i in sel.squad if pool[i].team == 1) <= 3


def test_fixed_squad_only_chooses_lineup_and_captain():
    pool = _pool(4)
    squad = optimize_squad(pool).squad
    # reward different players, then pick the best XI of the same 15
    changed = [Player(p.id, p.position, p.team, p.price, 9 - p.points) for p in pool]
    sel = pick_lineup(changed, squad)
    assert set(sel.squad) == set(squad)
    _check_legal(pool, sel, budget=10**9)
    best = max(sel.xi, key=lambda i: changed[i].points)
    assert changed[sel.captain].points == changed[best].points


def test_infeasible_and_bad_input():
    pool = _pool(5)
    with pytest.raises(InfeasibleError):
        optimize_squad(pool, budget=100)
    with pytest.raises(ValueError, match="duplicate"):
        optimize_squad(pool + [pool[0]])
    with pytest.raises(ValueError, match="not in player pool"):
        pick_lineup(pool, [10_000])


# ---- captured-fraction hook against a tiny in-memory season ----


def _gw_row(element, fixture, rnd, kickoff, pts, value):
    row = dict.fromkeys(HIST_GW_COLUMNS)
    row.update(
        season="2022-23", element_id=element, fixture_id=fixture, round=rnd, opponent_team=1,
        was_home=True, kickoff_time=kickoff, team_h_score=1, team_a_score=0, minutes=90,
        total_points=pts, value=value,
    )
    return tuple(row[c] for c in HIST_GW_COLUMNS)


@pytest.fixture
def season_data():
    rng = random.Random(7)
    layout = [1] * 3 + [2] * 7 + [3] * 7 + [4] * 4  # 21 players over 8 clubs
    teams = [("2022-23", t, f"T{t}") for t in range(1, 9)]
    players = [("2022-23", i, 1000 + i, f"P{i}", None, None, 1 + i % 8, pos)
               for i, pos in enumerate(layout, start=1)]
    rows = []
    for rnd, day in ((1, 6), (2, 13), (3, 20)):
        for i in range(1, len(layout) + 1):
            rows.append(_gw_row(i, rnd * 100 + i, rnd, f"2022-08-{day:02d} 14:00:00",
                                rng.randint(0, 12), 45))
    with Store() as s:
        s.replace_hist_season("2022-23", teams, players, rows)
        yield s.con, load_dataset(s.con)


def test_perfect_predictor_captures_everything(season_data):
    con, data = season_data
    preds = [ColumnPredictor("oracle", "target"), ConstantPredictor("flat", 1.0)]
    res = run_backtest(data, preds, ["2022-23"], step=None, min_history=0,
                       hooks=[CapturedFractionHook(con)])
    by = {(m.predictor, m.round): m.extra for m in res.gw_metrics}
    for rnd in (1, 2, 3):
        assert by[("oracle", rnd)]["captured_fraction"] == pytest.approx(1.0)
        flat = by[("flat", rnd)]
        assert flat["ceiling_points"] == by[("oracle", rnd)]["ceiling_points"]
        assert flat["achieved_points"] <= flat["ceiling_points"]
    summary = {r["predictor"]: r for r in res.summary()}
    assert summary["oracle"]["captured_fraction"] == pytest.approx(1.0)
    assert summary["flat"]["captured_fraction"] < 1.0
