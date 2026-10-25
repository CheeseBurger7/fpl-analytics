from __future__ import annotations

import random

import pytest

pytest.importorskip("lightgbm")

from fpl.backtest import Dataset  # noqa: E402
from fpl.features import FEATURE_COLUMNS  # noqa: E402
from fpl.model import LightGBMPredictor  # noqa: E402


def _data(n=400):
    rng = random.Random(0)
    cols = {c: [rng.random() for _ in range(n)] for c in FEATURE_COLUMNS}
    cols["xp"] = [None if i % 5 == 0 else rng.random() for i in range(n)]
    cols["target"] = [4 * x + 0.1 * rng.random() for x in cols["pts_per_fix_5"]]
    for c in ("season", "round", "gw_ordinal", "gw_start", "kickoff_time", "element_id",
              "fixture_id"):
        cols[c] = list(range(n))
    return Dataset(cols)


def test_fit_predict_recovers_signal_and_handles_missing_xp():
    data = _data()
    train, test = list(range(300)), list(range(300, 400))
    params = {"verbosity": -1, "min_data_in_leaf": 5}
    p = LightGBMPredictor(use_xp=True, n_rounds=100, params=params)
    p.fit(data, train)
    pred = p.predict(data, test)
    assert len(pred) == len(test)
    err = sum(abs(a - data.columns["target"][i]) for a, i in zip(pred, test, strict=True)) / 100
    assert err < 0.5  # constant-mean error would be ~1


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError):
        LightGBMPredictor().predict(_data(10), [0])
