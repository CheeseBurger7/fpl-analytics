from __future__ import annotations

import pytest

from fpl.optimizer import Player
from fpl.planner import best_plan, evaluate_chips, plan_transfers

# 15-man squad (ids 1-15: 2 GK, 5 DEF, 5 MID, 3 FWD), one club each id % 5, price 50 each,
# plus bench-quality alternatives 16 (MID, strong) and 17 (MID, strong but pricey).
POS = [1] * 2 + [2] * 5 + [3] * 5 + [4] * 3


def _pool():
    players = [Player(i + 1, POS[i], (i % 5) + 1, 50, 0.0) for i in range(15)]
    players += [Player(16, 3, 6, 50, 0.0), Player(17, 3, 7, 90, 0.0)]
    return players


def _points(extra: dict[int, float]):
    pts = {i: 3.0 for i in range(1, 16)}
    pts[10] = 1.0  # a weak starting midfielder
    pts.update(extra)
    return pts


def test_zero_transfers_is_baseline_and_one_swap_improves():
    plans = plan_transfers(_pool(), [_points({16: 8.0})] * 2, range(1, 16), max_transfers=2)
    base, one = plans[0], plans[1]
    assert base.transfers == 0 and base.out == () and base.into == ()
    assert one.out == (10,) and one.into == (16,)
    assert one.hit == 0 and one.net > base.net  # 1 free transfer, 2 gameweeks of 8 vs 1
    assert one.xi[0] != () and len(one.xi) == len(one.captain) == 2


def test_hits_are_charged_beyond_free_transfers():
    pts = _points({16: 8.0, 17: 9.0})
    pts[9] = 1.0  # a second weak midfielder
    plans = plan_transfers(_pool(), [pts], range(1, 16), bank=40, free_transfers=1, max_transfers=2)
    two = plans[2]
    assert set(two.into) == {16, 17} and two.hit == 4
    assert two.net == pytest.approx(two.gross - 4)


def test_budget_blocks_unaffordable_transfer():
    pts = _points({17: 9.0})
    plans = plan_transfers(_pool(), [pts], range(1, 16), bank=0, max_transfers=1)
    assert all(17 not in p.into for p in plans)  # 90 > 50 sale price + 0 bank
    rich = plan_transfers(_pool(), [pts], range(1, 16), bank=40, max_transfers=1)
    assert 17 in rich[1].into
    assert rich[1].bank == 0


def test_best_plan_prefers_fewer_transfers_on_ties():
    plans = plan_transfers(_pool(), [_points({})], range(1, 16), max_transfers=2)
    assert best_plan(plans).transfers == 0


def test_best_plan_margin_ignores_marginal_extra_transfers():
    pts = _points({16: 8.0, 17: 7.5})
    pts[9] = 3.0  # second swap gains 4.5 points for a 4-point hit
    plans = plan_transfers(_pool(), [pts], range(1, 16), bank=40, max_transfers=2)
    assert best_plan(plans, margin=1.0).transfers == 1
    assert best_plan(plans, margin=0.0).net == max(p.net for p in plans)


def test_squad_must_be_in_pool():
    with pytest.raises(ValueError):
        plan_transfers(_pool(), [{}], range(100, 115))


# ------------------------------------------------------------------------------------- chips


def test_triple_captain_adds_the_captains_points_in_the_chosen_gameweek():
    gw0, gw1 = _points({}), _points({5: 9.0})
    base = plan_transfers(_pool(), [gw0, gw1], range(1, 16), max_transfers=0)[0]
    tc = plan_transfers(_pool(), [gw0, gw1], range(1, 16), max_transfers=0, chip="3xc",
                        chip_gw=1)[0]
    assert tc.captain[1] == 5 and tc.chip == "3xc" and tc.chip_gw == 1
    assert tc.net - base.net == pytest.approx(9.0)
    early = plan_transfers(_pool(), [gw0, gw1], range(1, 16), max_transfers=0, chip="3xc",
                           chip_gw=0)[0]
    assert early.net - base.net == pytest.approx(3.0)  # only a 3-point captain that week


def test_bench_boost_counts_the_bench():
    pts = _points({})
    base = plan_transfers(_pool(), [pts], range(1, 16), max_transfers=0)[0]
    bb = plan_transfers(_pool(), [pts], range(1, 16), max_transfers=0, chip="bboost")[0]
    bench = sum(pts[i] for i in range(1, 16)) - sum(pts[i] for i in base.xi[0])
    assert bench >= 4.0  # four bench players of at least 1 point each
    assert bb.net - base.net == pytest.approx(bench * 0.998, abs=1e-6)


def test_free_hit_uses_a_different_squad_for_one_gameweek_without_a_hit():
    weak = {9: 1.0, 16: 8.0, 17: 9.0}
    pts = [_points(weak), _points(weak)]
    plans = plan_transfers(_pool(), pts, range(1, 16), bank=40, free_transfers=0, max_transfers=0,
                           chip="freehit", chip_gw=1)
    (p,) = plans
    assert p.hit == 0 and {16, 17} <= set(p.chip_squad)
    assert set(p.squad) == set(range(1, 16))  # the real squad is untouched
    assert 16 not in p.xi[0] and 16 in p.xi[1]  # only the free-hit gameweek uses the new squad
    first = plan_transfers(_pool(), pts, range(1, 16), bank=40, max_transfers=3,
                           chip="freehit", chip_gw=0)
    assert len(first) == 1 and first[0].transfers == 0  # nothing to transfer in a free-hit week


def test_wildcard_squad_applies_from_its_gameweek_onwards():
    weak = {9: 1.0, 16: 8.0, 17: 9.0}
    pts = [_points(weak)] * 3
    (p,) = plan_transfers(_pool(), pts, range(1, 16), bank=40, free_transfers=0, max_transfers=0,
                          chip="wildcard", chip_gw=1)
    assert 16 not in p.xi[0] and 16 in p.xi[1] and 16 in p.xi[2]
    assert p.hit == 0


def test_evaluate_chips_ranks_options_by_gain_over_the_chip_free_plan():
    pts = [_points({}), _points({5: 20.0})]
    base, options = evaluate_chips(_pool(), pts, range(1, 16), ("3xc", "bboost"), max_transfers=0)
    assert base.chip is None
    assert [o.gain for o in options] == sorted((o.gain for o in options), reverse=True)
    assert (options[0].chip, options[0].gw) == ("3xc", 1)
    assert all(o.gain > 0 for o in options)


def test_bad_chip_arguments_are_rejected():
    with pytest.raises(ValueError):
        plan_transfers(_pool(), [{}], range(1, 16), chip="nope")
    with pytest.raises(ValueError):
        plan_transfers(_pool(), [{}], range(1, 16), chip="3xc", chip_gw=1)
