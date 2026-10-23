from __future__ import annotations

import pytest

from fpl.features import FEATURE_COLUMNS, build_features
from fpl.store import HIST_GW_COLUMNS, Store


def _gw_row(season, element, fixture, rnd, kickoff, *, pts, minutes, opp=2, home=True, value=50,
            h=1, a=0):
    row = dict.fromkeys(HIST_GW_COLUMNS)
    row.update(
        season=season, element_id=element, fixture_id=fixture, round=rnd, opponent_team=opp,
        was_home=home, kickoff_time=kickoff, team_h_score=h, team_a_score=a, minutes=minutes,
        total_points=pts, value=value,
    )
    return tuple(row[c] for c in HIST_GW_COLUMNS)


@pytest.fixture
def store():
    with Store() as s:
        yield s


def _load(store, season, rows, element=10, code=111):
    teams = [(season, 1, "Arsenal"), (season, 2, "Brentford")]
    players = [(season, element, code, "Saka", None, None, 1, 3)]
    store.replace_hist_season(season, teams, players, rows)


def _features(store, season="2022-23"):
    rel = build_features(store.con)
    cols = ["fixture_id", "target", *FEATURE_COLUMNS]
    return {
        r[0]: dict(zip(cols, r, strict=True))
        for r in rel.filter(f"season = '{season}'").select(", ".join(cols)).fetchall()
    }


def test_features_use_only_earlier_gameweeks(store):
    rows = [
        _gw_row("2022-23", 10, 1, 1, "2022-08-06 14:00:00", pts=10, minutes=90),
        _gw_row("2022-23", 10, 2, 2, "2022-08-13 14:00:00", pts=2, minutes=60),
        _gw_row("2022-23", 10, 3, 3, "2022-08-20 14:00:00", pts=100, minutes=90),
    ]
    _load(store, "2022-23", rows)
    f = _features(store)
    assert f[1]["pts_per_fix_5"] is None and f[1]["n_prior_fixtures"] == 0
    assert f[2]["pts_per_fix_5"] == 10  # GW1 only
    assert f[3]["pts_per_fix_5"] == 6  # (10 + 2) / 2, never its own 100
    assert f[3]["mins_per_fix_5"] == 75


def test_changing_a_gameweeks_own_result_does_not_change_its_features(store):
    def run(points):
        rows = [
            _gw_row("2022-23", 10, 1, 1, "2022-08-06 14:00:00", pts=4, minutes=90),
            _gw_row("2022-23", 10, 2, 2, "2022-08-13 14:00:00", pts=points, minutes=0, h=5),
        ]
        with Store() as s:
            _load(s, "2022-23", rows)
            f = _features(s)[2]
        return {k: v for k, v in f.items() if k != "target"}

    assert run(1) == run(20)


def test_double_gameweek_fixtures_share_the_same_pre_gameweek_information(store):
    rows = [
        _gw_row("2022-23", 10, 1, 1, "2022-08-06 14:00:00", pts=6, minutes=90),
        _gw_row("2022-23", 10, 2, 2, "2022-08-13 14:00:00", pts=9, minutes=90),
        _gw_row("2022-23", 10, 3, 2, "2022-08-16 19:00:00", pts=1, minutes=90, home=False),
        _gw_row("2022-23", 10, 4, 3, "2022-08-20 14:00:00", pts=0, minutes=0),
    ]
    _load(store, "2022-23", rows)
    f = _features(store)
    for col in ("pts_per_fix_5", "mins_per_fix_5", "n_prior_fixtures"):
        assert f[2][col] == f[3][col]
    assert f[2]["pts_per_fix_5"] == 6
    # the double gameweek counts as two fixtures in later windows: (6 + 9 + 1) / 3
    assert f[4]["n_prior_fixtures"] == 3
    assert f[4]["pts_per_fix_5"] == pytest.approx(16 / 3)


def test_history_carries_across_seasons_by_player_code(store):
    _load(store, "2021-22", [_gw_row("2021-22", 10, 1, 1, "2022-05-01 14:00:00", pts=8,
                                     minutes=90)])
    # new season, different element_id, same code
    _load(store, "2022-23", [_gw_row("2022-23", 77, 1, 1, "2022-08-06 14:00:00", pts=3,
                                     minutes=90)], element=77)
    f = _features(store)
    assert f[1]["pts_per_fix_career"] == 8
    assert f[1]["n_prior_fixtures"] == 1


def test_blank_gameweek_is_skipped_not_counted_as_zero(store):
    rows = [
        _gw_row("2022-23", 10, 1, 1, "2022-08-06 14:00:00", pts=6, minutes=90),
        _gw_row("2022-23", 10, 2, 3, "2022-08-27 14:00:00", pts=2, minutes=90),  # GW2 blank
    ]
    _load(store, "2022-23", rows)
    assert _features(store)[2]["pts_per_fix_3"] == 6


def test_team_form_excludes_current_gameweek(store):
    rows = [
        _gw_row("2022-23", 10, 1, 1, "2022-08-06 14:00:00", pts=1, minutes=90, h=3, a=1),
        _gw_row("2022-23", 10, 2, 2, "2022-08-13 14:00:00", pts=1, minutes=90, h=9, a=9),
    ]
    _load(store, "2022-23", rows)
    f = _features(store)
    assert f[1]["own_goals_for_6"] is None
    assert f[2]["own_goals_for_6"] == 3 and f[2]["own_goals_against_6"] == 1
