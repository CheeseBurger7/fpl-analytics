"""Horizon-aware LightGBM: predict the points of a fixture ``h`` gameweeks after the decision.

A decision before gameweek g sees only results before g. For a fixture in gameweek g+h the dataset
row has features that include results of g..g+h-1, so it cannot be used. Instead each target row
is paired with the player's *source row*: his latest row in a gameweek <= g (features as of that
deadline). The model for horizon h maps (source features, target ``was_home``, the gap between the
two gameweeks) to the target row's points. Opponent and own-team form are taken from the source
row (own team) or dropped (opponent: the dataset carries no opponent id to look it up at g), so
fixture difficulty of later gameweeks is only partly modelled. Source and target are in the same
season, so a season's first gameweeks have no horizon rows.

``HorizonPredictor`` implements the ``fpl.backtest.Predictor`` protocol (the as-of gameweek of a
row defaults to its own ordinal minus ``h``); the planner backtest passes an explicit ``as_of``.
``PersistencePredictor`` is the reference: the base model's prediction on the source row.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from fpl.backtest import Dataset, Predictor
from fpl.features import FEATURE_COLUMNS
from fpl.model import DEFAULT_PARAMS, feature_matrix

# taken from the target row (known from the schedule) / not available for a future fixture
TARGET_COLUMNS = ("was_home",)
DROPPED = ("opp_goals_for_6", "opp_goals_against_6")
SOURCE_COLUMNS: tuple[str, ...] = tuple(
    c for c in FEATURE_COLUMNS if c not in TARGET_COLUMNS and c not in DROPPED
)


class HistoryIndex:
    """Per (season, player): the first row of each gameweek, for as-of lookups by ordinal."""

    def __init__(self, data: Dataset) -> None:
        self.data = data
        seasons, elements = data.columns["season"], data.columns["element_id"]
        ords = data.columns["gw_ordinal"]
        rows: dict[tuple, tuple[list[int], list[int]]] = {}
        for i in range(len(data)):
            o, r = rows.setdefault((seasons[i], elements[i]), ([], []))
            if not o or o[-1] != ords[i]:
                o.append(ords[i])
                r.append(i)
        self.rows = rows
        self._matrices: dict[tuple[str, ...], np.ndarray] = {}

    @classmethod
    def of(cls, data: Dataset) -> HistoryIndex:
        """One index per dataset (cached on it), shared by all horizon predictors."""
        cached = data.__dict__.get("_history_index")
        if cached is None:
            cached = data.__dict__["_history_index"] = cls(data)
        return cached

    def source(self, row: int, as_of: int) -> int | None:
        """The player's latest row of ``row``'s season in a gameweek ordinal <= ``as_of``."""
        d = self.data.columns
        entry = self.rows.get((d["season"][row], d["element_id"][row]))
        if entry is None:
            return None
        k = bisect.bisect_right(entry[0], as_of) - 1
        return entry[1][k] if k >= 0 else None

    def matrix(self, columns: Sequence[str]) -> np.ndarray:
        """Every dataset row x ``columns`` as floats (NaN = missing); cached."""
        key = tuple(columns)
        if key not in self._matrices:
            self._matrices[key] = feature_matrix(self.data, range(len(self.data)), key)
        return self._matrices[key]


def sources(
    data: Dataset, idx: Sequence[int], h: int, as_of: int | None = None
) -> list[int | None]:
    """Source row per target row: as of ``as_of``, or each row's own ordinal minus ``h``."""
    index = HistoryIndex.of(data)
    ords = data.columns["gw_ordinal"]
    return [index.source(i, ords[i] - h if as_of is None else as_of) for i in idx]


@dataclass
class HorizonPredictor:
    """Per-fixture points ``h`` gameweeks ahead from features as of the decision gameweek.

    ``use_xp`` adds FPL's ``xp`` of the *source* row (the forecast known at the decision), never
    the target's.
    """

    h: int
    use_xp: bool = False
    name: str = ""
    n_rounds: int = 300
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    model: object = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.h < 1:
            raise ValueError("h must be >= 1 (h = 0 is the plain model)")
        self.name = self.name or f"lgbm{'_xp' if self.use_xp else ''}_h{self.h}"

    @property
    def source_columns(self) -> tuple[str, ...]:
        return (*SOURCE_COLUMNS, "xp") if self.use_xp else SOURCE_COLUMNS

    def _x(self, data: Dataset, idx: Sequence[int], src: Sequence[int | None]) -> np.ndarray:
        """Feature matrix for target rows ``idx``; rows without a source are all-NaN."""
        index = HistoryIndex.of(data)
        s = np.array([-1 if j is None else j for j in src], dtype=int)
        base = index.matrix(self.source_columns)[s]
        base[s < 0] = np.nan
        target = index.matrix(TARGET_COLUMNS)[np.asarray(idx, dtype=int)]
        ords = np.asarray(data.columns["gw_ordinal"], dtype=float)
        gap = ords[np.asarray(idx, dtype=int)] - ords[s]
        gap[s < 0] = np.nan
        return np.column_stack([base, target, gap])

    def fit(self, data: Dataset, idx: Sequence[int]) -> None:
        import lightgbm as lgb  # optional extra

        src = sources(data, idx, self.h)
        keep = [k for k, (i, j) in enumerate(zip(idx, src, strict=True))
                if j is not None and data.columns["target"][i] is not None]  # fmt: skip
        rows = [idx[k] for k in keep]
        x = self._x(data, rows, [src[k] for k in keep])
        y = np.array(data.column("target", rows), dtype=float)
        self.model = lgb.train(self.params, lgb.Dataset(x, y), num_boost_round=self.n_rounds)

    def predict(
        self, data: Dataset, idx: Sequence[int], as_of: int | None = None
    ) -> list[float | None]:
        """Per-fixture predictions; ``None`` for a row whose player has no source row."""
        if self.model is None:
            raise RuntimeError("fit() first")
        src = sources(data, idx, self.h, as_of)
        out: list[float | None] = [None] * len(idx)
        have = [k for k, j in enumerate(src) if j is not None]
        if have:
            x = self._x(data, [idx[k] for k in have], [src[k] for k in have])
            for k, v in zip(have, self.model.predict(x).tolist(), strict=True):
                out[k] = v
        return out


@dataclass
class PersistencePredictor:
    """Reference: the base predictor's per-fixture prediction on the source row, i.e. what the
    planner's persistence assumes (the latest forecast carried to the later gameweek)."""

    base: Predictor
    h: int
    name: str = ""

    def __post_init__(self) -> None:
        self.name = self.name or f"{self.base.name}_persist_h{self.h}"

    def fit(self, data: Dataset, idx: Sequence[int]) -> None:
        pass  # the base predictor is fitted by its owner

    def predict(self, data: Dataset, idx: Sequence[int]) -> list[float | None]:
        src = sources(data, idx, self.h)
        have = [k for k, j in enumerate(src) if j is not None]
        pred = self.base.predict(data, [src[k] for k in have])
        out: list[float | None] = [None] * len(idx)
        for k, v in zip(have, pred, strict=True):
            out[k] = v
        return out
