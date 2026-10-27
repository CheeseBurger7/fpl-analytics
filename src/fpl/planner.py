"""Transfer planner: the best transfers to make now, judged over the next few gameweeks.

``plan_transfers`` keeps the current 15, allows up to ``max_transfers`` swaps, and for each
transfer count k solves one MILP: choose the post-transfer squad and, per gameweek of the horizon,
the XI and captain, maximising the (discounted) sum of predicted points. The hit
(``HIT_COST`` per transfer beyond the free ones) is subtracted afterwards to give ``net``. The squad
is fixed across the horizon: only transfers made now are modelled, so there is no look-ahead to
later transfers, chips or auto-subs.

Budget: bank + sale value of the current squad >= cost of the new squad, where a kept player costs
his selling price and a new one the market price. Selling prices default to the current price; the
real one is lower after a price rise (FPL keeps half the profit), so pass ``sell_prices`` if you
know them (``fpl.planbacktest.selling_price`` computes it from the purchase price).

``horizon_predictions`` builds the per-gameweek points the planner needs from ``fpl.live``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import duckdb

from fpl.optimizer import (
    MAX_PER_CLUB,
    SQUAD_QUOTA,
    SQUAD_SIZE,
    XI_BOUNDS,
    XI_SIZE,
    InfeasibleError,
    Player,
)

HIT_COST = 4


@dataclass(frozen=True)
class Plan:
    transfers: int
    out: tuple[int, ...]
    into: tuple[int, ...]
    hit: int  # points deducted
    squad: tuple[int, ...]
    xi: tuple[tuple[int, ...], ...]  # per gameweek
    captain: tuple[int, ...]  # per gameweek
    gross: float  # discounted horizon points before the hit (includes a token bench term)
    net: float  # gross - hit
    bank: int  # tenths left after the transfers


def plan_transfers(
    players: Sequence[Player],
    points: Sequence[Mapping[int, float]],
    squad: Collection[int],
    *,
    bank: int = 0,
    free_transfers: int = 1,
    max_transfers: int = 3,
    discount: float = 1.0,
    sell_prices: Mapping[int, int] | None = None,
    bench_weight: float = 0.001,
) -> list[Plan]:
    """One best ``Plan`` per feasible transfer count 0..max_transfers, ordered by that count.

    ``players`` carries position/club/price (its ``points`` field is ignored); ``points[g][id]``
    is the predicted points in horizon gameweek g (missing = 0, e.g. a blank). Compare plans by
    ``net``; the 0-transfer plan is the baseline.
    """
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_array
    except ImportError as e:  # pragma: no cover
        raise ImportError('planner needs scipy: pip install -e ".[optimize]"') from e

    squad = set(squad)
    ids = {p.id for p in players}
    if len(squad) != SQUAD_SIZE or squad - ids:
        raise ValueError("squad must be 15 ids from the player pool")
    # a kept player costs his selling price, a new one his market price
    unit = [(sell_prices or {}).get(p.id, p.price) if p.id in squad else p.price for p in players]
    budget = bank + sum(u for u, p in zip(unit, players, strict=True) if p.id in squad)
    n, horizon = len(players), len(points)
    # variables: x (n, in squad) | s_g (n each, in XI) | c_g (n each, captain)

    def S(g: int) -> int:
        return n * (1 + g)

    def C(g: int) -> int:
        return n * (1 + horizon + g)

    nv = n * (1 + 2 * horizon)
    rows: list[tuple[dict[int, float], float, float]] = []
    inf = np.inf
    for g in range(horizon):
        for i in range(n):
            rows.append(({S(g) + i: 1, i: -1}, -inf, 0))  # starter must be in squad
            rows.append(({C(g) + i: 1, S(g) + i: -1}, -inf, 0))  # captain must start
        rows.append(({S(g) + i: 1 for i in range(n)}, XI_SIZE, XI_SIZE))
        rows.append(({C(g) + i: 1 for i in range(n)}, 1, 1))
        for pos, (lo, hi) in XI_BOUNDS.items():
            rows.append(({S(g) + i: 1 for i, p in enumerate(players) if p.position == pos}, lo, hi))
    rows.append(({i: 1 for i in range(n)}, SQUAD_SIZE, SQUAD_SIZE))
    rows.append(({i: u for i, u in enumerate(unit)}, -inf, budget))
    for pos, quota in SQUAD_QUOTA.items():
        rows.append(({i: 1 for i, p in enumerate(players) if p.position == pos}, quota, quota))
    for team in {p.team for p in players}:
        rows.append(({i: 1 for i, p in enumerate(players) if p.team == team}, -inf, MAX_PER_CLUB))
    transfers_row = len(rows)  # players kept from the current squad; bounds set per k below
    rows.append(({i: 1 for i, p in enumerate(players) if p.id in squad}, 0, 0))

    r, c, v = [], [], []
    for k, (coef, _, _) in enumerate(rows):
        for col, val in coef.items():
            r.append(k)
            c.append(col)
            v.append(val)
    a = coo_array((v, (r, c)), shape=(len(rows), nv)).tocsr()
    lo = np.array([row[1] for row in rows], dtype=float)
    hi = np.array([row[2] for row in rows], dtype=float)

    cost = np.zeros(nv)
    for g in range(horizon):
        w = discount**g
        pts = np.array([points[g].get(p.id, 0.0) for p in players], dtype=float)
        cost[:n] -= w * bench_weight * pts
        cost[S(g) : S(g) + n] = -w * (1 - bench_weight) * pts
        cost[C(g) : C(g) + n] = -w * pts

    plans = []
    for k in range(max_transfers + 1):
        lo[transfers_row] = hi[transfers_row] = SQUAD_SIZE - k
        res = milp(cost, constraints=LinearConstraint(a, lo, hi), integrality=np.ones(nv),
                   bounds=Bounds(np.zeros(nv), np.ones(nv)))  # fmt: skip
        if not res.success:
            continue  # e.g. no affordable legal squad with k changes
        z = np.round(res.x).astype(int)
        new = {players[i].id for i in range(n) if z[i]}
        hit = HIT_COST * max(0, k - free_transfers)
        gross = float(-res.fun)
        plans.append(Plan(
            transfers=k,
            out=tuple(sorted(squad - new)),
            into=tuple(sorted(new - squad)),
            hit=hit,
            squad=tuple(sorted(new)),
            xi=tuple(tuple(players[i].id for i in range(n) if z[S(g) + i]) for g in range(horizon)),
            captain=tuple(next(players[i].id for i in range(n) if z[C(g) + i])
                          for g in range(horizon)),
            gross=gross, net=gross - hit,
            bank=budget - sum(u for u, p in zip(unit, players, strict=True) if p.id in new),
        ))  # fmt: skip
    if not plans:
        raise InfeasibleError("no legal plan for this squad/bank")
    return plans


def best_plan(plans: Sequence[Plan], margin: float = 1.0) -> Plan:
    """Fewest transfers whose ``net`` is within ``margin`` points of the highest.

    Predictions are noisy, so an extra transfer must buy more than ``margin`` predicted points.
    """
    top = max(p.net for p in plans)
    return min((p for p in plans if p.net >= top - margin), key=lambda p: p.transfers)


def horizon_predictions(
    con: duckdb.DuckDBPyConnection,
    season: str,
    gw: int,
    horizon: int,
    predictor: str = "lgbm",
    *,
    min_history: int = 5,
) -> list[dict[int, float]]:
    """Predicted points per player for gameweeks ``gw .. gw+horizon-1`` (fixtures summed).

    ``predictor``: ``rolling_mean_5``, ``fpl_ep`` (FPL's ``ep``; only the first gameweek is a
    true forecast, later ones reuse ``ep_next``), ``lgbm`` (trained on every historical fixture)
    or ``lgbm_xp`` (the same with ``xp`` as an input, fed ``ep`` for the first gameweek; later
    gameweeks have no ``ep``, so they use the first gameweek's per-fixture prediction times the
    fixtures the player has then, as in ``fpl.planbacktest``). Features of later gameweeks only
    see results up to ``gw-1`` and differ just by fixture context. Gameweeks past the last
    scheduled one come back empty.
    """
    from fpl.live import ep_model_predictions, live_features, predictions

    model = None
    if predictor in ("lgbm", "lgbm_xp"):
        from fpl.backtest import load_dataset
        from fpl.model import LightGBMPredictor

        model = LightGBMPredictor(predictor, use_xp=predictor == "lgbm_xp")
        data = load_dataset(con)
        model.fit(data, range(len(data)))
    elif predictor not in ("rolling_mean_5", "fpl_ep"):
        raise ValueError(f"unknown predictor {predictor!r}")
    out: list[dict[int, float]] = []
    per_fixture: dict[int, float] = {}
    for g in range(gw, gw + horizon):
        live = live_features(con, season, g)
        if model is None:
            out.append(predictions(live, min_history=min_history)[predictor])
        elif predictor == "lgbm_xp":
            n_fix = Counter(r[0] for r in live.rows)  # element_id is the first column
            if g == gw:
                first = ep_model_predictions(live, model, min_history=min_history)
                per_fixture = {i: v / n_fix[i] for i, v in first.items()}
                out.append(first)
            else:
                out.append({i: v * n_fix.get(i, 0) for i, v in per_fixture.items()})
        else:
            rows = [r for r in live.dicts() if r["n_prior_fixtures"] >= min_history]
            pred: dict[int, float] = {}
            for r, y in zip(rows, model.predict_rows(rows), strict=True):
                pred[r["element_id"]] = pred.get(r["element_id"], 0.0) + y
            out.append(pred)
    return out
