from __future__ import annotations

import pytest

from fpl.live import live_features, predictions, score_blind
from fpl.store import HIST_GW_COLUMNS, Store

SEASON = "2026-27"


def _hist_row(fixture, rnd, kickoff, *, pts, minutes):
    row = dict.fromkeys(HIST_GW_COLUMNS)
    row.update(
        season=SEASON, element_id=10, fixture_id=fixture, round=rnd, opponent_team=2,
        was_home=True, kickoff_time=kickoff, team_h_score=1, team_a_score=0, minutes=minutes,
        total_points=pts, value=50,
    )
    return tuple(row[c] for c in HIST_GW_COLUMNS)


@pytest.fixture
def store():
    """GW1 from 'vaastav', GW2 only in the live tables, GW3 unplayed (the target)."""
    with Store() as s:
        s.replace_hist_season(
            SEASON,
            [(SEASON, 1, "Arsenal"), (SEASON, 2, "Brentford")],
            [(SEASON, 10, 111, "Saka", None, None, 1, 3)],
            [_hist_row(1, 1, "2026-08-15 14:00:00", pts=10, minutes=90)],
        )
        c = s.con
        c.execute("INSERT INTO snapshots VALUES (1, '2026-09-01 00:00:00', 2, 3)")
        c.execute(
            "INSERT INTO player_snapshots (snapshot_id, element_id, web_name, team_id, position,"
            " now_cost, ep_next, raw) VALUES (1, 10, 'Saka', 1, 3, 101, 5.0,"
            ' \'{"code": 111, "ep_this": "7.5"}\')'
        )
        for fid, ev, ko, hs, as_ in [(1, 1, "2026-08-15 14:00:00", 1, 0),
                                     (2, 2, "2026-08-22 14:00:00", 3, 0),
                                     (3, 3, "2026-08-29 14:00:00", None, None)]:
            c.execute(
                "INSERT INTO fixture_snapshots (snapshot_id, fixture_id, event, kickoff_time,"
                " team_h, team_a, team_h_score, team_a_score) VALUES (1, ?, ?, ?, 1, 2, ?, ?)",
                [fid, ev, ko, hs, as_],
            )
        c.execute(
            "INSERT INTO element_history (element_id, fixture_id, round, opponent_team, was_home,"
            " kickoff_time, minutes, total_points, value)"
            " VALUES (10, 2, 2, 2, true, '2026-08-22 14:00:00', 90, 2, 50)"
        )
        yield s


def test_target_row_uses_live_results_and_has_no_target(store):
    live = live_features(store.con, SEASON, 3)
    (row,) = live.dicts()
    assert live.last_played == 2
    assert row["fixture_id"] == 3 and row["price"] == 101 and row["was_home"] is True
    assert row["pts_per_fix_5"] == 6  # (10 from hist + 2 from element_history) / 2
    assert row["n_prior_fixtures"] == 2
    assert row["own_goals_for_6"] == 2  # scores of both played fixtures: (1 + 3) / 2


def test_main_tables_are_untouched(store):
    live_features(store.con, SEASON, 3)
    (n,) = store.con.execute("SELECT COUNT(*) FROM main.hist_player_gw").fetchall()[0]
    assert n == 1
    assert store.con.execute(
        "SELECT COUNT(*) FROM hist_player_gw WHERE round = 3").fetchall()[0][0] == 0


def test_ep_is_ep_this_for_the_current_gameweek_else_ep_next(store):
    assert live_features(store.con, SEASON, 2).dicts()[0]["ep"] == 7.5
    assert live_features(store.con, SEASON, 3).dicts()[0]["ep"] == 5.0


def test_predictions_mask_cold_starts_for_both_predictors(store):
    live = live_features(store.con, SEASON, 3)
    assert predictions(live, min_history=2)["rolling_mean_5"] == {10: 6.0}
    assert predictions(live, min_history=3) == {"rolling_mean_5": {}, "fpl_ep": {}}


def _blind_store(finished: bool):
    """15 players (ids 1-15, 2/5/5/3, club = id % 5 + 1), player i scores i points in GW4."""
    s = Store()
    c = s.con
    c.execute("INSERT INTO snapshots VALUES (1, '2026-09-01 00:00:00', 3, 4)")
    c.execute("INSERT INTO snapshots VALUES (2, '2026-09-08 00:00:00', 4, 5)")
    for i in range(1, 16):
        pos = 1 if i <= 2 else 2 if i <= 7 else 3 if i <= 12 else 4
        c.execute(
            "INSERT INTO player_snapshots (snapshot_id, element_id, web_name, team_id, position,"
            " now_cost, raw) VALUES (1, ?, ?, ?, ?, 50, '{}')", [i, f"p{i}", i % 5 + 1, pos])
        c.execute(
            "INSERT INTO element_history (element_id, fixture_id, round, minutes, total_points)"
            " VALUES (?, 1, 4, 90, ?)", [i, i])  # fmt: skip
    c.execute("INSERT INTO fixture_snapshots (snapshot_id, fixture_id, event, finished)"
              " VALUES (2, 1, 4, ?)", [finished])  # fmt: skip
    return s


def _frozen(predicted_xi):
    squad = list(range(1, 16))
    sel = {"squad": squad, "xi": predicted_xi, "captain": predicted_xi[-1], "cost": 750}
    return {"season": SEASON, "gw": 4, "snapshot_id": 1, "last_played": 3,
            "predictors": {"p": {"predicted": {str(i): 1.0 for i in squad}, "fresh": sel,
                                 "entry": sel}}}  # fmt: skip


def test_score_blind_against_hindsight_ceiling():
    xi = [1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14]  # 1 GK, 4 DEF, 4 MID, 2 FWD
    with _blind_store(True) as s:
        res = score_blind(s.con, _frozen(xi))["p"]
    assert res["fresh"]["achieved"] == sum(xi) + xi[-1]
    assert res["fresh"]["ceiling"] >= res["fresh"]["achieved"]
    assert 0 < res["fresh"]["captured_fraction"] <= 1
    assert res["entry"]["ceiling"] >= res["entry"]["achieved"]


def test_score_blind_refuses_unfinished_gameweek():
    with _blind_store(False) as s, pytest.raises(RuntimeError, match="not finished"):
        score_blind(s.con, _frozen([1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14]))


def test_ep_model_predictions_feeds_ep_as_xp_and_sums_fixtures():
    from fpl.live import Live, ep_model_predictions

    class FakeModel:
        def predict_rows(self, rows):
            return [r["xp"] * 2 for r in rows]  # only sees ep through the xp key

    cols = ["element_id", "ep", "n_prior_fixtures"]
    rows = [(1, 1.5, 9), (1, 2.0, 9), (2, None, 9), (3, 4.0, 2)]  # DGW; no ep; cold start
    live = Live("s", 9, 1, 8, cols, rows)
    assert ep_model_predictions(live, FakeModel()) == {1: 7.0}


def test_mean_captured_averages_per_predictor_and_who():
    from fpl.live import mean_captured

    def res(a, b):
        return {"fpl_ep": {"fresh": {"captured_fraction": a}},
                "lgbm": {"fresh": {"captured_fraction": b}, "entry": {"captured_fraction": b}}}

    out = mean_captured({8: res(0.6, 0.8), 9: res(0.4, 0.6)})
    assert out[("fpl_ep", "fresh")] == (pytest.approx(0.5), 2)
    assert out[("lgbm", "entry")] == (pytest.approx(0.7), 2)
