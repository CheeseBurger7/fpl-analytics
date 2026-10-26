from __future__ import annotations

import pytest

from fpl.backtest import (
    ColumnPredictor,
    ConstantPredictor,
    GwContext,
    load_dataset,
    run_backtest,
    spearman,
    top_k_hit_rate,
    walk_forward_splits,
)
from fpl.store import HIST_GW_COLUMNS, Store

S1, S2 = "2022-23", "2023-24"


def _gw_row(season, element, fixture, rnd, kickoff, *, pts, minutes=90, xp=None):
    row = dict.fromkeys(HIST_GW_COLUMNS)
    row.update(
        season=season, element_id=element, fixture_id=fixture, round=rnd, opponent_team=2,
        was_home=True, kickoff_time=kickoff, team_h_score=1, team_a_score=0, minutes=minutes,
        total_points=pts, value=50, xp=xp,
    )
    return tuple(row[c] for c in HIST_GW_COLUMNS)


def _load(store, season, rows):
    teams = [(season, 1, "Arsenal"), (season, 2, "Brentford")]
    players = [(season, 10, 111, "A", None, None, 1, 3), (season, 11, 222, "B", None, None, 1, 3)]
    store.replace_hist_season(season, teams, players, rows)


@pytest.fixture
def data():
    """Two players, 3 GWs in S1 (player 10 has a double GW 2) and 2 GWs in S2."""
    with Store() as s:
        r1 = [
            _gw_row(S1, 10, 1, 1, "2022-08-06 14:00:00", pts=2, xp=2.0),
            _gw_row(S1, 11, 1, 1, "2022-08-06 14:00:00", pts=6, xp=1.0),
            _gw_row(S1, 10, 2, 2, "2022-08-13 14:00:00", pts=4, xp=2.0),
            _gw_row(S1, 10, 3, 2, "2022-08-16 19:00:00", pts=1, xp=2.0),  # double GW
            _gw_row(S1, 11, 2, 2, "2022-08-13 14:00:00", pts=2, xp=1.0),
            _gw_row(S1, 10, 4, 3, "2022-08-20 14:00:00", pts=8, xp=2.0),
            _gw_row(S1, 11, 3, 3, "2022-08-20 14:00:00", pts=3, xp=1.0),
        ]
        r2 = [
            _gw_row(S2, 10, 1, 1, "2023-08-12 14:00:00", pts=5),
            _gw_row(S2, 11, 1, 1, "2023-08-12 14:00:00", pts=1),
            _gw_row(S2, 10, 2, 2, "2023-08-19 14:00:00", pts=3),
        ]
        _load(s, S1, r1)
        _load(s, S2, r2)
        yield load_dataset(s.con)


def test_dataset_is_chronological_with_contiguous_gameweeks(data):
    assert [k for k, _, _ in data.gameweeks] == [(S1, 1), (S1, 2), (S1, 3), (S2, 1), (S2, 2)]
    kick = data.columns["kickoff_time"]
    assert [kick[a] for _, a, _ in data.gameweeks] == sorted(kick[a] for _, a, _ in data.gameweeks)
    assert len(data) == 10


def test_gameweeks_ordered_by_kickoff_not_round():
    with Store() as s:
        # round numbers run backwards relative to time
        rows = [
            _gw_row(S1, 10, 1, 9, "2022-08-06 14:00:00", pts=1),
            _gw_row(S1, 10, 2, 3, "2022-08-13 14:00:00", pts=1),
        ]
        _load(s, S1, rows)
        d = load_dataset(s.con)
    assert [k for k, _, _ in d.gameweeks] == [(S1, 9), (S1, 3)]


@pytest.mark.parametrize("step", [1, 2, None])
def test_training_rows_always_precede_the_evaluated_block(data, step):
    kick, start = data.columns["kickoff_time"], data.columns["gw_start"]
    splits = list(walk_forward_splits(data, [S1, S2], step))
    seen = []
    for sp in splits:
        block_start = start[sp.eval[0][1]]
        assert all(kick[i] < block_start for i in sp.train)
        evaluated = {i for _, a, b in sp.eval for i in range(a, b)}
        assert not evaluated & set(sp.train)
        seen += [k for k, _, _ in sp.eval]
    assert seen == [k for k, _, _ in data.gameweeks]  # each GW evaluated exactly once


def test_season_block_trains_once_per_season_and_never_in_season(data):
    splits = list(walk_forward_splits(data, [S1, S2], None))
    assert len(splits) == 2
    assert splits[0].train == []
    assert len(splits[1].train) == 7  # all of S1, nothing of S2


def test_restricting_eval_seasons_still_trains_on_earlier_ones(data):
    (split,) = walk_forward_splits(data, [S2], None)
    assert len(split.train) == 7


def test_spearman_handles_ties_and_constants():
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 2], [1, 2, 3]) == pytest.approx(0.8660254)
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert spearman([1], [1]) is None


def test_top_k_hit_rate():
    ids = [1, 2, 3, 4]
    actual = [9, 1, 5, 0]
    assert top_k_hit_rate(ids, [4, 3, 2, 1], actual, 2) == 0.5  # picks 1,2; best are 1,3
    assert top_k_hit_rate(ids, [9, 0, 8, 0], actual, 2) == 1.0
    assert top_k_hit_rate(ids, [1, 1, 1, 1], [1, 1, 1, 1], 2) == 1.0  # ties are generous
    assert top_k_hit_rate(ids, [1, 2, 3, 4], actual, 5) is None


def test_metrics_aggregate_double_gameweek_before_scoring(data):
    res = run_backtest(data, [ConstantPredictor("c3", 3.0)], [S1], step=None, min_history=0,
                       top_ks=(1,))
    by_round = {m.round: m for m in res.gw_metrics}
    # GW2: player 10 plays twice -> predicted 6 vs actual 5; player 11 predicted 3 vs 2
    assert by_round[2].mae == pytest.approx((1 + 1) / 2)
    assert by_round[2].n_players == 2 and by_round[2].n_fixtures == 3
    # fixture-level: |3-4| + |3-1| + |3-2| over 3 fixtures
    assert by_round[2].mae_fixture == pytest.approx(4 / 3)
    # GW1: actual 2 and 6 vs 3 and 3
    assert by_round[1].mae == pytest.approx((1 + 3) / 2)


def test_min_history_masks_cold_starts(data):
    res = run_backtest(data, [ConstantPredictor("c", 2.0)], [S1, S2], step=None, min_history=2)
    assert {(m.season, m.round) for m in res.gw_metrics} == {(S1, 3), (S2, 1), (S2, 2)}
    gw3 = next(m for m in res.gw_metrics if (m.season, m.round) == (S1, 3))
    assert gw3.n_players == 2  # both players have >= 2 prior fixtures at S1 GW3


def test_predictors_are_compared_on_common_player_gws(data):
    # xp is null for all of S2: the xp baseline must not shrink S1 but must drop S2 for everyone
    preds = [ConstantPredictor("c", 2.0), ColumnPredictor("xp", "xp")]
    res = run_backtest(data, preds, [S1, S2], step=None, min_history=0)
    assert {m.season for m in res.gw_metrics} == {S1}
    rows = {(m.predictor, m.round): m for m in res.gw_metrics}
    assert rows[("c", 1)].n_players == rows[("xp", 1)].n_players == 2


def test_round_with_all_zero_xp_is_treated_as_missing_xp():
    rows = [
        _gw_row(S1, 10, 1, 1, "2022-08-06 14:00:00", pts=2, xp=0.0),
        _gw_row(S1, 11, 1, 1, "2022-08-06 14:00:00", pts=6, xp=0.0),  # vaastav: xp missing as 0
        _gw_row(S1, 10, 2, 2, "2022-08-13 14:00:00", pts=4, xp=0.0),
        _gw_row(S1, 11, 2, 2, "2022-08-13 14:00:00", pts=2, xp=1.5),
    ]
    with Store() as s:
        _load(s, S1, rows)
        xp = load_dataset(s.con).columns["xp"]
    assert xp == [None, None, 0.0, 1.5]  # a real 0 in a round with forecasts stays 0


def test_features_never_see_the_target_for_baseline_predictions(data):
    # rolling mean for S1 GW3 player 10 is built from GW1-2 only: (2 + 4 + 1) / 3 fixtures
    res = run_backtest(data, [ColumnPredictor("r", "pts_per_fix_5")], [S1], step=None,
                       min_history=1)
    gw3 = next(m for m in res.gw_metrics if m.round == 3)
    # player 10: pred 7/3, actual 8; player 11: pred (6+2)/2 = 4, actual 3
    assert gw3.mae == pytest.approx((abs(7 / 3 - 8) + abs(4 - 3)) / 2)


def test_fit_is_called_per_split_with_only_past_rows(data):
    calls = []

    class Spy:
        name = "spy"

        def fit(self, d, idx):
            calls.append(len(idx))

        def predict(self, d, idx):
            return [1.0] * len(idx)

    run_backtest(data, [Spy()], [S1], step=1, min_history=0)
    assert calls == [0, 2, 5]  # GW1 fit on nothing, GW2 on GW1, GW3 on GW1-2


def test_gw_hook_receives_player_level_sums_and_extra_is_summarised(data):
    seen = []

    def hook(ctx: GwContext):
        seen.append(ctx)
        return {"total_pred": sum(ctx.predicted.values())}

    res = run_backtest(data, [ConstantPredictor("c", 2.0)], [S1], step=None, min_history=0,
                       hooks=[hook])
    gw2 = next(c for c in seen if c.round == 2)
    assert gw2.predicted == {10: 4.0, 11: 2.0} and gw2.actual == {10: 5.0, 11: 2.0}
    assert gw2.eligible == {10, 11}
    (row,) = res.summary()
    assert row["total_pred"] == pytest.approx((4 + 6 + 4) / 3)
    assert row["n_gws"] == 3


def test_summary_by_season_and_duplicate_names_rejected(data):
    res = run_backtest(data, [ConstantPredictor("c")], [S1, S2], step=None, min_history=0)
    rows = res.summary(by_season=True)
    assert [(r["season"], r["n_gws"]) for r in rows] == [(S1, 3), (S2, 2)]
    with pytest.raises(ValueError, match="unique"):
        run_backtest(data, [ConstantPredictor("c"), ConstantPredictor("c")], [S1])
