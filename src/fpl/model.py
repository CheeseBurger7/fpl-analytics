"""LightGBM expected-points predictor for the walk-forward backtest (optional extra ``model``).

One model predicts the points of a single player-fixture from ``FEATURE_COLUMNS`` (optionally
plus FPL's own ``xp``). Fixture predictions are summed per gameweek by the harness, so double
gameweeks and blanks need no special handling. Missing values (``xp`` before 2020-21, cold
starts) are passed through as NaN for LightGBM to route.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from fpl.backtest import Dataset
from fpl.features import FEATURE_COLUMNS

DEFAULT_PARAMS: dict = {
    "objective": "regression",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 10.0,
    "verbosity": -1,
    "seed": 0,
}


def _matrix(cols: Sequence[Sequence], n: int) -> np.ndarray:
    arr = [[np.nan if v is None else float(v) for v in col] for col in cols]
    return np.array(arr, dtype=float).T.reshape(n, len(cols))


def feature_matrix(data: Dataset, idx: Sequence[int], columns: Sequence[str]) -> np.ndarray:
    return _matrix([data.column(c, idx) for c in columns], len(idx))


@dataclass
class LightGBMPredictor:
    """Gradient-boosted regressor on the per-fixture target; refit by the harness per block."""

    name: str = "lgbm"
    use_xp: bool = False
    xp_column: str = "xp"  # "xp_prev" = last gameweek's xp (leak-free in the backtest)
    n_rounds: int = 300
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    model: object = field(default=None, init=False, repr=False)

    @property
    def columns(self) -> tuple[str, ...]:
        return (*FEATURE_COLUMNS, self.xp_column) if self.use_xp else FEATURE_COLUMNS

    def fit(self, data: Dataset, idx: Sequence[int]) -> None:
        import lightgbm as lgb  # optional extra

        rows = [i for i in idx if data.columns["target"][i] is not None]
        x = feature_matrix(data, rows, self.columns)
        y = np.array(data.column("target", rows), dtype=float)
        self.model = lgb.train(self.params, lgb.Dataset(x, y), num_boost_round=self.n_rounds)

    def predict(self, data: Dataset, idx: Sequence[int]) -> list[float | None]:
        if self.model is None:
            raise RuntimeError("fit() first")
        return self.model.predict(feature_matrix(data, idx, self.columns)).tolist()

    def predict_rows(self, rows: Sequence[Mapping[str, object]]) -> list[float]:
        """Predict from feature dicts (e.g. ``Live.dicts()``); ``use_xp`` needs an ``xp`` key."""
        if self.model is None:
            raise RuntimeError("fit() first")
        x = _matrix([[r[c] for r in rows] for c in self.columns], len(rows))
        return self.model.predict(x).tolist()


def model_predictors() -> list[LightGBMPredictor]:
    """With and without FPL's ``xp`` as an input, so its contribution is visible."""
    return [LightGBMPredictor("lgbm", use_xp=False), LightGBMPredictor("lgbm_xp", use_xp=True)]
