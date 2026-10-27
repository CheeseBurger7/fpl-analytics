from __future__ import annotations

import random

import pytest

from fpl.backtest import ColumnPredictor, Dataset
from fpl.features import FEATURE_COLUMNS
from fpl.horizon import HistoryIndex, PersistencePredictor, sources

N_GW = 12


def _data(players=30, seed=0):
    """Players x gameweeks, one fixture each; player 0 blanks in gameweek 5.

    ``pts_per_fix_5`` is a per-player constant and the target follows it, so a horizon model can
    learn the signal from the source row alone.
    """
    rng = random.Random(seed)
    level = {p: rng.random() for p in range(players)}
    rows = [(g, p) for g in range(1, N_GW + 1) for p in range(players) if (g, p) != (5, 0)]
    cols = {c: [] for c in (*FEATURE_COLUMNS, "xp", "target", "season", "round", "gw_ordinal",
                            "gw_start", "kickoff_time", "element_id", "fixture_id")}
    for g, p in rows:
        for c in FEATURE_COLUMNS:
            cols[c].append(rng.random())
        cols["pts_per_fix_5"][-1] = level[p]
        cols["opp_goals_for_6"][-1] = float(g)  # would leak the gameweek if it were used
        cols["xp"].append(None)
        cols["target"].append(4 * level[p])
        cols["season"].append("s")
        cols["round"].append(g)
        cols["gw_ordinal"].append(g)
        cols["gw_start"].append(g)
        cols["kickoff_time"].append(g)
        cols["element_id"].append(p)
        cols["fixture_id"].append(g * 100 + p)
    return Dataset(cols)


def _row(data, g, p):
    rounds, elements = data.columns["round"], data.columns["element_id"]
    return next(i for i in range(len(data)) if rounds[i] == g and elements[i] == p)


def test_source_is_latest_row_at_or_before_the_decision_gameweek():
    data = _data()
    # target GW8, h=3 -> decision GW5; player 0 blanked then, so his source is his GW4 row
    assert sources(data, [_row(data, 8, 0)], 3) == [_row(data, 4, 0)]
    assert sources(data, [_row(data, 8, 1)], 3) == [_row(data, 5, 1)]
    # explicit as-of overrides the default
    assert sources(data, [_row(data, 8, 1)], 3, as_of=2) == [_row(data, 2, 1)]
    # nothing before the first gameweek
    assert sources(data, [_row(data, 2, 1)], 3) == [None]


def test_source_stays_within_the_season():
    data = _data()
    data.columns["season"][_row(data, 1, 3)] = "other"
    assert HistoryIndex.of(data).source(_row(data, 2, 3), 1) is None


def test_persistence_predicts_the_source_row():
    data = _data()
    base = ColumnPredictor("lvl", "pts_per_fix_5")
    pred = PersistencePredictor(base, 2).predict(data, [_row(data, 6, 4), _row(data, 2, 4)])
    assert pred[0] == data.columns["pts_per_fix_5"][_row(data, 4, 4)]
    assert pred[1] is None  # source GW0 does not exist


def test_horizon_model_learns_from_source_features_and_never_sees_future_columns():
    pytest.importorskip("lightgbm")
    from fpl.horizon import SOURCE_COLUMNS, HorizonPredictor

    assert "opp_goals_for_6" not in SOURCE_COLUMNS and "was_home" not in SOURCE_COLUMNS
    data = _data()
    train = [i for i in range(len(data)) if data.columns["round"][i] <= 9]
    test = [i for i in range(len(data)) if data.columns["round"][i] >= 10]
    m = HorizonPredictor(2, n_rounds=100, params={"verbosity": -1, "min_data_in_leaf": 5})
    m.fit(data, train)
    pred = m.predict(data, test)
    target = data.columns["target"]
    err = sum(abs(v - target[i]) for v, i in zip(pred, test, strict=True)) / len(test)
    assert err < 0.3  # a constant prediction would miss by ~1
    # a player blanking in the decision gameweek still has a source (older row), so a prediction
    assert m.predict(data, [_row(data, 7, 0)])[0] is not None


def test_horizon_predict_requires_fit_and_positive_h():
    pytest.importorskip("lightgbm")
    from fpl.horizon import HorizonPredictor

    with pytest.raises(RuntimeError):
        HorizonPredictor(1).predict(_data(), [0])
    with pytest.raises(ValueError):
        HorizonPredictor(0)
