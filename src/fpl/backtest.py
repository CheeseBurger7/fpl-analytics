"""Walk-forward backtest harness for expected-points predictors.

The dataset is one row per player-fixture (``build_features`` plus FPL's own ``xp``), ordered by
gameweek start. Gameweeks are ordered by their earliest kickoff, never by raw ``round`` (2019-20
runs to 47 and spans the COVID break).

A predictor sees only rows whose kickoff is strictly before the first evaluated gameweek of the
current block, so a model is never fitted on a result that was not known at that deadline.
Predictions are per fixture; metrics are computed after summing them per (player, gameweek) so a
double gameweek counts as one decision and a blank as none.

To plug in a model (e.g. LightGBM), implement ``Predictor``: ``fit(data, idx)`` on training row
indices and ``predict(data, idx)`` returning one value per row (``None`` = no prediction). Pull
arrays with ``data.column(name, idx)``. For decision-level metrics (the ILP captured fraction)
pass a ``GwMetricHook`` to ``run_backtest``; it is called once per predictor per gameweek.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from typing import Protocol

import duckdb

from fpl.features import FEATURE_COLUMNS, build_features

ID_COLUMNS = ("season", "round", "gw_ordinal", "gw_start", "kickoff_time", "element_id",
              "fixture_id", "target", "xp")
DATA_COLUMNS = (*ID_COLUMNS, *FEATURE_COLUMNS)

DEFAULT_TOP_KS = (10, 20)

GwKey = tuple[str, int]  # (season, round)


# --------------------------------------------------------------------------------------- data


@dataclass
class Dataset:
    """Columnar rows sorted by (gw_start, kickoff_time, fixture_id, element_id)."""

    columns: dict[str, list]

    def __post_init__(self) -> None:
        missing = set(ID_COLUMNS) - set(self.columns)
        if missing:
            raise ValueError(f"dataset missing columns: {sorted(missing)}")

    def __len__(self) -> int:
        return len(self.columns["target"])

    def column(self, name: str, idx: Sequence[int] | None = None) -> list:
        col = self.columns[name]
        return col if idx is None else [col[i] for i in idx]

    @cached_property
    def gameweeks(self) -> list[tuple[GwKey, int, int]]:
        """Gameweeks in chronological order as (key, first_row, end_row)."""
        ords, seasons, rounds = (self.columns[c] for c in ("gw_ordinal", "season", "round"))
        out: list[tuple[GwKey, int, int]] = []
        start = 0
        for i in range(1, len(self) + 1):
            if i == len(self) or ords[i] != ords[start]:
                out.append(((seasons[start], rounds[start]), start, i))
                start = i
        if len({o for o in ords}) != len(out):
            raise ValueError("rows must be sorted so each gameweek is contiguous")
        return out

    @cached_property
    def _by_kickoff(self) -> tuple[list[int], list[datetime]]:
        kick = self.columns["kickoff_time"]
        order = sorted(range(len(self)), key=kick.__getitem__)
        return order, [kick[i] for i in order]

    def rows_before(self, when: datetime) -> list[int]:
        """Indices of rows kicking off strictly before ``when`` (results known by then)."""
        order, kicks = self._by_kickoff
        return order[: bisect.bisect_left(kicks, when)]


def load_dataset(con: duckdb.DuckDBPyConnection) -> Dataset:
    """Features + xp for every historical fixture row, in chronological order.

    vaastav stores a missing ``xp`` as 0 for a whole round (27 of 38 rounds in 2025-26), so a
    round whose ``xp`` is 0 for everyone is treated as missing (NULL), not as a forecast of 0.

    On a double gameweek vaastav repeats the round's ``xp`` on both fixture rows (mean 5.7 vs 2.7 on
    single-gameweek rows), so it is divided by the player's row count to be a per-fixture forecast
    that the harness can sum.

    ``xp_prev`` is the player's ``xp`` per fixture in his latest earlier gameweek with an ``xp``.
    vaastav's ``xp`` of a gameweek looks partly recorded after it was played (see the wiki), so
    ``xp`` itself may leak the result; ``xp_prev`` only holds what was known before the deadline.
    """
    rel = build_features(con)
    cols = ", ".join(f"f.{c}" for c in FEATURE_COLUMNS)
    sql = f"""
    WITH j AS (
        SELECT f.season, f.round, f.kickoff_time, f.element_id, f.fixture_id, f.target,
               CASE WHEN MAX(g.xp) OVER (PARTITION BY f.season, f.round) > 0
                    THEN g.xp / COUNT(*) OVER (PARTITION BY f.season, f.element_id, f.round)
               END AS xp,
               MIN(f.kickoff_time) OVER (PARTITION BY f.season, f.round) AS gw_start, {cols}
        FROM feat f JOIN hist_player_gw g USING (season, element_id, fixture_id)
        WHERE f.kickoff_time IS NOT NULL
    ),
    rx AS (
        SELECT season, element_id, round, AVG(xp) AS xp_r, MIN(kickoff_time) AS k
        FROM j GROUP BY ALL
    ),
    rl AS (
        SELECT season, element_id, round,
               LAST_VALUE(xp_r IGNORE NULLS) OVER (
                   PARTITION BY season, element_id ORDER BY k
                   ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS xp_prev
        FROM rx
    )
    SELECT season, round,
           DENSE_RANK() OVER (ORDER BY gw_start, season, round) AS gw_ordinal,
           gw_start, kickoff_time, element_id, fixture_id, target, xp, xp_prev,
           {", ".join(FEATURE_COLUMNS)}
    FROM j JOIN rl USING (season, element_id, round)
    ORDER BY gw_start, season, round, kickoff_time, fixture_id, element_id
    """
    cur = rel.query("feat", sql)
    names = cur.columns
    data: dict[str, list] = {n: [] for n in names}
    for row in cur.fetchall():
        for n, v in zip(names, row, strict=True):
            data[n].append(v)
    return Dataset(data)


# ------------------------------------------------------------------------------------ splits


@dataclass(frozen=True)
class Split:
    train: list[int]  # row indices, all kicking off before the first evaluated gameweek
    eval: tuple[tuple[GwKey, int, int], ...]  # (key, first_row, end_row) per evaluated gameweek


def walk_forward_splits(
    data: Dataset, eval_seasons: Sequence[str], step: int | None = 1
) -> Iterator[Split]:
    """Expanding-window splits over the gameweeks of ``eval_seasons``.

    ``step`` gameweeks are evaluated per fit (1 = refit every gameweek); ``None`` fits once per
    season and evaluates the whole season with that model (a season block). Blocks never span
    seasons.
    """
    if step is not None and step < 1:
        raise ValueError("step must be >= 1 or None")
    wanted = set(eval_seasons)
    by_season: dict[str, list[tuple[GwKey, int, int]]] = defaultdict(list)
    for gw in data.gameweeks:
        if gw[0][0] in wanted:
            by_season[gw[0][0]].append(gw)
    kick = data.columns["gw_start"]
    for season in sorted(by_season):
        gws = by_season[season]
        size = len(gws) if step is None else step
        for i in range(0, len(gws), size):
            block = tuple(gws[i : i + size])
            yield Split(data.rows_before(kick[block[0][1]]), block)


# ------------------------------------------------------------------------------- predictors


class Predictor(Protocol):
    name: str

    def fit(self, data: Dataset, idx: Sequence[int]) -> None: ...

    def predict(self, data: Dataset, idx: Sequence[int]) -> list[float | None]: ...


@dataclass
class ColumnPredictor:
    """Predict a feature column as-is (a rolling mean, FPL's xp, ...); stateless."""

    name: str
    column: str

    def fit(self, data: Dataset, idx: Sequence[int]) -> None:
        pass

    def predict(self, data: Dataset, idx: Sequence[int]) -> list[float | None]:
        col = data.columns[self.column]
        return [col[i] for i in idx]


@dataclass
class ConstantPredictor:
    name: str
    value: float = 2.0

    def fit(self, data: Dataset, idx: Sequence[int]) -> None:
        pass

    def predict(self, data: Dataset, idx: Sequence[int]) -> list[float | None]:
        return [self.value] * len(idx)


def default_baselines() -> list[Predictor]:
    return [
        ConstantPredictor("constant_2", 2.0),
        ColumnPredictor("rolling_mean_5", "pts_per_fix_5"),
        ColumnPredictor("career_mean", "pts_per_fix_career"),
        ColumnPredictor("fpl_xp", "xp"),
    ]


# -------------------------------------------------------------------------------------- metrics


def _ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks, ties get the average rank."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rank correlation; ``None`` if undefined (n < 2 or either side constant)."""
    n = len(x)
    if n < 2:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True)) / (sxx * syy) ** 0.5


def top_k_hit_rate(
    ids: Sequence[int], pred: Sequence[float], actual: Sequence[float], k: int
) -> float | None:
    """Share of the predicted top-k whose actual points reach the k-th best actual score.

    Ties in actual points are generous (anyone tying the k-th score counts as a hit); ties in
    the prediction break by id, so a constant predictor is a deterministic arbitrary pick.
    """
    if len(ids) < k:
        return None
    cutoff = sorted(actual, reverse=True)[k - 1]
    picked = sorted(range(len(ids)), key=lambda i: (-pred[i], ids[i]))[:k]
    return sum(actual[i] >= cutoff for i in picked) / k


@dataclass(frozen=True)
class GwContext:
    """Per-gameweek view handed to a ``GwMetricHook`` (player-GW sums, common players only).

    ``predicted``/``actual`` cover every player with a prediction from all predictors;
    ``eligible`` is the subset with enough history. Position, price and team are not included:
    an optimizer metric joins them from the database by (season, element_id).
    """

    predictor: str
    season: str
    round: int
    predicted: Mapping[int, float]
    actual: Mapping[int, float]
    eligible: frozenset[int]


GwMetricHook = Callable[[GwContext], Mapping[str, float]]


@dataclass(frozen=True)
class GwMetrics:
    predictor: str
    season: str
    round: int
    n_players: int
    n_fixtures: int
    mae: float  # per (player, gw) sums
    mae_fixture: float
    spearman: float | None
    top_k: dict[int, float | None]
    extra: dict[str, float] = field(default_factory=dict)


@dataclass
class BacktestResult:
    gw_metrics: list[GwMetrics]

    def summary(self, by_season: bool = False) -> list[dict[str, object]]:
        """Unweighted mean over gameweeks per predictor (and season), ignoring undefined values."""
        groups: dict[tuple[str, str], list[GwMetrics]] = defaultdict(list)
        for m in self.gw_metrics:
            groups[(m.predictor, m.season if by_season else "all")].append(m)
        order = {m.predictor: i for i, m in reversed(list(enumerate(self.gw_metrics)))}
        rows: list[dict[str, object]] = []
        ordered = sorted(groups.items(), key=lambda kv: (kv[0][1], order[kv[0][0]]))
        for (pred, season), ms in ordered:
            row: dict[str, object] = {"predictor": pred, "season": season, "n_gws": len(ms)}
            series: dict[str, list[float | None]] = {
                "mae": [m.mae for m in ms],
                "mae_fixture": [m.mae_fixture for m in ms],
                "spearman": [m.spearman for m in ms],
            }
            for k in sorted({k for m in ms for k in m.top_k}):
                series[f"top{k}"] = [m.top_k.get(k) for m in ms]
            for name in sorted({n for m in ms for n in m.extra}):
                series[name] = [m.extra.get(name) for m in ms]
            for name, vals in series.items():
                defined = [v for v in vals if v is not None]
                row[name] = sum(defined) / len(defined) if defined else None
            rows.append(row)
        return rows


def _mean(vals: Sequence[float]) -> float:
    return sum(vals) / len(vals)


def _evaluate_gw(
    data: Dataset,
    key: GwKey,
    first: int,
    end: int,
    preds: Mapping[str, Sequence[float | None]],
    min_history: int,
    top_ks: Sequence[int],
    hooks: Sequence[GwMetricHook],
) -> list[GwMetrics]:
    elements = data.columns["element_id"]
    targets = data.columns["target"]
    n_prior = data.columns["n_prior_fixtures"]

    actual: dict[int, float] = defaultdict(float)
    eligible: set[int] = set()
    for i in range(first, end):
        actual[elements[i]] += targets[i]
        if (n_prior[i] or 0) >= min_history:
            eligible.add(elements[i])

    # sum fixture predictions per player; one missing fixture makes the player-GW missing
    agg: dict[str, dict[int, float | None]] = {}
    for name, p in preds.items():
        sums: dict[int, float | None] = defaultdict(float)
        for i in range(first, end):
            el = elements[i]
            v = p[i - first]
            sums[el] = None if (v is None or sums[el] is None) else sums[el] + v
        agg[name] = sums
    common = [el for el in sorted(actual) if all(a[el] is not None for a in agg.values())]
    pool = [el for el in common if el in eligible]
    if not pool:
        return []
    pool_set = set(pool)
    fixture_rows = [i for i in range(first, end) if elements[i] in pool_set]

    out = []
    for name, p in preds.items():
        pv = [agg[name][el] for el in pool]
        av = [actual[el] for el in pool]
        ctx = GwContext(
            name, key[0], key[1],
            {el: agg[name][el] for el in common}, {el: actual[el] for el in common},
            frozenset(pool),
        )
        extra: dict[str, float] = {}
        for hook in hooks:
            extra.update(hook(ctx))
        out.append(GwMetrics(
            predictor=name, season=key[0], round=key[1],
            n_players=len(pool), n_fixtures=len(fixture_rows),
            mae=_mean([abs(a - b) for a, b in zip(pv, av, strict=True)]),
            mae_fixture=_mean([abs(p[i - first] - targets[i]) for i in fixture_rows]),
            spearman=spearman(pv, av),
            top_k={k: top_k_hit_rate(pool, pv, av, k) for k in top_ks},
            extra=extra,
        ))
    return out


def run_backtest(
    data: Dataset,
    predictors: Sequence[Predictor],
    eval_seasons: Sequence[str],
    *,
    step: int | None = 1,
    min_history: int = 5,
    top_ks: Sequence[int] = DEFAULT_TOP_KS,
    hooks: Sequence[GwMetricHook] = (),
) -> BacktestResult:
    """Walk forward over ``eval_seasons``; all predictors are scored on the same player-GWs.

    A player-GW is scored only if every predictor produced a value for every one of its fixtures
    (e.g. ``fpl_xp`` is missing before 2020-21) and it has ``min_history`` prior fixtures.
    """
    if len({p.name for p in predictors}) != len(predictors):
        raise ValueError("predictor names must be unique")
    metrics: list[GwMetrics] = []
    for split in walk_forward_splits(data, eval_seasons, step):
        for p in predictors:
            p.fit(data, split.train)
        for key, first, end in split.eval:
            idx = range(first, end)
            preds = {p.name: p.predict(data, idx) for p in predictors}
            for name, v in preds.items():
                if len(v) != len(idx):
                    raise ValueError(f"{name} returned {len(v)} predictions for {len(idx)} rows")
            metrics += _evaluate_gw(data, key, first, end, preds, min_history, top_ks, hooks)
    return BacktestResult(metrics)


def format_summary(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "(no evaluated gameweeks)"
    cols = list(rows[0])
    cells = [[f"{r[c]:.3f}" if isinstance(r[c], float) else str(r[c] or "-") for c in cols]
             for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(cols)]
    lines = ["  ".join(c.ljust(w) for c, w in zip(cols, widths, strict=True))]
    lines += ["  ".join(v.ljust(w) for v, w in zip(row, widths, strict=True)) for row in cells]
    return "\n".join(lines)
