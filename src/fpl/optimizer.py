"""Squad and lineup selection as a mixed-integer program (scipy ``milp``, HiGHS).

``optimize_squad`` picks a 15-man squad, a starting XI and a captain maximising the XI's points
(captain counted twice) under FPL's rules: budget, 2/5/5/3 squad shape, at most 3 per club and a
legal formation. It is a pure function of (position, club, price, points) per player, so the same
code serves predicted points (what to pick) and actual points (the hindsight ceiling).
``pick_lineup`` is the same problem with the squad already fixed.

This is a fresh-squad problem: no transfers, hits or chips yet. Those extend the model with a
previous-squad input and a transfer-cost term.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import duckdb

from fpl.backtest import GwContext

GK, DEF, MID, FWD = 1, 2, 3, 4
SQUAD_SIZE = 15
XI_SIZE = 11
SQUAD_QUOTA = {GK: 2, DEF: 5, MID: 5, FWD: 3}
XI_BOUNDS = {GK: (1, 1), DEF: (3, 5), MID: (2, 5), FWD: (1, 3)}
MAX_PER_CLUB = 3
BUDGET = 1000  # tenths of a million, as in ``value``/``now_cost``


@dataclass(frozen=True)
class Player:
    id: int
    position: int  # 1 GK, 2 DEF, 3 MID, 4 FWD
    team: int
    price: int  # tenths of a million
    points: float


@dataclass(frozen=True)
class Selection:
    squad: tuple[int, ...]
    xi: tuple[int, ...]
    captain: int
    objective: float  # XI points + captain bonus (+ the tiny bench term)
    cost: int

    @property
    def bench(self) -> tuple[int, ...]:
        return tuple(i for i in self.squad if i not in set(self.xi))


class InfeasibleError(ValueError):
    pass


def optimize_squad(
    players: Sequence[Player],
    *,
    budget: int = BUDGET,
    fixed_squad: Collection[int] | None = None,
    bench_weight: float = 0.001,
) -> Selection:
    """Best squad + XI + captain. ``fixed_squad`` restricts the squad to exactly those ids.

    ``bench_weight`` gives bench players a token weight so ties resolve towards a useful bench;
    keep it far below one point so it never trades off against the XI.
    """
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_array
    except ImportError as e:  # pragma: no cover
        raise ImportError('optimizer needs scipy: pip install -e ".[optimize]"') from e

    n = len(players)
    if len({p.id for p in players}) != n:
        raise ValueError("duplicate player ids")
    if fixed_squad is not None:
        unknown = set(fixed_squad) - {p.id for p in players}
        if unknown:
            raise ValueError(f"fixed_squad ids not in player pool: {sorted(unknown)}")
    # variables: x (in squad) | s (in XI) | c (captain), each n long
    X, S, C = 0, n, 2 * n
    rows: list[tuple[dict[int, float], float, float]] = []

    def add(coef: dict[int, float], lo: float, hi: float) -> None:
        rows.append((coef, lo, hi))

    for i in range(n):
        add({S + i: 1, X + i: -1}, -np.inf, 0)  # starter must be in squad
        add({C + i: 1, S + i: -1}, -np.inf, 0)  # captain must start
    add({X + i: 1 for i in range(n)}, SQUAD_SIZE, SQUAD_SIZE)
    add({S + i: 1 for i in range(n)}, XI_SIZE, XI_SIZE)
    add({C + i: 1 for i in range(n)}, 1, 1)
    add({X + i: p.price for i, p in enumerate(players)}, -np.inf, budget)
    for pos, quota in SQUAD_QUOTA.items():
        add({X + i: 1 for i, p in enumerate(players) if p.position == pos}, quota, quota)
        lo, hi = XI_BOUNDS[pos]
        add({S + i: 1 for i, p in enumerate(players) if p.position == pos}, lo, hi)
    for team in {p.team for p in players}:
        add({X + i: 1 for i, p in enumerate(players) if p.team == team}, -np.inf, MAX_PER_CLUB)

    r, c, v = [], [], []
    for k, (coef, _, _) in enumerate(rows):
        for col, val in coef.items():
            r.append(k)
            c.append(col)
            v.append(val)
    a = coo_array((v, (r, c)), shape=(len(rows), 3 * n)).tocsr()
    cons = LinearConstraint(a, [lo for _, lo, _ in rows], [hi for _, _, hi in rows])

    pts = np.array([p.points for p in players], dtype=float)
    cost = np.concatenate([-bench_weight * pts, -(1 - bench_weight) * pts, -pts])
    lb, ub = np.zeros(3 * n), np.ones(3 * n)
    if fixed_squad is not None:
        fixed = set(fixed_squad)
        lb[:n] = ub[:n] = [p.id in fixed for p in players]

    res = milp(cost, constraints=cons, integrality=np.ones(3 * n), bounds=Bounds(lb, ub))
    if not res.success:
        raise InfeasibleError(f"no legal squad for this pool/budget: {res.message}")
    z = np.round(res.x).astype(int)
    squad = tuple(players[i].id for i in range(n) if z[X + i])
    xi = tuple(players[i].id for i in range(n) if z[S + i])
    captain = next(players[i].id for i in range(n) if z[C + i])
    return Selection(squad, xi, captain, float(-res.fun), sum(
        p.price for i, p in enumerate(players) if z[X + i]))


def pick_lineup(players: Sequence[Player], squad: Collection[int]) -> Selection:
    """Best XI and captain from an existing 15 (``players`` may be the whole pool)."""
    return optimize_squad(players, budget=10**9, fixed_squad=squad)


def score_selection(sel: Selection, points: Mapping[int, float]) -> float:
    """XI points with the captain doubled; no auto-subs, missing players score 0."""
    return sum(points.get(i, 0.0) for i in sel.xi) + points.get(sel.captain, 0.0)


class CapturedFractionHook:
    """``GwMetricHook``: achieved / hindsight-optimal points of a fresh squad per gameweek.

    Both squads are chosen from the same pool (players every predictor scored that gameweek),
    with the same budget, and scored on actual points; the first from predicted points, the
    ceiling from actual points. Position and club come from ``hist_players`` (end-of-season
    club) and price from the player's last fixture that gameweek.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection, budget: int = BUDGET) -> None:
        self.con = con
        self.budget = budget
        self._ceiling: dict[tuple[str, int], float] = {}

    def _info(self, season: str, rnd: int) -> dict[int, tuple[int, int, int]]:
        rows = self.con.execute(
            """SELECT g.element_id, p.position, p.team_id, ARG_MAX(g.value, g.kickoff_time)
               FROM hist_player_gw g JOIN hist_players p USING (season, element_id)
               WHERE g.season = ? AND g.round = ? GROUP BY ALL""",
            [season, rnd],
        ).fetchall()
        return {r[0]: (r[1], r[2], r[3]) for r in rows if None not in r}

    def __call__(self, ctx: GwContext) -> Mapping[str, float]:
        info = self._info(ctx.season, ctx.round)
        ids = [i for i in ctx.predicted if i in info]

        def pool(points: Mapping[int, float]) -> list[Player]:
            return [Player(i, *info[i], points[i]) for i in ids]

        key = (ctx.season, ctx.round)
        if key not in self._ceiling:
            best = optimize_squad(pool(ctx.actual), budget=self.budget)
            self._ceiling[key] = score_selection(best, ctx.actual)
        picked = optimize_squad(pool(ctx.predicted), budget=self.budget)
        achieved = score_selection(picked, ctx.actual)
        ceiling = self._ceiling[key]
        out = {"achieved_points": achieved, "ceiling_points": ceiling}
        if ceiling > 0:
            out["captured_fraction"] = achieved / ceiling
        return out
