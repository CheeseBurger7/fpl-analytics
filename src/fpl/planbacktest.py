"""Season-long backtest of the transfer planner against simple policies, scored on actual points.

Each policy manages one squad through a season. Before gameweek g it sees only predictions made
from results before g (the walk-forward dataset's rows for g), asks ``plan_transfers`` for the best
plan over ``horizon`` gameweeks, applies it, picks the XI and captain *from predictions*, and is
scored on the actual gameweek points minus 4 per hit. Sale price = FPL selling price (half of any
rise); auto-subs and vice-captain are applied when the gameweek's minutes are known.

Future gameweeks (horizon > 1) cannot use the dataset's rows for g+j: their features include
results of g..g+j-1. Instead a player's predicted points for g+j are his latest per-fixture
prediction times the number of fixtures he has in g+j (the schedule is known in advance), i.e.
persistence. ``horizon=1`` needs no such assumption.

``simulate`` is pure (no database); ``season_inputs`` builds its inputs from the walk-forward data.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import duckdb

from fpl.backtest import Dataset, GwKey, Predictor, walk_forward_splits
from fpl.optimizer import (
    BUDGET,
    GK,
    XI_BOUNDS,
    Player,
    Selection,
    optimize_squad,
    score_selection,
)
from fpl.planner import best_plan, plan_transfers

MAX_FREE_TRANSFERS = 5


@dataclass(frozen=True)
class Policy:
    name: str
    max_transfers: int = 0  # 0 = never transfer
    margin: float = 1.0  # ``best_plan`` margin


HOLD = Policy("hold")
PLANNER = Policy("planner", max_transfers=3, margin=1.0)
PLANNER_HITS = Policy("planner_hits", max_transfers=3, margin=0.0)
DEFAULT_POLICIES = (HOLD, PLANNER, PLANNER_HITS)


@dataclass(frozen=True)
class GwInput:
    """What a policy may know before gameweek ``key``, plus the actuals used only to score it."""

    key: GwKey
    predicted: Mapping[int, float]  # eligible players: predicted GW points (fixtures summed)
    fixtures: Mapping[int, int]  # fixtures per player this GW (schedule; absent = blank)
    price: Mapping[int, int]  # tenths, carried forward over blanks
    actual: Mapping[int, float]
    minutes: Mapping[int, int] | None = None  # played minutes; None = no auto-subs


@dataclass(frozen=True)
class GwResult:
    key: GwKey
    points: float  # actual points of the chosen XI + captain, after the hit
    hit: int
    transfers: int
    out: tuple[int, ...]
    into: tuple[int, ...]
    free_transfers: int  # available before this gameweek's transfers
    bank: int  # tenths, after transfers


@dataclass
class SeasonRun:
    policy: str
    results: list[GwResult] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(r.points for r in self.results)

    @property
    def hits(self) -> int:
        return sum(r.hit for r in self.results)

    @property
    def transfers(self) -> int:
        return sum(r.transfers for r in self.results)


def next_free_transfers(free: int, used: int) -> int:
    """Free transfers for the next gameweek: unused ones bank (up to 5) plus one new."""
    return min(MAX_FREE_TRANSFERS, max(0, free - used) + 1)


def selling_price(buy: int, now: int) -> int:
    """FPL selling price (tenths): a rise is kept at half, rounded down; a fall is lost in full."""
    return now if now <= buy else buy + (now - buy) // 2


def autosub_points(
    xi: Sequence[int],
    captain: int,
    bench: Sequence[int],
    info: Mapping[int, tuple[int, int]],
    predicted: Mapping[int, float],
    actual: Mapping[int, float],
    minutes: Mapping[int, int],
) -> float:
    """XI + captain points after FPL's automatic substitutions.

    A starter with no minutes is replaced by the first legal bench player who played: the bench
    goalkeeper only for the goalkeeper, outfield bench players in order of predicted points, and
    only if the formation stays legal. If the captain did not play, the vice-captain (the starter
    with the highest prediction who played) takes the armband. Blanks have no ``minutes`` entry.
    """
    played = {i for i in set(xi) | set(bench) if minutes.get(i, 0) > 0}
    final = list(xi)
    counts = Counter(info[i][0] for i in final)
    bench_gk = [i for i in bench if info[i][0] == GK]
    bench_out = sorted((i for i in bench if info[i][0] != GK), key=lambda i: -predicted.get(i, 0.0))
    for i in list(xi):
        if i in played:
            continue
        pos = info[i][0]
        pool = bench_gk if pos == GK else bench_out
        for b in pool:
            if b not in played:
                continue
            bp = info[b][0]
            new = counts.copy()
            new[pos] -= 1
            new[bp] += 1
            if all(XI_BOUNDS[q][0] <= new[q] <= XI_BOUNDS[q][1] for q in XI_BOUNDS):
                final[final.index(i)] = b
                counts = new
                pool.remove(b)
                break
    total = sum(actual.get(i, 0.0) for i in final if i in played)
    if captain not in played:
        alt = [i for i in final if i in played]
        captain = max(alt, key=lambda i: predicted.get(i, 0.0), default=None)
    return total + (actual.get(captain, 0.0) if captain is not None else 0.0)


def _players(
    ids: set[int], info: Mapping[int, tuple[int, int]], price: Mapping[int, int]
) -> list[Player]:
    return [Player(i, info[i][0], info[i][1], price[i], 0.0) for i in sorted(ids)]


def horizon_points(gws: Sequence[GwInput], i: int, horizon: int, per_fixture: Mapping[int, float]):
    """Predicted points for gameweeks i..i+horizon-1: the real prediction now, persistence after."""
    out: list[dict[int, float]] = [dict(gws[i].predicted)]
    for j in range(i + 1, min(i + horizon, len(gws))):
        out.append({p: v * gws[j].fixtures.get(p, 0) for p, v in per_fixture.items()})
    return out


def start_squad(first: GwInput, info: Mapping[int, tuple[int, int]]) -> tuple[Selection, int]:
    """Best squad for the first gameweek's predictions under the opening budget, and the bank."""
    ids = set(first.predicted) & set(first.price) & set(info)
    pool = [Player(i, *info[i], first.price[i], first.predicted[i]) for i in sorted(ids)]
    sel = optimize_squad(pool, budget=BUDGET)
    return sel, BUDGET - sel.cost


def simulate(
    gws: Sequence[GwInput],
    info: Mapping[int, tuple[int, int]],
    policy: Policy,
    *,
    horizon: int = 1,
    discount: float = 1.0,
    start: tuple[Selection, int] | None = None,
) -> SeasonRun:
    """Run ``policy`` through ``gws``. ``info[id] = (position, team)``.

    The first gameweek is played with the starting squad and no transfers. Afterwards free
    transfers accrue one per gameweek (banked up to 5) and every transfer beyond them costs 4.
    """
    squad_sel, bank = start or start_squad(gws[0], info)
    squad = set(squad_sel.squad)
    buy = {i: gws[0].price[i] for i in squad}  # purchase prices, for the selling price
    free = 1
    per_fixture: dict[int, float] = {}
    run = SeasonRun(policy.name)
    for i, gw in enumerate(gws):
        for p, v in gw.predicted.items():
            n = gw.fixtures.get(p, 0)
            if n:
                per_fixture[p] = v / n
        pool_ids = (set(gw.predicted) | squad) & set(info)
        pool = _players(pool_ids, info, gw.price)
        pts = horizon_points(gws, i, horizon, per_fixture)
        k_max = policy.max_transfers if i else 0
        sell = {i: selling_price(buy[i], gw.price[i]) for i in squad}
        plans = plan_transfers(pool, pts, squad, bank=bank, free_transfers=free,
                               max_transfers=k_max, discount=discount,
                               sell_prices=sell)  # fmt: skip
        plan = best_plan(plans, policy.margin)
        if gw.minutes is None:
            sel = Selection(plan.squad, plan.xi[0], plan.captain[0], plan.gross, 0)
            points = score_selection(sel, gw.actual) - plan.hit
        else:
            info_ = {i: info[i] for i in plan.squad}
            bench = [i for i in plan.squad if i not in set(plan.xi[0])]
            points = autosub_points(plan.xi[0], plan.captain[0], bench, info_, gw.predicted,
                                    gw.actual, gw.minutes) - plan.hit  # fmt: skip
        buy = {i: buy[i] if i in buy else gw.price[i] for i in plan.squad}
        run.results.append(GwResult(gw.key, points, plan.hit, plan.transfers, plan.out, plan.into,
                                    free, plan.bank))  # fmt: skip
        squad, bank = set(plan.squad), plan.bank
        free = next_free_transfers(free, plan.transfers)
    return run


def ceiling_points(gw: GwInput, info: Mapping[int, tuple[int, int]]) -> float:
    """Hindsight-best fresh squad under the opening budget (context only)."""
    ids = set(gw.predicted) & set(gw.price) & set(info)
    pool = [Player(i, *info[i], gw.price[i], gw.actual.get(i, 0.0)) for i in sorted(ids)]
    return score_selection(optimize_squad(pool, budget=BUDGET), gw.actual)


# ------------------------------------------------------------------------------------ DB layer


def season_info(
    con: duckdb.DuckDBPyConnection, season: str
) -> tuple[dict[int, tuple[int, int]], dict[int, dict[int, int]]]:
    """``(position, team)`` per player and ``round -> {player: price}`` (last fixture of the round).

    Team is the end-of-season club (see the data gotchas).
    """
    info = {
        r[0]: (r[1], r[2])
        for r in con.execute(
            "SELECT element_id, position, team_id FROM hist_players WHERE season = ?", [season]
        ).fetchall()
        if None not in r
    }
    prices: dict[int, dict[int, int]] = defaultdict(dict)
    for el, rnd, value in con.execute(
        "SELECT element_id, round, ARG_MAX(value, kickoff_time) FROM hist_player_gw "
        "WHERE season = ? GROUP BY ALL", [season]).fetchall():  # fmt: skip
        if value is not None:
            prices[rnd][el] = value
    return info, prices


def season_inputs(
    data: Dataset,
    predictors: Sequence[Predictor],
    season: str,
    con: duckdb.DuckDBPyConnection,
    *,
    min_history: int = 5,
) -> tuple[dict[str, list[GwInput]], dict[int, tuple[int, int]]]:
    """Per predictor, the season's ``GwInput`` list; fits each predictor once for the season.

    All predictors share one eligible pool per gameweek (enough history and a prediction from
    every predictor). Prices carry forward over a player's blank gameweeks. Rounds with no
    eligible player are left out, so all policies are scored on the same gameweeks.
    """
    info, round_prices = season_info(con, season)
    round_minutes: dict[int, dict[int, int]] = defaultdict(dict)
    for el, rnd, mins in con.execute(
        "SELECT element_id, round, SUM(minutes) FROM hist_player_gw "
        "WHERE season = ? AND minutes IS NOT NULL GROUP BY ALL", [season]).fetchall():  # fmt: skip
        round_minutes[rnd][el] = int(mins)
    (split,) = [s for s in walk_forward_splits(data, [season], step=None)]
    for p in predictors:
        p.fit(data, split.train)
    elements, targets = data.columns["element_id"], data.columns["target"]
    n_prior = data.columns["n_prior_fixtures"]
    out: dict[str, list[GwInput]] = {p.name: [] for p in predictors}
    carried: dict[int, int] = {}
    for key, first, end in split.eval:
        carried.update(round_prices.get(key[1], {}))
        idx = range(first, end)
        fixtures: dict[int, int] = defaultdict(int)
        actual: dict[int, float] = defaultdict(float)
        for i in idx:
            fixtures[elements[i]] += 1
            actual[elements[i]] += targets[i]
        sums: dict[str, dict[int, float | None]] = {}
        for p in predictors:
            s: dict[int, float | None] = defaultdict(float)
            for i, v in zip(idx, p.predict(data, idx), strict=True):
                el = elements[i]
                s[el] = None if (v is None or s[el] is None) else s[el] + v
            sums[p.name] = s
        eligible = {
            elements[i] for i in idx if (n_prior[i] or 0) >= min_history
        } & {el for el in fixtures if all(s[el] is not None for s in sums.values())}
        eligible &= set(info) & set(carried)
        if not eligible:
            continue  # no forecast this round (e.g. vaastav has no xp): skipped for every policy
        for p in predictors:
            out[p.name].append(GwInput(
                key, {el: sums[p.name][el] for el in eligible}, dict(fixtures),
                dict(carried), dict(actual), round_minutes.get(key[1]) or None,
            ))  # fmt: skip
    return out, info


def summarize(runs: Sequence[SeasonRun]) -> list[dict[str, object]]:
    return [
        {"policy": r.policy, "n_gws": len(r.results), "total": r.total,
         "per_gw": r.total / len(r.results), "hit_pts": r.hits, "transfers": r.transfers}
        for r in runs
    ]  # fmt: skip
